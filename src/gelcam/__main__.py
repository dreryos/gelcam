"""Run with: `uv run python -m gelcam` (camera via EDSDK) or `--mock` (simulation)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gelcam")
    ap.add_argument("--mock", nargs="?", const="", metavar="FOLDER_WITH_CR2",
                    help="simulated camera; optionally a folder with CR2 files it will 'shoot'")
    ap.add_argument("--vendor", type=Path, default=None, help="folder with Canon EDSDK (default vendor/edsdk)")
    args = ap.parse_args(argv)

    from PySide6.QtWidgets import QApplication

    from .ui.controller import CameraController
    from .ui import theme
    from .ui.main_window import MainWindow

    if args.mock is not None:
        from .camera import MockCamera

        src = Path(args.mock) if args.mock else None
        factory = lambda: MockCamera(src, latency=0.2)  # noqa: E731
    else:
        from .camera.edsdk import EdsdkCamera

        factory = lambda: EdsdkCamera(args.vendor)  # noqa: E731

    app = QApplication(sys.argv[:1])
    theme.apply(app)
    win = MainWindow(CameraController(factory))
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
