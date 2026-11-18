"""Speed and memory benchmark for a PC; the code lives in the package so that the packaged app can run it too.

    uv run python tools/bench.py [--sample DIR]
    GelCam-console.exe --bench [--sample DIR]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gelcam.bench import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
