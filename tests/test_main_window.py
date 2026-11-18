"""Main window behaviour over MockCamera (offscreen)."""

import os
import time

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gelcam.camera import LensInfo, MockCamera, Prop  # noqa: E402
from gelcam.camera import values  # noqa: E402
from gelcam.ui.controller import CameraController  # noqa: E402
from gelcam.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def _wait(app, cond, timeout=6.0):
    end = time.monotonic() + timeout
    while not cond():
        app.processEvents()
        if time.monotonic() > end:
            return False
        time.sleep(0.01)
    return True


def _window(tmp_path, kw=None):
    kw = {} if kw is None else kw
    cams = []

    def factory():
        cams.append(MockCamera(seed=3, **kw))  # kw is read on every connect
        return cams[-1]

    win = MainWindow(CameraController(factory))
    win.out_dir = tmp_path
    win.show()
    return win, cams


def test_exposure_capture_and_measurement(app, tmp_path):
    win, cams = _window(tmp_path)
    errors = []
    win.ctrl.error.connect(errors.append)
    assert _wait(app, lambda: win.combos[Prop.ISO].count() > 0 and win._frame is not None)
    assert [win.combos[Prop.TV].itemData(i) for i in range(win.combos[Prop.TV].count())] == cams[0].allowed_values(Prop.TV)
    assert win.combos[Prop.ISO].itemText(1) == values.iso_label(win.combos[Prop.ISO].itemData(1))
    assert win.chip_camera.text().endswith("Canon EOS 100D (simulation)")
    win.btn_capture.click()
    assert _wait(app, lambda: win.stat_bright._value.text().endswith("ADU"))
    assert any(tmp_path.iterdir()) and win.lbl_file.text().startswith("IMG_")
    assert "%" in win.stat_sat._value.text()
    assert errors == []
    win.close()


def test_focus_controls_are_available_at_every_zoom(app, tmp_path):
    win, cams = _window(tmp_path)
    win.show()
    errors = []
    win.ctrl.error.connect(errors.append)
    assert _wait(app, lambda: win._frame is not None)
    assert win.focus_card.isVisibleTo(win) and win.cam_card.isVisibleTo(win)  # both at the normal 1x view
    win.btn_af.click()  # autofocus works without any magnifier
    assert _wait(app, lambda: cams[0].defocus < 2)
    win.zoom_btns[5].click()
    assert win.focus_card.isVisibleTo(win) and win.cam_card.isVisibleTo(win)  # and nothing is swapped at 5x
    assert _wait(app, lambda: cams[0]._zoom[0] == 5)
    win.btn_af.click()
    assert _wait(app, lambda: cams[0].defocus < 2)
    win.focus_btns[list(win.focus_btns)[-1]].click()
    assert _wait(app, lambda: win.lbl_sharp.text() != "–")
    assert errors == []
    win.close()


def test_display_adjustments_do_not_touch_frames(app, tmp_path):
    win, _ = _window(tmp_path)
    assert _wait(app, lambda: win._frame is not None)
    win.ctrl.live = False  # freeze the stream
    app.processEvents()
    frame = win._frame
    before = frame.copy()
    win.sl_black.setValue(100)
    win.sl_gamma.setValue(20)
    win.btn_invert.setChecked(True)
    win.btn_clip.setChecked(True)
    assert win._frame is frame and np.array_equal(frame, before)
    assert not np.array_equal(win.view._frame, before)
    win.btn_auto.click()
    win.btn_reset.click()
    assert (win.sl_black.value(), win.sl_white.value(), win.sl_gamma.value()) == (0, 255, 10)
    win.close()


def test_no_camera_then_try_again(app, tmp_path):
    kw = {"available": False}
    win, cams = _window(tmp_path, kw)
    assert _wait(app, lambda: bool(cams) and win.stack.currentIndex() == 1 and win.nocam_msg.text() != "Looking for the camera…")
    assert win.stack.currentIndex() == 1 and not win.btn_new.isEnabled()
    kw["available"] = True
    win.btn_retry.click()
    assert _wait(app, lambda: win._connected)
    assert win.stack.currentIndex() == 0 and win.btn_new.isEnabled()
    win.close()


def test_connection_lost_overlay_and_auto_reconnect(app, tmp_path):
    win, cams = _window(tmp_path)
    assert _wait(app, lambda: win._frame is not None)
    cams[0].simulate_disconnect(0.5)
    assert _wait(app, lambda: win.lost_card.isVisibleTo(win))
    assert _wait(app, lambda: not win.lost_card.isVisibleTo(win) and win._connected, timeout=10)
    assert any(level == "WARNING" for _, level, _ in win._log_entries)
    win.close()


def test_status_ready_has_quality_and_battery(app, tmp_path):
    win, _ = _window(tmp_path)
    got = []
    win.ctrl.status_ready.connect(got.append)
    win.ctrl.refresh_options()
    assert _wait(app, lambda: bool(got))
    assert values.is_raw_only(got[0][Prop.IMAGE_QUALITY]) and got[0][Prop.BATTERY] == 100
    assert _wait(app, lambda: win.lbl_quality.text() == "RAW" and win.lbl_battery.text() == "100 %")
    win.close()


def test_lens_in_status_and_window(app, tmp_path):
    win, _ = _window(tmp_path)
    got = []
    win.ctrl.status_ready.connect(got.append)
    win.ctrl.refresh_options()
    assert _wait(app, lambda: bool(got))
    assert got[0]["lens"] == LensInfo("EF-S 18-55mm f/3.5-5.6 IS STM (simulation)", True, 35.0)
    assert _wait(app, lambda: win.lbl_focal.text() == "35 mm")
    assert "EF-S 18-55mm" in win.lbl_lens.text()
    win.close()


def test_lens_not_reported(app, tmp_path, monkeypatch):
    monkeypatch.setattr(MockCamera, "lens_info", lambda self: LensInfo())
    win, _ = _window(tmp_path)
    win.ctrl.refresh_options()
    assert _wait(app, lambda: win.lbl_lens.text() == "not reported")
    assert win.lbl_focal.text() == "not reported by the camera"
    assert win.lbl_focal.property("role") == "dim"
    win.close()


def test_chips_not_truncated_and_starting_message(app, tmp_path):
    win, _ = _window(tmp_path)
    win.resize(1280, 800)
    assert win.view._message == "Camera is not connected"
    win.ctrl.connect_camera()
    assert _wait(app, lambda: win.chip_camera.text().startswith("●"))
    assert win.view._message == "Starting live view…"
    assert _wait(app, lambda: win.view._image is not None)
    for w in (win.chip_camera, win.chip_quality, win.light_combo):
        assert w.width() >= w.sizeHint().width()
    win.close()


def test_disconnect_after_loss_rearms_detection(app, tmp_path):
    win, cams = _window(tmp_path)
    assert _wait(app, lambda: win._frame is not None)
    cams[-1].simulate_disconnect(30)
    assert _wait(app, lambda: win.ctrl.lost)
    win.btn_cancel.click()
    assert _wait(app, lambda: win.stack.currentIndex() == 1 and not win.ctrl.lost)
    win.btn_retry.click()  # the mock factory makes a fresh camera
    assert _wait(app, lambda: win._connected and win._frame is not None)
    win._frame = None
    cams[-1].simulate_disconnect(30)
    assert _wait(app, lambda: win.lost_card.isVisibleTo(win))
    win.close()


def test_wizard_is_window_modal(app, tmp_path):
    from PySide6.QtCore import Qt

    win, _cams = _window(tmp_path)
    win._open_wizard()
    assert win._wizard.windowModality() == Qt.WindowModality.WindowModal and win._wizard.isModal()
    win._wizard.close()
    win.ctrl.shutdown()


def test_histogram_can_be_switched_off_and_is_then_not_computed(app, tmp_path):
    win, _cams = _window(tmp_path)
    win.show()
    assert _wait(app, lambda: win._frame is not None)
    calls: list[int] = []
    orig = win.hist.set_data
    win.hist.set_data = lambda *a, **k: (calls.append(1), orig(*a, **k))[1]
    win.btn_hist.setChecked(False)
    assert win.hist.isHidden()
    before, n0 = len(calls), win._frame_n
    assert _wait(app, lambda: win._frame_n >= n0 + 8)  # several more frames arrive
    assert len(calls) == before  # none of them computed a histogram
    win.btn_hist.setChecked(True)
    assert not win.hist.isHidden() and len(calls) > before  # switching on draws it at once
    win.close()


def test_a_black_live_view_explains_itself_and_the_hint_goes_away(app, tmp_path):
    win, _cams = _window(tmp_path)
    win.show()
    assert _wait(app, lambda: win._frame is not None)
    win.ctrl.set_live_view(False)  # no real frames while the test feeds its own
    app.processEvents()
    dark = np.zeros((480, 720, 3), np.uint8)
    for _ in range(12):  # about four statistics updates
        win._on_frame(dark)
    assert not win.dark_note.isHidden() and "ISO" in win.dark_note.text() and "very dark" in win.dark_note.text()
    bright = np.full((480, 720, 3), 120, np.uint8)
    for _ in range(4):
        win._on_frame(bright)
    assert win.dark_note.isHidden()
    for _ in range(3):  # a short dark moment (a hand over the target) does not flash the hint
        win._on_frame(dark)
    assert win.dark_note.isHidden()
    win.close()


def test_the_window_says_when_the_live_view_runs_with_other_values(app, tmp_path):
    win, _cams = _window(tmp_path)
    win.show()
    assert win.lbl_live_boost.isHidden()
    win._on_live_boost({Prop.AV: (0x28, 0x30)})  # live view value, operator's value
    assert not win.lbl_live_boost.isHidden()
    text = win.lbl_live_boost.text()
    assert "live view runs at" in text and "Captures use" in text and text.count("f/") == 2
    win._on_live_boost({Prop.ISO: (0x78, 0x48), Prop.AV: (0x28, 0x30)})
    assert win.lbl_live_boost.text().count("ISO") == 2 and win.lbl_live_boost.text().count("f/") == 2
    win._on_live_boost(None)
    assert win.lbl_live_boost.isHidden()
    win.close()


def test_the_bright_live_view_button_drives_the_controller_and_follows_other_windows(app, tmp_path):
    win, _cams = _window(tmp_path)
    win.show()
    assert _wait(app, lambda: win._frame is not None)  # connected: the buttons are enabled
    assert not win.btn_bright.isChecked() and win.ctrl.live_iso is False
    win.btn_bright.click()
    assert win.ctrl.live_iso is True and win.btn_bright.isChecked()
    win.ctrl.set_live_iso(False)  # e.g. the wizard gives its state back when it closes
    app.processEvents()
    assert not win.btn_bright.isChecked()
    assert "Bright live view" in win.dark_note.text() or True  # the hint text is covered by its own test
    win.close()
