"""Render screenshots of the real application for the README.

    uv run python tools/screenshots.py [--out docs/screenshots]

Runs the actual Qt windows over MockCamera offscreen, so the images are the
application as it is, not a mockup. Re-run after any UI change.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def wait(app, cond, timeout: float = 15.0) -> bool:
    end = time.monotonic() + timeout
    while not cond():
        app.processEvents()
        if time.monotonic() > end:
            return False
        time.sleep(0.01)
    return True


def grab(widget, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(path))
    print(f"  {path}  {path.stat().st_size / 1024:.0f} kB")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="screenshots")
    ap.add_argument("--out", type=Path, default=Path("docs/screenshots"))
    args = ap.parse_args(argv)

    from PySide6.QtWidgets import QApplication

    from gelcam.camera import MockCamera
    from gelcam.ui import theme
    from gelcam.ui.controller import CameraController
    from gelcam.ui.main_window import MainWindow
    from gelcam.ui.wizard import GelWizard

    app = QApplication.instance() or QApplication(sys.argv[:1])
    theme.apply(app)
    shots = Path(args.out)
    tmp = Path(".screenshots-tmp")
    tmp.mkdir(exist_ok=True)

    print("Live view window")
    win = MainWindow(CameraController(lambda: MockCamera(seed=3)))
    win.out_dir = tmp
    win.resize(1280, 800)
    win.show()
    wait(app, lambda: win._frame is not None)
    for _ in range(40):          # let the histogram and sharpness settle
        app.processEvents()
        time.sleep(0.02)
    grab(win, shots / "live-view.png")

    print("No camera")
    nocam = MainWindow(CameraController(lambda: MockCamera(seed=3, available=False)))
    nocam.resize(1280, 800)
    nocam.show()
    wait(app, lambda: nocam.stack.currentIndex() != 0, timeout=8.0)
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)
    grab(nocam, shots / "no-camera.png")
    nocam.close()

    print("Capture wizard")
    cams: list = []

    def factory():
        cams.append(MockCamera(seed=1))
        return cams[-1]

    ctrl = CameraController(factory)
    ctrl.connect_camera()
    wait(app, lambda: bool(cams) and cams[0].is_connected)
    ctrl.set_live_view(True)
    wait(app, lambda: ctrl.live)
    wiz = GelWizard(ctrl, tmp, "white")
    wiz.resize(960, 640)
    wiz.show()
    for page, name in [(0, "wizard-profile"), (2, "wizard-focus"), (5, "wizard-series")]:
        wiz._goto(page)
        if page == 2:
            # the mock upscales its live view, so 10x would be a blocky crop
            wiz._set_mag(1)
        for _ in range(30):
            app.processEvents()
            time.sleep(0.02)
        grab(wiz, shots / f"{name}.png")
    wiz.close()
    win.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
