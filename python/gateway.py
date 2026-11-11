"""UI + transparent transport. All recognition stays inside LocalASR."""

import asyncio
from pathlib import Path
from aiohttp import web, ClientSession, ClientTimeout, WSMsgType

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def run(asr):
    async def clients(app):
        app["client"] = ClientSession(
            timeout=ClientTimeout(total=None, sock_connect=10)
        )
        yield
        await app["client"].close()

    def origin_check(request):
        origin = request.headers.get("Origin")
        if origin and origin != f"{request.scheme}://{request.host}":
            raise web.HTTPForbidden(text="Cross-origin audio is disabled.")

    async def index(request):
        return web.FileResponse(ASSETS / "index.html")

    async def proxy(request):
        origin_check(request)
        body = await request.read() if request.method == "POST" else None
        async with request.app["client"].request(
            request.method,
            asr.URL + request.path,
            data=body,
            headers={"Content-Type": request.content_type},
        ) as response:
            return web.Response(
                body=await response.read(),
                status=response.status,
                content_type=response.content_type,
                headers={"Cache-Control": "no-store"},
            )

    async def live(request):
        origin_check(request)
        try:
            upstream = await request.app["client"].ws_connect(
                asr.URL + "/api/live", max_msg_size=1024 * 1024
            )
        except Exception:
            raise web.HTTPServiceUnavailable(text="ASR is busy or unavailable.")
        socket = web.WebSocketResponse(max_msg_size=65536, heartbeat=20)
        await socket.prepare(request)

        async def send_audio():
            async for message in socket:
                if message.type == WSMsgType.BINARY:
                    await upstream.send_bytes(message.data)
                elif message.type == WSMsgType.TEXT:
                    await upstream.send_str(message.data)
                else:
                    break

        async def receive_captions():
            async for message in upstream:
                if message.type == WSMsgType.TEXT:
                    await socket.send_str(message.data)
                else:
                    break

        tasks = [
            asyncio.create_task(send_audio()),
            asyncio.create_task(receive_captions()),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await upstream.close()
            await socket.close()
        return socket

    app = web.Application(client_max_size=1025536)
    app.cleanup_ctx.append(clients)
    app.router.add_get("/", index)
    app.router.add_get("/api/health", proxy)
    app.router.add_post("/api/transcribe", proxy)
    app.router.add_get("/api/live", live)
    app.router.add_static("/static/", ASSETS)
    web.run_app(app, host="0.0.0.0", port=7000, handle_signals=False, access_log=None)
