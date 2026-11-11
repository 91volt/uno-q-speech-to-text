#!/usr/bin/env sh
# Download the Whistle speech model into the Local ASR brick and verify it.
# Works on macOS, Linux and on the UNO Q itself. Requires curl.
set -eu

URL="https://huggingface.co/Cactus-Compute/whistle/resolve/741118687e1f008f06d1351a402a731274789790/whistle.cact"
SHA256="b6e02f048568ac5d01a2042556c658061e699acbc0aa2a1439f52f3d461dffeb"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/bricks/local_asr/service/models/whistle.cact"

checksum() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d ' ' -f 1
  else
    shasum -a 256 "$1" | cut -d ' ' -f 1
  fi
}

if [ -f "$DEST" ] && [ "$(checksum "$DEST")" = "$SHA256" ]; then
  echo "Model already present: $DEST"
  exit 0
fi

echo "Downloading whistle.cact (17 MB)..."
curl -fL --progress-bar -o "$DEST.part" "$URL"

if [ "$(checksum "$DEST.part")" != "$SHA256" ]; then
  rm -f "$DEST.part"
  echo "Checksum mismatch. The download is incomplete or the file has changed." >&2
  exit 1
fi

mv "$DEST.part" "$DEST"
echo "Model saved and verified: $DEST"
