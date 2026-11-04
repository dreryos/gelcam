"""Spuštění: `uv run python -m gelcam` (foťák přes EDSDK) nebo `--mock` (simulace)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gelcam")
    ap.add_argument("--mock", nargs="?", const="", metavar="SLOŽKA_S_CR2",
                    help="simulovaný foťák; volitelně složka s CR2, které bude 'fotit'")
    ap.add_argument("--vendor", type=Path, default=None, help="složka s Canon EDSDK (výchozí vendor/edsdk)")
    args = ap.parse_args(argv)

    from PySide6.QtWidgets import QApplication

    from .ui.controller import CameraController
    from .ui.main_window import MainWindow

    if args.mock is not None:
        from .camera import MockCamera

        src = Path(args.mock) if args.mock else None
        factory = lambda: MockCamera(src, latency=0.2)  # noqa: E731
    else:
        from .camera.edsdk import EdsdkCamera

        factory = lambda: EdsdkCamera(args.vendor)  # noqa: E731

    app = QApplication(sys.argv[:1])
    win = MainWindow(CameraController(factory))
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
