"""The live view runs with other values than the captures: a wide aperture (f/5.6 or the widest) and, on request,
a high ISO ("bright live view"). Every capture uses the operator's values."""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gelcam.camera import MockCamera, Prop  # noqa: E402
from gelcam.camera.values import av_fnumber, iso_value  # noqa: E402
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


def _av(cam, f):
    return next(c for c in cam.allowed_values(Prop.AV) if abs(av_fnumber(c) - f) < 0.05)


def _iso(cam, value):
    return next(c for c in cam.allowed_values(Prop.ISO) if iso_value(c) == value)


@pytest.fixture
def env(tmp_path):
    QApplication.instance() or QApplication([])
    cams: list[MockCamera] = []
    ctrl = CameraController(lambda: cams.append(MockCamera(seed=1)) or cams[-1])
    ctrl.MAGNIFIER_SETTLE = 0.01
    changes: list = []
    ctrl.live_boost_changed.connect(changes.append)
    ctrl.connect_camera()
    assert _wait(lambda: bool(cams) and cams[0].is_connected)
    cam = cams[0]
    cam.set(Prop.AV, _av(cam, 8.0))  # the operator's aperture
    cam.set(Prop.ISO, _iso(cam, 100))  # and ISO
    yield ctrl, cam, changes, tmp_path
    ctrl.shutdown()


def _idle(ctrl):
    assert _wait(lambda: ctrl._pool._work_queue.empty())
    time.sleep(0.15)


# ------------------------------------------------------------------------------------------- aperture
def test_the_live_view_opens_the_aperture_and_giving_it_back_restores_it(env):
    ctrl, cam, changes, _ = env
    f8, f56 = _av(cam, 8.0), _av(cam, 5.6)
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live and cam.get(Prop.AV) == f56)
    assert _wait(lambda: bool(changes) and changes[-1] == {Prop.AV: (f56, f8)})  # the window is told
    assert ctrl._operator == {Prop.AV: f8}
    ctrl.set_live_view(False)
    assert _wait(lambda: not ctrl.live and cam.get(Prop.AV) == f8)
    assert ctrl._operator == {}
    assert _wait(lambda: changes[-1] is None)


def test_every_capture_is_taken_at_the_operators_aperture(env):
    ctrl, cam, _changes, tmp = env
    f8, f56 = _av(cam, 8.0), _av(cam, 5.6)
    seen: list[int] = []
    orig = cam.capture
    cam.capture = lambda dest: (seen.append(int(cam.get(Prop.AV))), orig(dest))[1]
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live and cam.get(Prop.AV) == f56)
    ctrl.capture(tmp)
    assert _wait(lambda: bool(seen))
    assert seen == [f8]  # the picture is taken at f/8 ...
    assert _wait(lambda: cam.get(Prop.AV) == f56)  # ... and the live view is wide open again
    _idle(ctrl)
    assert ctrl._operator == {Prop.AV: f8}


def test_choosing_an_aperture_during_live_view_is_kept_for_the_captures(env):
    ctrl, cam, changes, tmp = env
    f56, f11 = _av(cam, 5.6), _av(cam, 11.0)
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live and cam.get(Prop.AV) == f56)
    ctrl.set_value(Prop.AV, f11)
    assert _wait(lambda: ctrl._operator.get(Prop.AV) == f11)
    assert cam.get(Prop.AV) == f56  # the live view stays wide open
    assert _wait(lambda: changes[-1] == {Prop.AV: (f56, f11)})
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
    ctrl, cam, _changes, _ = env
    errors: list[str] = []
    ctrl.error.connect(errors.append)
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live and Prop.AV in ctrl._operator)
    before = dict(ctrl._operator)
    ctrl.set_value(Prop.AV, 0x7F)  # not in the camera's list
    assert _wait(lambda: bool(errors))
    assert ctrl._operator == before


def test_the_aperture_setting_can_switch_it_off(env):
    ctrl, cam, changes, _ = env
    ctrl.live_aperture = False
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live)
    _idle(ctrl)
    assert cam.get(Prop.AV) == _av(cam, 8.0) and ctrl._operator == {} and changes == []


def test_an_aperture_that_is_already_the_widest_changes_nothing(env):
    ctrl, cam, changes, _ = env
    cam.set(Prop.AV, _av(cam, 5.6))
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live)
    _idle(ctrl)
    assert ctrl._operator == {} and changes == []


def test_f56_is_preferred_and_the_widest_is_the_fallback(env):
    ctrl, cam, _changes, _ = env
    assert ctrl._widest_av(cam) == _av(cam, 5.6)

    class Narrow(MockCamera):
        def allowed_values(self, prop):
            allowed = super().allowed_values(prop)
            return [c for c in allowed if av_fnumber(c) >= 8.0] if prop is Prop.AV else allowed

    narrow = Narrow()
    narrow.connect()
    assert abs(av_fnumber(ctrl._widest_av(narrow)) - 8.0) < 0.05  # f/5.6 is not offered: the lowest f-number there is


def test_switching_the_aperture_setting_while_the_live_view_runs_takes_effect_at_once(env):
    ctrl, cam, _changes, _ = env
    f8, f56 = _av(cam, 8.0), _av(cam, 5.6)
    ctrl.live_aperture = False
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live)
    _idle(ctrl)
    ctrl.set_live_aperture(True)
    assert _wait(lambda: cam.get(Prop.AV) == f56)
    ctrl.set_live_aperture(False)
    assert _wait(lambda: cam.get(Prop.AV) == f8)
    assert ctrl._operator == {}


def test_disconnecting_with_the_live_view_open_gives_the_values_back(env):
    ctrl, cam, _changes, _ = env
    f8, iso100 = _av(cam, 8.0), _iso(cam, 100)
    ctrl.set_live_iso(True)
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live and len(ctrl._operator) == 2)
    ctrl.disconnect_camera()
    assert _wait(lambda: not cam.is_connected)
    assert ctrl._operator == {}
    assert cam._values[Prop.AV] == f8 and cam._values[Prop.ISO] == iso100  # given back before the disconnect


def test_the_operators_aperture_survives_a_lost_connection(env):
    ctrl, cam, _changes, _ = env
    f8, f56 = _av(cam, 8.0), _av(cam, 5.6)
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live and ctrl._operator.get(Prop.AV) == f8)
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
    assert _wait(lambda: ctrl.live and cam.get(Prop.AV) == f56, 10)
    assert ctrl._operator.get(Prop.AV) == f8  # still remembered: the next capture goes back to f/8


# ------------------------------------------------------------------------------------------- bright live view (ISO)
def test_bright_live_view_raises_the_iso_for_the_live_view_only(env):
    ctrl, cam, changes, tmp = env
    iso100, iso6400 = _iso(cam, 100), _iso(cam, 6400)
    flags: list[bool] = []
    ctrl.live_iso_flag_changed.connect(flags.append)
    ctrl.live_aperture = False
    ctrl.set_live_iso(True)
    assert _wait(lambda: flags == [True])
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live and cam.get(Prop.ISO) == iso6400)
    assert _wait(lambda: bool(changes) and changes[-1] == {Prop.ISO: (iso6400, iso100)})
    seen: list[int] = []
    orig = cam.capture
    cam.capture = lambda dest: (seen.append(int(cam.get(Prop.ISO))), orig(dest))[1]
    ctrl.capture(tmp)
    assert _wait(lambda: bool(seen))
    assert seen == [iso100]  # the picture is taken with the operator's ISO
    assert _wait(lambda: cam.get(Prop.ISO) == iso6400)  # and the live view is bright again
    _idle(ctrl)
    ctrl.set_live_view(False)
    assert _wait(lambda: cam.get(Prop.ISO) == iso100)
    assert _wait(lambda: changes[-1] is None)


def test_switching_the_bright_live_view_while_it_runs(env):
    ctrl, cam, changes, _ = env
    iso100, iso6400 = _iso(cam, 100), _iso(cam, 6400)
    ctrl.live_aperture = False
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live)
    _idle(ctrl)
    assert cam.get(Prop.ISO) == iso100
    ctrl.set_live_iso(True)
    assert _wait(lambda: cam.get(Prop.ISO) == iso6400)
    ctrl.set_live_iso(False)
    assert _wait(lambda: cam.get(Prop.ISO) == iso100)
    assert ctrl._operator == {}


def test_aperture_and_iso_boost_together_and_the_window_shows_the_operators_values(env):
    ctrl, cam, changes, _ = env
    f8, f56, iso100, iso6400 = _av(cam, 8.0), _av(cam, 5.6), _iso(cam, 100), _iso(cam, 6400)
    ctrl.set_live_iso(True)
    ctrl.set_live_view(True)
    assert _wait(lambda: ctrl.live and cam.get(Prop.AV) == f56 and cam.get(Prop.ISO) == iso6400)
    assert _wait(lambda: bool(changes) and changes[-1] == {Prop.ISO: (iso6400, iso100), Prop.AV: (f56, f8)})
    opts = {}
    ctrl.options_ready.connect(lambda o: opts.update(o))
    ctrl.refresh_options()
    assert _wait(lambda: Prop.ISO in opts)
    assert opts[Prop.ISO][1] == iso100 and opts[Prop.AV][1] == f8  # what the combo boxes show
    ctrl.set_value(Prop.ISO, _iso(cam, 400))  # a choice during the live view is for the captures
    assert _wait(lambda: ctrl._operator.get(Prop.ISO) == _iso(cam, 400))
    assert cam.get(Prop.ISO) == iso6400
    ctrl.set_live_view(False)
    assert _wait(lambda: cam.get(Prop.ISO) == _iso(cam, 400) and cam.get(Prop.AV) == f8)


def test_the_bright_iso_is_the_highest_offered_up_to_6400(env):
    ctrl, cam, _changes, _ = env
    assert iso_value(ctrl._boost_iso(cam)) == 6400

    class Low(MockCamera):
        def allowed_values(self, prop):
            allowed = super().allowed_values(prop)
            return [c for c in allowed if (iso_value(c) or 0) <= 800] if prop is Prop.ISO else allowed

    low = Low()
    low.connect()
    assert iso_value(ctrl._boost_iso(low)) == 800
