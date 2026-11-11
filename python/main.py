"""App Lab entry point. The model is owned by the local_asr custom brick."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bricks/local_asr/vendor"))
from arduino.app_utils import App, brick
from local_asr import LocalASR
from gateway import run

asr = LocalASR()


@brick
class BrowserUI:
    @brick.execute
    def serve(self):
        run(asr)


ui = BrowserUI()
App.run()
