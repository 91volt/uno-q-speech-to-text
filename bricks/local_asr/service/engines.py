"""Audio validation and the Cactus Whistle recognizer. Inference never touches the network."""

import array
import io
import math
import os
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RATE = 16000
MAX_SECONDS = 30
MODEL = ROOT / "models/whistle.cact"
MODEL_URL = (
    "https://huggingface.co/Cactus-Compute/whistle/resolve/"
    "741118687e1f008f06d1351a402a731274789790/whistle.cact"
)
os.environ["CACTUS_TELEMETRY"] = "0"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["CACTUS_LIB_PATH"] = str(ROOT / "runtime/libcactus.so")


def decode_audio(data, content_type):
    """Accept canonical WAV or raw little-endian PCM16, never compressed uploads."""
    if not data:
        raise ValueError("Empty audio.")
    if len(data) > RATE * 2 * MAX_SECONDS + 65536:
        raise ValueError("Audio exceeds the 30-second limit.")
    if content_type in ("audio/wav", "audio/x-wav", "audio/wave"):
        try:
            with wave.open(io.BytesIO(data), "rb") as w:
                if (
                    w.getnchannels(),
                    w.getsampwidth(),
                    w.getframerate(),
                    w.getcomptype(),
                ) != (1, 2, RATE, "NONE"):
                    raise ValueError(
                        "WAV must be mono, 16 kHz, 16-bit PCM. Convert it first."
                    )
                if w.getnframes() > RATE * MAX_SECONDS:
                    raise ValueError("Audio exceeds the 30-second limit.")
                expected = w.getnframes() * 2
                data = w.readframes(w.getnframes())
                if len(data) != expected:
                    raise ValueError("Truncated WAV.")
        except (wave.Error, EOFError) as exc:
            raise ValueError("Invalid WAV file.") from exc
    elif content_type != "application/octet-stream":
        raise ValueError(
            "Use audio/wav or application/octet-stream (mono 16 kHz PCM16)."
        )
    if len(data) % 2 or not 3200 <= len(data) <= RATE * 2 * MAX_SECONDS:
        raise ValueError(
            "Audio must contain 0.1 to 30 seconds of complete PCM16 samples."
        )
    pcm = array.array("h", data)
    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm


class Recognizer:
    """Wraps one Cactus Whistle model instance. Not thread-safe: callers serialize access."""

    engine = "whistle"

    def __init__(self, threads=4):
        if not MODEL.is_file():
            # The model is not stored in git; see models/README.md.
            raise FileNotFoundError(
                "Speech model not found. Download whistle.cact from "
                f"{MODEL_URL} into bricks/local_asr/service/models/ "
                "and restart the app."
            )
        import cactus

        start = time.perf_counter()
        self.threads = threads
        cactus.set_threads(threads)
        self.model = cactus.Whistle(weights=MODEL)
        self.load_s = time.perf_counter() - start

    def stream(self, chunks):
        """Yield stable text, revisable pending text, and word timestamps.

        chunks contains little-endian mono 16 kHz PCM16 bytes. Ownership of the
        shared engine is handled by the caller for the entire session.
        """

        def samples():
            for chunk in chunks:
                pcm = array.array("h", chunk)
                if sys.byteorder != "little":
                    pcm.byteswap()
                yield array.array("f", (x / 32768 for x in pcm))

        yield from self.model.stream(samples(), language="en")

    def transcribe(self, pcm):
        start = time.perf_counter()
        duration = len(pcm) / RATE
        rms = math.sqrt(sum(x * x for x in pcm) / len(pcm)) / 32768
        # This only rejects near-digital silence. It is not a speech classifier.
        if rms < 0.0003:
            result = {"text": "", "language": "en", "skipped": "silence"}
        else:
            samples = array.array("f", (x / 32768 for x in pcm))
            result = self.model.transcribe(samples, language="en")
        elapsed = time.perf_counter() - start
        return {
            **result,
            "engine": self.engine,
            "audio_seconds": duration,
            "processing_seconds": elapsed,
            "real_time_factor": elapsed / duration,
        }
