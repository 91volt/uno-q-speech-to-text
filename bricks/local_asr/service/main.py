"""Local ASR service entry point, started by brick_compose.yaml inside the brick container."""

from pathlib import Path
import logging
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor"))
from aiohttp import web
from engines import Recognizer
from server import make_app, make_setup_app

logging.basicConfig(level=logging.INFO)
try:
    app = make_app(Recognizer(int(os.getenv("ASR_THREADS", "4"))))
except Exception as exc:
    logging.error("Local ASR is not ready: %s", exc)
    app = make_setup_app(str(exc))
web.run_app(app, host="0.0.0.0", port=9000, access_log=None)
