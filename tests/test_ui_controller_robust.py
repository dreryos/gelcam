"""Controller: connect failure, connection loss + reconnect, off-thread measurement."""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gelcam.camera import MockCamera  # noqa: E402
from gelcam.ui.controller import CameraController  # noqa: E402


def _wait(app, cond, timeout=5.0):
    end = time.monotonic() + timeout
    while not cond():
        app.processEvents()
        if time.monotonic() > end:
            return False
        time.sleep(0.01)
    return True


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_connect_failed(app):
    ctrl = CameraController(lambda: MockCamera(available=False))
    failed, errors = [], []
    ctrl.connect_failed.connect(failed.append)
    ctrl.error.connect(errors.append)
    ctrl.connect_camera()
    assert _wait(app, lambda: failed)
    assert "No camera found" in failed[0] and not errors and ctrl._camera is None
    ctrl.shutdown()


def test_loss_and_reconnect(app):
    cams = []
    ctrl = CameraController(lambda: cams.append(MockCamera(seed=1)) or cams[-1])
    lost, back, errors, frames = [], [], [], []
    ctrl.connection_lost.connect(lambda: lost.append(1))
    ctrl.reconnected.connect(back.append)
    ctrl.error.connect(errors.append)
    ctrl.frame_ready.connect(frames.append)
    ctrl.connect_camera()
    assert _wait(app, lambda: cams and cams[0].is_connected)
    ctrl.set_live_view(True)
    assert _wait(app, lambda: ctrl.live)
    cams[0].simulate_disconnect(0.3)
    assert _wait(app, lambda: (ctrl.request_frame(), lost)[1])
    assert _wait(app, lambda: not ctrl.live)
    time.sleep(0.1)
    app.processEvents()
    assert lost == [1] and errors == []
    time.sleep(0.3)
    ctrl.reconnect()
    assert _wait(app, lambda: back)
    assert not ctrl.lost
    assert _wait(app, lambda: ctrl.live)
    frames.clear()
    assert _wait(app, lambda: (ctrl.request_frame(), frames)[1])
    ctrl.shutdown()


def test_measure_file(app, tmp_path):
    cam = MockCamera(seed=1)
    cam.connect()
    path = cam.capture(tmp_path)
    ctrl = CameraController(lambda: cam)
    got = []
    ctrl.measured.connect(lambda p, m: got.append((p, m)))
    ctrl.measure_file(path, "R")
    assert _wait(app, lambda: got)
    assert got[0][0] == path and got[0][1].fraction > 0
    ctrl.shutdown()
