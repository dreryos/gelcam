"""Run with: `uv run python -m gelcam` (camera via EDSDK) or `--mock` (simulation).

Packaged build: `GelCam.exe` (windowed) and `GelCam-console.exe` (same program with a console, for
`--selftest` and diagnostics).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    raw_args = sys.argv[1:] if argv is None else argv
    if raw_args[:1] == ["--bench"]:  # speed and memory report of this PC (see gelcam/bench.py)
        from .bench import main as bench_main

        return bench_main(raw_args[1:])
    ap = argparse.ArgumentParser(prog="gelcam")
    ap.add_argument("--mock", nargs="?", const="", metavar="FOLDER_WITH_CR2",
                    help="simulated camera; optionally a folder with CR2 files it will 'shoot'")
    ap.add_argument("--vendor", type=Path, default=None, help="folder with Canon EDSDK (default vendor/edsdk)")
    ap.add_argument("--lang", metavar="CODE", help="interface language, e.g. en or cs (default: GELCAM_LANG, "
                                                   "then the system language if a translation exists)")
    ap.add_argument("--selftest", action="store_true",
                    help="check that this installation works (libraries, window, EDSDK DLL) and exit")
    ap.add_argument("--camera", action="store_true", help="with --selftest: also connect to the real camera")
    ap.add_argument("--version", action="store_true", help="print the version and exit")
    args = ap.parse_args(argv)

    from . import __version__, runtime

    if args.version:
        print(__version__)
        return 0
    log_file = runtime.setup_logging()
    if args.selftest:
        return runtime.selftest(check_camera=args.camera)

    from PySide6.QtWidgets import QApplication, QMessageBox

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
    runtime.install_excepthook(lambda title, text: QMessageBox.critical(None, title, text))
    from PySide6.QtCore import QLocale

    runtime.install_translator(app, runtime.choose_language(args.lang, QLocale.system().name()))
    theme.apply(app)
    win = MainWindow(CameraController(factory))
    win.show()
    if log_file is not None:
        import logging

        logging.getLogger("gelcam").info("Main window shown; log file %s", log_file)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
