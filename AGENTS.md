# AGENTS.md

Guidance for automated coding agents working in this repository. Read
`README.md` first for what the app does and how it is installed.

## What this is

An Arduino App Lab app for the UNO Q (Linux aarch64). A browser page records
speech, the app forwards the audio to the **Local ASR** custom brick, and the
brick transcribes it on the board CPU with Cactus Whistle. There is no
microcontroller sketch, no build step, and no network access at inference time.

## Architecture in one minute

- `app.yaml`: App Lab manifest. Exposes port 7000 and declares the `local_asr` brick.
- `python/main.py`: App Lab entry point. Creates `LocalASR()` and runs the gateway.
- `python/gateway.py`: aiohttp server on `0.0.0.0:7000`. Serves `assets/` and
  forwards `/api/health`, `/api/transcribe`, and `/api/live` to the brick at
  `http://local_asr:9000`. It must not contain speech logic.
- `assets/`: plain HTML and ES modules, no bundler. `index.html` loads
  `phrase.js`; `capture.js` is the AudioWorklet loaded from `/static/capture.js`.
- `bricks/local_asr/__init__.py`: `LocalASR` client (`health`, `transcribe_wav`, `stream`).
- `bricks/local_asr/brick_compose.yaml`: brick container. Mounts the brick folder
  read-only at `/brick` and runs `python /brick/service/main.py`.
- `bricks/local_asr/service/`: the speech service.
  - `server.py`: routes, origin check, single-inference lock, upload limits.
  - `live.py`: WebSocket streaming session with a bounded queue.
  - `engines.py`: `decode_audio` validation and the `Recognizer` wrapper.
  - `main.py`: loads the model. If it is missing or fails to load, it serves
    `make_setup_app()` instead, so `/api/health` returns `ready: false` with an
    `error` message and the page shows it.
- `tools/`: development scripts, excluded from packaging by `.gitattributes`.
  - `fetch-model.sh`: downloads `whistle.cact` and verifies its SHA-256.
  - `package.sh`: builds `dist/local-speech-to-text.zip` from `HEAD` plus the model.

## The model is not in git

`bricks/local_asr/service/models/whistle.cact` is ignored by git. Run
`sh tools/fetch-model.sh` to get it. Never commit it. Release ZIPs built with
`tools/package.sh` include it. The URL and hash appear in `tools/fetch-model.sh`,
`service/engines.py`, `service/models/README.md`, and `README.md`; keep them in sync.

## Hard constraints

- **Do not edit** `bricks/local_asr/vendor/` or `service/runtime/` by hand. They are pinned binaries for Linux aarch64 and
  CPython 3.13. To update them, follow "Updating Cactus or the model" in
  `README.md` and update the pinned versions and hashes there.
- The brick folder is mounted read-only. Do not write files at runtime.
- Audio format everywhere is mono, 16 kHz, little-endian 16-bit PCM.
  Limits: 0.1 to 30 s per request, at most 1 s (32000 bytes) per WebSocket chunk,
  four queued chunks.
- One recognition at a time. Keep the shared `busy` lock around every model call,
  and never release it while a native call is still running.
- Keep the same-origin check on every audio endpoint in both the gateway and the service.
- The brick port (9000) stays internal. Only port 7000 is published.
- Browser microphone capture requires a secure context (localhost or HTTPS).
  Do not remove the ADB/SSH port-forward guidance.
- The frontend has no build step. Keep it that way unless asked.
- Only English is supported by the bundled model.

## Making changes

- New UI features: edit `assets/` and, if a new endpoint is needed, add a route
  in `python/gateway.py` that forwards to the brick.
- New recognition features: add them in `bricks/local_asr/service/`, then expose
  them in `bricks/local_asr/__init__.py` and in the gateway.
- New Python packages for the app container go in `python/requirements.txt`.
  Packages for the brick container must be vendored for aarch64 / CPython 3.13.
- Update `README.md` (and `bricks/local_asr/README.md` for brick changes) in the
  same change when behavior, endpoints, or limits change.

## Checking your work

On any machine:

```bash
python3 -m py_compile python/*.py bricks/local_asr/__init__.py bricks/local_asr/service/*.py
```

`server.py` and `live.py` can be exercised on a development machine with
`aiohttp` installed by passing a stub object to `make_app()` that provides
`engine`, `load_s`, `transcribe(pcm)`, and `stream(chunks)`. The real
`Recognizer` only loads on Linux aarch64. `make_setup_app(message)` can be
tested the same way.

`package.sh` packages committed files only; commit before packaging.

On the board:

```bash
arduino-app-cli app start user:local-speech-to-text
arduino-app-cli app logs user:local-speech-to-text --follow
docker ps                              # the brick container ends in -local_asr-1
docker logs <app>-local_asr-1          # brick service log
```

Then open the page through `adb forward tcp:17000 tcp:7000` and check a
recording and a file transcription.

## Style

- Python: formatted with `ruff format` (Black-compatible), standard library and
  aiohttp only in app code.
- JavaScript: plain ES modules, formatted with Prettier defaults.
- Comments explain why, not what. Keep files small and single-purpose.
- Commit messages: short imperative subject. No generated-by or co-author trailers.
