# Local Speech to Text for Arduino UNO Q

An Arduino App Lab app that turns speech into text **entirely on the UNO Q**.
You speak into your computer's microphone in the browser, the audio is sent to
the board, and the transcript comes back. No cloud service, no API key, and no
Internet connection is needed once the app is installed.

Recognition runs on the UNO Q CPU with [Cactus](https://github.com/cactus-compute/cactus)
and the [Whistle](https://huggingface.co/Cactus-Compute/whistle) English speech
model. The Cactus runtime is bundled in this repository. The model file
(17 MB) is downloaded separately, see [Get the speech model](#get-the-speech-model).

The app is intentionally small. Use it as a starting point for your own speech
projects, workshops, and hackathons.

## Features

- Record a phrase in the browser; it stops on **Stop** or, optionally, after a pause.
- Transcribe an audio file (up to 30 seconds). The browser converts it to the
  required format, so no tools are needed on your computer.
- Shows how long the board took and the real-time factor of each transcription.
- Includes a reusable **Local ASR** custom brick with three APIs: batch
  transcription, live streaming captions, and a health check.

## Requirements

- Arduino UNO Q
- Arduino App Lab 0.7.0 or later (Arduino App CLI 0.9.0 or later on the board)
- A computer with a microphone and a recent browser (Chrome recommended)
- A USB cable, or the board and computer on the same network

The speech brick runs on Arduino's Python base image
(`ghcr.io/arduino/app-bricks/python-apps-base:0.13.1`). Boards with Arduino App
CLI 0.14 already have it. On older boards the first run downloads it, which
needs Internet access. After that, everything works offline.

## Get the speech model

The Whistle model is not stored in git. The app needs it at
`bricks/local_asr/service/models/whistle.cact`.

| File            | Download                                                                                                                                  | SHA-256                                                            |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `whistle.cact`  | [huggingface.co/Cactus-Compute/whistle](https://huggingface.co/Cactus-Compute/whistle/resolve/741118687e1f008f06d1351a402a731274789790/whistle.cact) | `b6e02f048568ac5d01a2042556c658061e699acbc0aa2a1439f52f3d461dffeb` |

On macOS or Linux, the script downloads it to the right place and checks the
checksum:

```bash
git clone https://github.com/91volt/uno-q-speech-to-text.git
cd uno-q-speech-to-text
sh tools/fetch-model.sh
```

On Windows, open the download link in a browser and save the file as
`bricks/local_asr/service/models/whistle.cact`.

If the app runs without the model, the page shows a message with the download
link instead of the recording controls.

## Get the app onto the board

### Option A: Import a ZIP in Arduino App Lab

1. Build a ZIP that includes the model (the model is downloaded if missing):

   ```bash
   sh tools/package.sh
   ```

   This creates `dist/local-speech-to-text.zip`. If a ZIP is attached to a
   release of this repository, you can download that one instead; it already
   contains the model.

2. In Arduino App Lab, use **Import app** and select the ZIP.
3. Press **Run**.

### Option B: Copy the folder to the board

Download the model first (see above). User apps live in `~/ArduinoApps` on the
board. Copy the folder over SSH and start the app:

```bash
scp -r uno-q-speech-to-text arduino@<board-name>.local:ArduinoApps/local-speech-to-text
ssh arduino@<board-name>.local arduino-app-cli app start user:local-speech-to-text
```

The app then also appears in Arduino App Lab.

### Adding the model to an app that is already on the board

If you imported the app without the model, download it straight into the app
folder on the board (the board needs Internet access for this step), then
restart the app:

```bash
ssh arduino@<board-name>.local
cd ~/ArduinoApps/local-speech-to-text    # use the imported folder name
sh tools/fetch-model.sh                  # or copy whistle.cact with scp
arduino-app-cli app restart user:local-speech-to-text
```

`tools/` is not included in the release ZIP. In that case use `scp` to copy
`whistle.cact` into `bricks/local_asr/service/models/` on the board.

## Open the web interface

The app serves its page on port **7000** of the board.

Browsers only allow microphone access on `localhost` or HTTPS pages, so open the
page through a local port forward:

- **USB:**

  ```bash
  adb forward tcp:17000 tcp:7000
  ```

  Then open <http://127.0.0.1:17000>.

- **Network:**

  ```bash
  ssh -L 17000:localhost:7000 arduino@<board-name>.local
  ```

  Then open <http://127.0.0.1:17000>.

Opening `http://<board-ip>:7000` directly also works, but the browser will block
the microphone. File transcription still works in that case.

## Use it

1. Wait until the status says **Ready**.
2. Press **Record a phrase**, allow microphone access, and speak.
3. Press **Stop & transcribe**, or pause for about one second if
   **Stop after a pause** is checked. Recordings stop automatically after 25 seconds.
4. The text appears in the **Transcript** panel. Use **Copy** or **Clear** as needed.

To transcribe a file instead, open **Transcribe an audio file** and choose a
recording of 30 seconds or less.

Audio is processed in memory and never saved. The transcript only lives in the
open page.

## How it works

```text
 Browser (your computer)            UNO Q
┌────────────────────────┐   ┌──────────────────────────────────────────────┐
│ assets/index.html      │   │ App container (python/)                      │
│ assets/phrase.js       │──▶│  gateway.py  serves the page on :7000 and    │
│ assets/capture.js      │   │              forwards /api/* to the brick    │
│                        │◀──│                    │                         │
│ mic → PCM16 16 kHz     │   │                    ▼                         │
└────────────────────────┘   │ Local ASR brick container (bricks/local_asr) │
                             │  service/ :9000  Cactus Whistle on the CPU   │
                             └──────────────────────────────────────────────┘
```

1. The browser records the microphone with an AudioWorklet, converts the audio
   to mono 16 kHz 16-bit PCM, and posts it to `/api/transcribe`.
2. `python/gateway.py` serves the page and passes API requests to the brick.
   It contains no speech logic.
3. The **Local ASR** brick runs in its own container, managed by App Lab through
   `brick_compose.yaml`. It loads the Whistle model once and returns the text.

The brick only listens on the internal app network. Only port 7000 is exposed.

## Local ASR brick API

The brick can be reused by other apps. Copy `bricks/local_asr/` into your app
and add `- local_asr: {}` under `bricks:` in `app.yaml`.

### From Python

```python
from local_asr import LocalASR

asr = LocalASR()
asr.health()                    # {"ready": true, "engine": "whistle", ...}
asr.transcribe_wav(wav_bytes)   # {"text": "...", "processing_seconds": ..., ...}

async for event in asr.stream(chunks):
    # chunks: async iterable of mono 16 kHz PCM16 bytes, at most 1 s each,
    # sent at speaking pace.
    # event["text"]: confirmed text, append it.
    # event["pending"]: provisional text, replace the previous value.
    ...
```

### Over HTTP (through the app on port 7000)

| Endpoint              | Method    | Description                                                                                                     |
| --------------------- | --------- | --------------------------------------------------------------------------------------------------------------- |
| `/api/health`         | GET       | Readiness, engine name, and whether a recognition is running.                                                  |
| `/api/transcribe`     | POST      | Body: mono 16 kHz 16-bit WAV (`audio/wav`) or raw PCM16 (`application/octet-stream`), 0.1 to 30 s. Returns JSON. |
| `/api/live`           | WebSocket | Streaming captions. See below.                                                                                  |

Example with a WAV file already in the right format:

```bash
curl -X POST -H "Content-Type: audio/wav" --data-binary @speech.wav \
  http://127.0.0.1:17000/api/transcribe
```

Streaming protocol for `/api/live`:

1. The server sends `{"type": "ready", "sample_rate": 16000, "chunk_samples": 16000}`.
2. The client sends binary PCM16 chunks of at most one second, at speaking pace.
3. The server sends `{"type": "caption", "text": ..., "pending": ...}` events.
4. The client sends `{"type": "stop"}`; the server finishes and sends `{"type": "done"}`.

Errors arrive as `{"type": "error", "message": ...}`.

Only one recognition runs at a time. A second request gets HTTP 429 while the
board is busy. Requests from other web origins are rejected.

## Project layout

```text
app.yaml                        App Lab manifest: name, port 7000, local_asr brick
python/
  main.py                       App entry point: creates the brick and starts the gateway
  gateway.py                    Web server: page, static files, API forwarding
  requirements.txt              Extra Python packages for the app (none needed)
assets/
  index.html                    The page (markup and styles)
  phrase.js                     Recording, file input, and calls to the API
  capture.js                    AudioWorklet that collects microphone samples
bricks/local_asr/
  brick_config.yaml             Brick identity
  brick_compose.yaml            Brick container: image, entry point, health check
  __init__.py                   Python client: LocalASR
  README.md                     Brick reference
  service/
    main.py                     Service entry point (port 9000)
    server.py                   HTTP routes and request limits
    live.py                     WebSocket streaming session
    engines.py                  Audio validation and the Whistle recognizer
    models/                     Whistle model goes here (downloaded, not in git)
    runtime/libcactus.so        Cactus native library (Linux aarch64)
  vendor/                       Bundled Python packages (Linux aarch64, CPython 3.13)
tools/
  fetch-model.sh                Download and verify the model
  package.sh                    Build dist/local-speech-to-text.zip with the model
```

Day-to-day work only touches `assets/`, `python/`, and the small Python files in
`bricks/local_asr/`. The model, native library, and `vendor/` folder are
dependencies and normally stay as they are. `tools/` is for development only
and is left out of the packaged ZIP.

## Ideas for extending it

- Show live captions while speaking with the `/api/live` WebSocket or `LocalASR.stream()`.
- Recognize voice commands in `python/main.py` and act on them, for example by
  calling the board's microcontroller through the Bridge.
- Add a sketch folder to drive LEDs, displays, or motors from recognized words.
- Pass the transcript to a local language model or a text-to-speech brick.

## Updating Cactus or the model

The bundled files are pinned to:

| Item                    | Version                                                                       |
| ----------------------- | ----------------------------------------------------------------------------- |
| `cactus-compute`        | 4.1.0                                                                         |
| Cactus engine revision  | `4e822c9036be2eb0e47ef556df32a818bb1572ef`                                    |
| `models/whistle.cact`   | SHA-256 `b6e02f048568ac5d01a2042556c658061e699acbc0aa2a1439f52f3d461dffeb`    |
| `runtime/libcactus.so`  | SHA-256 `520ea4f06ee2e8a83116eaf9120b674395fea4e41b21efc1f3bd8364b3c237b9`    |

To move to a newer release, update all three together on a Linux aarch64
machine with CPython 3.13, the same as the brick container:

1. Install the packages into `vendor/`:
   `pip install --target bricks/local_asr/vendor cactus-compute==<version> aiohttp`
2. Download the matching library with `cactus.agent.fetch.fetch_library(...)`
   into `service/runtime/`.
3. Update the model URL and SHA-256 in `tools/fetch-model.sh`,
   `service/engines.py`, `service/models/README.md`, and this README.
4. Run the app on the board and check a recording and a file transcription.

## Publishing a release

```bash
sh tools/package.sh
gh release create v1.0.0 dist/local-speech-to-text.zip --title "v1.0.0"
```

The release ZIP is the one users import; it contains the model, so it works
without any extra download.

## Limitations

- English only.
- Transcripts are estimates. Names, accents, and noisy rooms can cause errors.
- 30 seconds of audio per request. Use streaming for longer speech.
- App Lab runs one app at a time, and the brick runs one recognition at a time.

## Third-party software

Third-party software keeps its own license:

- Cactus (`service/runtime/libcactus.so` and `vendor/cactus/`) and the Whistle
  model: Apache License 2.0.
- The packages in `bricks/local_asr/vendor/`: the license of each package is
  included in its `*.dist-info` folder.
