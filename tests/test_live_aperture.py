"""The live view runs at a wide aperture (f/5.6 or the widest); every capture uses the operator's aperture."""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gelcam.camera import MockCamera, Prop  # noqa: E402
from gelcam.camera.values import av_fnumber  # noqa: E402
from gelcam.ui.controller import CameraController  # noqa: E402


def _wait(cond, timeout=10.0):
    app = QApplication.instance() or QApplication([])
    end = time.monotonic() + timeout
    while not cond():
        app.processEvents()
        if time.monotonic() > end:
            return False
        time.sleep(0.01)
    return True


@pytest.fixture
def env(tmp_path):
    QApplication.instance() or QApplication([])
    cams: list[MockCamera] = []
    ctrl = CameraController(lambda: cams.append(MockCamera(seed=1)) or cams[-1])
    ctrl.MAGNIFIER_SETTLE = 0.01
    changes: list = []
    ctrl.live_aperture_changed.connect(changes.append)
    ctrl.connect_camera()
    assert _wait(lambda: bool(cams) and cams[0].is_connected)
    cam = cams[0]
    allowed = cam.allowed_values(Prop.AV)
    f8 = next(c for c in allowed if abs(av_fnumber(c) - 8.0) < 0.05)
    cam.set(Prop.AV, f8)  # the operator's aperture
    yield ctrl, cam, f8, changes, tmp_path
    ctrl.shutdown()


def _f56(cam):
    return next(c for c in cam.allowed_values(Prop.AV) if abs(av_fnumber(c) - 5.6) < 0.05)


def _idle(ctrl):
    assert _wait(lambda: ctrl._pool._work_queue.empty())
    time.sleep(0.15)


def test_the_live_view_opens_the_aperture_and_giving_it_back_restores_it(env):
    ctrl, cam, f8, changes, _ = env
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live and cam.get(Prop.AV) == _f56(cam))
    assert _wait(lambda: bool(changes) and changes[-1] == (_f56(cam), f8))  # the window is told
    assert ctrl._capture_av == f8
    ctrl.set_live_view(False)
    assert _wait(lambda: not ctrl.live and cam.get(Prop.AV) == f8)
    assert ctrl._capture_av is None
    assert _wait(lambda: changes[-1] is None)


def test_every_capture_is_taken_at_the_operators_aperture(env):
    ctrl, cam, f8, _changes, tmp = env
    seen: list[int] = []
    orig = cam.capture
    cam.capture = lambda dest: (seen.append(int(cam.get(Prop.AV))), orig(dest))[1]
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live and cam.get(Prop.AV) == _f56(cam))
    ctrl.capture(tmp)
    assert _wait(lambda: bool(seen))
    assert seen == [f8]  # the picture is taken at f/8 ...
    assert _wait(lambda: cam.get(Prop.AV) == _f56(cam))  # ... and the live view is wide open again
    _idle(ctrl)
    assert ctrl._capture_av == f8


def test_choosing_an_aperture_during_live_view_is_kept_for_the_captures(env):
    ctrl, cam, f8, changes, tmp = env
    f11 = next(c for c in cam.allowed_values(Prop.AV) if abs(av_fnumber(c) - 11.0) < 0.05)
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live and cam.get(Prop.AV) == _f56(cam))
    ctrl.set_value(Prop.AV, f11)
    assert _wait(lambda: ctrl._capture_av == f11)
    assert cam.get(Prop.AV) == _f56(cam)  # the live view stays wide open
    assert _wait(lambda: changes[-1] == (_f56(cam), f11))
    opts = {}
    ctrl.options_ready.connect(lambda o: opts.update(o))
    ctrl.refresh_options()
    assert _wait(lambda: Prop.AV in opts)
    assert opts[Prop.AV][1] == f11  # the window shows the operator's aperture, not the live view's
    seen = []
    orig = cam.capture
    cam.capture = lambda dest: (seen.append(int(cam.get(Prop.AV))), orig(dest))[1]
    ctrl.capture(tmp)
    assert _wait(lambda: bool(seen))
    assert seen == [f11]
    _idle(ctrl)
    ctrl.set_live_view(False)
    assert _wait(lambda: cam.get(Prop.AV) == f11)  # what was chosen stays after the live view


def test_a_value_the_camera_does_not_offer_is_refused(env):
    ctrl, cam, _f8, _changes, _ = env
    errors: list[str] = []
    ctrl.error.connect(errors.append)
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live and ctrl._capture_av is not None)
    before = ctrl._capture_av
    ctrl.set_value(Prop.AV, 0x7F)  # not in the camera's list
    assert _wait(lambda: bool(errors))
    assert ctrl._capture_av == before


def test_the_setting_can_switch_it_off(env):
    ctrl, cam, f8, changes, _ = env
    ctrl.live_aperture = False
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live)
    _idle(ctrl)
    assert cam.get(Prop.AV) == f8 and ctrl._capture_av is None and changes == []


def test_an_aperture_that_is_already_the_widest_changes_nothing(env):
    ctrl, cam, _f8, changes, _ = env
    cam.set(Prop.AV, _f56(cam))
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live)
    _idle(ctrl)
    assert ctrl._capture_av is None and changes == []


def test_f56_is_preferred_and_the_widest_is_the_fallback(env):
    ctrl, cam, _f8, _changes, _ = env
    assert ctrl._widest_av(cam) == _f56(cam)

    class Narrow(MockCamera):
        def allowed_values(self, prop):
            return [c for c in super().allowed_values(prop) if av_fnumber(c) >= 8.0] if prop is Prop.AV else super().allowed_values(prop)

    narrow = Narrow()
    narrow.connect()
    widest = ctrl._widest_av(narrow)
    assert abs(av_fnumber(widest) - 8.0) < 0.05  # f/5.6 is not offered: the lowest f-number there is


def test_disconnecting_with_the_live_view_open_gives_the_aperture_back(env):
    ctrl, cam, f8, _changes, _ = env
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live and cam.get(Prop.AV) == _f56(cam))
    ctrl.disconnect_camera()
    assert _wait(lambda: not cam.is_connected)
    assert ctrl._capture_av is None


def test_the_operators_aperture_survives_a_lost_connection(env):
    ctrl, cam, f8, _changes, tmp = env
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live and ctrl._capture_av == f8)
    cam.simulate_disconnect(0.8)

    def noticed() -> bool:
        ctrl.request_frame()  # the window's timer asks for frames; that is how a lost camera is noticed
        return ctrl.lost

    assert _wait(noticed, 10)
    for _ in range(40):  # what the window does: try again until the camera is back
        ctrl.reconnect()
        if _wait(lambda: not ctrl.lost, 0.5):
            break
    assert not ctrl.lost
    assert _wait(lambda: ctrl.live and cam.get(Prop.AV) == _f56(cam), 10)
    assert ctrl._capture_av == f8  # still remembered: the next capture goes back to f/8
