"""Reusable Local ASR brick. Inference lives in its managed sidecar container."""

import asyncio
import json
import urllib.request
from arduino.app_utils import brick


@brick
class LocalASR:
    URL = "http://local_asr:9000"

    def health(self):
        with urllib.request.urlopen(self.URL + "/api/health", timeout=5) as response:
            return json.load(response)

    def transcribe_wav(self, audio: bytes):
        request = urllib.request.Request(
            self.URL + "/api/transcribe",
            data=audio,
            headers={"Content-Type": "audio/wav"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)

    async def stream(self, chunks):
        """chunks: async iterable of mono 16 kHz PCM16 bytes, <= one second each.

        Yield caption dictionaries. Append text, replace pending. Send at audio pace.
        """
        from aiohttp import ClientSession

        async with ClientSession() as client:
            async with client.ws_connect(self.URL + "/api/live") as socket:
                await socket.receive_json()

                async def send():
                    async for chunk in chunks:
                        await socket.send_bytes(chunk)
                    await socket.send_json({"type": "stop"})

                task = asyncio.create_task(send())
                try:
                    async for message in socket:
                        event = json.loads(message.data)
                        if event["type"] == "done":
                            await task
                            return
                        if event["type"] == "error":
                            raise RuntimeError(event["message"])
                        yield event
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
