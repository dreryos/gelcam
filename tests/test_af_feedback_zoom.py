"""Autofocus feedback is measured, not assumed; unsupported magnifier steps are not offered."""

import os
import time

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gelcam.camera import CameraError, MockCamera  # noqa: E402
from gelcam.camera.edsdk import EdsdkCamera  # noqa: E402
from gelcam.ui.controller import CameraController  # noqa: E402
from gelcam.ui.main_window import MainWindow  # noqa: E402


def _wait(cond, timeout=8.0):
    app = QApplication.instance()
    end = time.monotonic() + timeout
    while not cond():
        app.processEvents()
        if time.monotonic() > end:
            return False
        time.sleep(0.01)
    return True


class CleanMock(MockCamera):
    """Noise-free live view whose sharpness really depends on the (simulated) defocus."""

    def live_view_frame(self):
        if not self._live:
            return None
        img = self._blurred(self._signal, self._defocus)
        g = np.clip(img / img.max() * 255, 0, 255).astype(np.uint8)
        return np.stack([g, g, g], axis=-1)


class StuckLens(CleanMock):
    """AF command is accepted but the lens never moves (AF/MF switch on MF)."""

    def autofocus(self) -> None:
        self._require()


def _run_af(cam_factory) -> list[str]:
    ctrl = CameraController(cam_factory)
    msgs: list[str] = []
    ctrl.message.connect(msgs.append)
    errors: list[str] = []
    ctrl.error.connect(errors.append)
    ctrl.connect_camera()
    assert _wait(lambda: ctrl._camera is not None)
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live)
    msgs.clear()
    ctrl.autofocus()
    assert _wait(lambda: any("utofocus" in m or "Focused" in m for m in msgs))
    ctrl.shutdown()
    assert not errors
    return msgs


def test_af_success_reports_measured_sharpness():
    msgs = _run_af(lambda: CleanMock(seed=3))
    assert any(m.startswith("Focused: sharpness") and "→" in m for m in msgs)


def test_af_that_changes_nothing_is_not_reported_as_success():
    msgs = _run_af(lambda: StuckLens(seed=3))
    af = [m for m in msgs if "utofocus" in m or "Focused" in m]
    assert af and not af[0].startswith("Focused")
    assert "unchanged" in af[0] and "AF" in af[0]


def test_edsdk_camera_offers_no_distinct_10x():
    assert EdsdkCamera.live_view_zooms == (1, 5)
    with pytest.raises(CameraError):
        EdsdkCamera().set_live_view_zoom(10)  # rejected before any SDK call
    assert MockCamera.live_view_zooms == (1, 5, 10)


def test_window_hides_unsupported_zoom_steps():
    win = MainWindow(CameraController(lambda: MockCamera(seed=1)))
    win.show()
    win._on_status({"zooms": (1, 5)})
    assert not win.zoom_btns[10].isVisible() and win.zoom_btns[5].isVisible()
    win.zoom_btns[10].setChecked(True)
    win._on_status({"zooms": (1, 5)})  # selected step vanished -> back to 1x
    assert win.zoom_group.checkedId() == 1
    win._on_status({"zooms": (1, 5, 10)})
    assert win.zoom_btns[10].isVisible()
    win.close()
    win.ctrl.shutdown()
