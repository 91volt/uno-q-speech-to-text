"""HTTP API of the Local ASR service: health, batch transcription and live streaming."""

import asyncio
import logging
from aiohttp import web
from engines import decode_audio
from live import serve_live

log = logging.getLogger("local-stt")


def make_app(recognizer):
    # One inference at a time; no unbounded backlog on a four-core SBC.
    busy = asyncio.Lock()

    async def health(request):
        return web.json_response(
            {
                "ready": True,
                "engine": recognizer.engine,
                "language": "en",
                "busy": busy.locked(),
                "local_only": True,
                "load_seconds": recognizer.load_s,
            }
        )

    async def transcribe(request):
        # Only the same-origin UI or non-browser API clients may submit audio.
        origin = request.headers.get("Origin")
        if origin and origin != f"{request.scheme}://{request.host}":
            raise web.HTTPForbidden(text="Cross-origin audio submission is disabled.")
        if busy.locked():
            return web.json_response(
                {"error": "Recognizer is busy. Try again after the current recording."},
                status=429,
            )
        async with busy:
            try:
                data = await asyncio.wait_for(request.read(), timeout=15)
                pcm = decode_audio(data, request.content_type)
            except ValueError as exc:
                return web.json_response({"error": str(exc)}, status=400)
            except asyncio.TimeoutError:
                return web.json_response(
                    {"error": "Audio upload timed out."}, status=408
                )
            try:
                # Shield so a disconnected client cannot unlock an in-flight native call.
                task = asyncio.create_task(
                    asyncio.to_thread(recognizer.transcribe, pcm)
                )
                try:
                    result = await asyncio.shield(task)
                except asyncio.CancelledError:
                    await task
                    raise
                return web.json_response(result)
            except Exception:
                log.exception("Local inference failed")
                return web.json_response(
                    {"error": "Local inference failed. Check the service log."},
                    status=500,
                )

    async def live(request):
        return await serve_live(request, recognizer, busy)

    @web.middleware
    async def headers(request, handler):
        response = await handler(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Permissions-Policy"] = "microphone=(self)"
        return response

    app = web.Application(client_max_size=16000 * 2 * 30 + 65536, middlewares=[headers])
    app.router.add_get("/api/health", health)
    app.router.add_post("/api/transcribe", transcribe)
    app.router.add_get("/api/live", live)
    return app


def make_setup_app(message):
    """Answer health checks with the setup problem instead of crashing the brick.

    The container stays healthy so App Lab can start the app and the page can
    show the user what is missing.
    """

    async def health(request):
        return web.json_response(
            {"ready": False, "engine": None, "language": "en", "error": message}
        )

    async def unavailable(request):
        return web.json_response({"error": message}, status=503)

    app = web.Application()
    app.router.add_get("/api/health", health)
    app.router.add_post("/api/transcribe", unavailable)
    app.router.add_get("/api/live", unavailable)
    return app
