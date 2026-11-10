"""Window over MockCamera: connection, live view, setting a value and an image (without a display)."""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gelcam.camera import MockCamera, Prop  # noqa: E402
from gelcam.ui.controller import CameraController  # noqa: E402
from gelcam.ui.main_window import MainWindow  # noqa: E402


def _wait(app, cond, timeout=5.0):
    end = time.monotonic() + timeout
    while not cond():
        app.processEvents()
        if time.monotonic() > end:
            return False
        time.sleep(0.01)
    return True


def test_main_window_with_mock(tmp_path):
    app = QApplication.instance() or QApplication([])
    cams = []

    def factory():
        cams.append(MockCamera(seed=2))
        return cams[-1]

    win = MainWindow(CameraController(factory))
    win.out_dir = tmp_path
    errors = []
    win.ctrl.error.connect(errors.append)

    win.btn_connect.click()
    assert _wait(app, lambda: win.combos[Prop.ISO].count() > 0)

    iso = win.combos[Prop.ISO]
    iso.setCurrentIndex(iso.count() - 1)
    assert _wait(app, lambda: cams[0]._values[Prop.ISO] == iso.currentData())

    win.btn_live.setChecked(True)
    assert _wait(app, lambda: win.view.pixmap() is not None and not win.view.pixmap().isNull())

    win.btn_af.click()
    win.btn_capture.click()
    assert _wait(app, lambda: any(tmp_path.iterdir()))
    assert errors == []
    win.close()
