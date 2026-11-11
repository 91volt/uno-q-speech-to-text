"""WebSocket transport for a single bounded, continuous recognition session.

Protocol: client sends mono 16 kHz PCM16 binary chunks (<= 1 s), then
{"type":"stop"}. Server emits ready, caption, done, or error JSON events.
Only this adapter knows about WebSockets; engines supply an iterator of events.
"""

import asyncio
import json
import queue
import threading
from aiohttp import web, WSMsgType


async def serve_live(request, recognizer, busy):
    origin = request.headers.get("Origin")
    if origin and origin != f"{request.scheme}://{request.host}":
        raise web.HTTPForbidden(text="Cross-origin audio submission is disabled.")
    if not hasattr(recognizer, "stream"):
        raise web.HTTPBadRequest(text="This engine does not support streaming.")
    if busy.locked():
        raise web.HTTPTooManyRequests(text="Another recognition session is active.")
    async with busy:
        ws = web.WebSocketResponse(max_msg_size=65536, heartbeat=20)
        await ws.prepare(request)
        audio = queue.Queue(maxsize=4)
        loop = asyncio.get_running_loop()
        cancelled = threading.Event()
        ended = False

        def chunks():
            while not cancelled.is_set():
                try:
                    chunk = audio.get(timeout=0.25)
                except queue.Empty:
                    continue
                if chunk is None:
                    return
                yield chunk

        def emit(event):
            # Backpressure includes the browser connection, not just inference.
            asyncio.run_coroutine_threadsafe(ws.send_json(event), loop).result(
                timeout=10
            )

        def worker():
            try:
                for event in recognizer.stream(chunks()):
                    if cancelled.is_set():
                        return
                    emit({"type": "caption", **event})
                emit({"type": "done"})
            except Exception:
                if not cancelled.is_set():
                    try:
                        emit(
                            {
                                "type": "error",
                                "message": "Streaming inference failed. Check the board log.",
                            }
                        )
                    except Exception:
                        pass
                raise

        task = asyncio.create_task(asyncio.to_thread(worker))
        await ws.send_json(
            {"type": "ready", "sample_rate": 16000, "chunk_samples": 16000}
        )
        try:
            async for message in ws:
                if message.type == WSMsgType.BINARY:
                    if (
                        not message.data
                        or len(message.data) % 2
                        or len(message.data) > 32000
                    ):
                        await ws.send_json(
                            {
                                "type": "error",
                                "message": "Expected complete PCM16 samples.",
                            }
                        )
                        break
                    try:
                        audio.put_nowait(message.data)
                    except queue.Full:
                        await ws.send_json(
                            {
                                "type": "error",
                                "message": "Audio is arriving faster than the board can process it. Please restart.",
                            }
                        )
                        break
                elif message.type == WSMsgType.TEXT:
                    try:
                        command = json.loads(message.data)
                    except ValueError:
                        command = None
                    if command != {"type": "stop"}:
                        await ws.send_json(
                            {"type": "error", "message": "Unknown stream command."}
                        )
                        break
                    await asyncio.to_thread(audio.put, None, True, 10)
                    ended = True
                    await asyncio.wait_for(asyncio.shield(task), timeout=30)
                    break
                elif message.type == WSMsgType.ERROR:
                    break
        finally:
            cancelled.set()
            # Never release the engine lock while the native worker is running.
            try:
                await asyncio.shield(task)
            except Exception:
                if ended:
                    request.app.logger.exception("Streaming worker failed")
            await ws.close()
        return ws
