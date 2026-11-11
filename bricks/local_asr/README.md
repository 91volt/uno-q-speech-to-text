# Local ASR custom brick

Cactus Whistle 4.1.0 on the UNO Q CPU. The ARM64 runtime and Python packages
are included. The model is downloaded separately into `service/models/`; see
`service/models/README.md`. No API keys or inference network access are required.
The sidecar uses Arduino's Python apps base image 0.13.1; Docker downloads it only
if missing. No extracted virtual-environment executable is used.

Import from Python with `from local_asr import LocalASR` and instantiate once.
`asr.health()` returns readiness; `asr.transcribe_wav(wav_bytes)` returns text.
`async for event in asr.stream(chunks)` yields continuous captions for an async
PCM16 chunk source. Append confirmed `text`; replace revisable `pending`.
The service listens on port 9000 on the internal app network, without a host port.
Only one recognition session runs at a time. Four queued audio chunks are allowed.

The service implementation is under `service/`, the model under `service/models/`,
and native library under `service/runtime/`. The bundled `vendor/` packages target
Linux aarch64 / CPython 3.13. Do not substitute a different Python ABI.

Whistle and Cactus: Apache-2.0. See bundled package licensing metadata.
Model source: https://huggingface.co/Cactus-Compute/whistle
