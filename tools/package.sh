#!/usr/bin/env sh
# Build an App Lab importable ZIP that includes the speech model.
# Output: dist/local-speech-to-text.zip. Requires git, curl and zip.
set -eu

NAME="local-speech-to-text"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="bricks/local_asr/service/models/whistle.cact"

cd "$ROOT"
sh tools/fetch-model.sh

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# Only committed files are packaged; paths marked export-ignore are skipped.
git archive --format=tar --prefix="$NAME/" HEAD | tar -x -C "$STAGE"
cp "$MODEL" "$STAGE/$NAME/$MODEL"

mkdir -p dist
rm -f "dist/$NAME.zip"
(cd "$STAGE" && zip -qr -X "$ROOT/dist/$NAME.zip" "$NAME")
echo "Created dist/$NAME.zip"
