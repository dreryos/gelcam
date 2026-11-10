"""Capture wizard over MockCamera: the whole walk-through, saved files and metadata (offscreen)."""

import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from gelcam.camera import MockCamera  # noqa: E402
from gelcam.ui.controller import CameraController  # noqa: E402
from gelcam.ui.wizard import GelWizard  # noqa: E402


def _wait(app, cond, timeout=20.0):
    end = time.monotonic() + timeout
    while not cond():
        app.processEvents()
        if time.monotonic() > end:
            return False
        time.sleep(0.01)
    return True


@pytest.fixture
def env(tmp_path):
    app = QApplication.instance() or QApplication([])
    cams = []

    def factory():
        cams.append(MockCamera(seed=1))
        return cams[-1]

    ctrl = CameraController(factory)
    ctrl.connect_camera()
    assert _wait(app, lambda: bool(cams) and ctrl.live is False and cams[0].is_connected)
    ctrl.set_live_view(True)
    assert _wait(app, lambda: ctrl.live)
    sent = []
    orig = ctrl.set_value
    ctrl.set_value = lambda prop, code: (sent.append((prop, code)), orig(prop, code))[1]
    assert _wait(app, lambda: ctrl.lens.name is not None)
    wiz = GelWizard(ctrl, tmp_path, "uv70")
    assert _wait(app, lambda: bool(wiz.opts))
    yield app, ctrl, cams[0], wiz, sent, tmp_path
    wiz.close()
    ctrl.shutdown()


def _series(app, wiz, n):
    wiz.frames.setCurrentIndex(wiz.frames.findData(n))
    wiz.btn_series.click()
    assert _wait(app, lambda: wiz.series_done)
    for cb in wiz.dark_checks:
        cb.setChecked(True)
    wiz.btn_darks.click()
    assert _wait(app, lambda: wiz.darks_done)


def test_full_walk(env):
    app, ctrl, cam, wiz, sent, root = env
    wiz.gel_name.setText("pcr")
    wiz.btn_next.click()  # 1 -> 2, creates the folder
    folder = wiz.folder
    assert folder is not None and folder.parent == root
    assert wiz.light_declared == "uv70"
    wiz.btn_next.click()  # -> 3 focus
    assert _wait(app, lambda: wiz.sharp_now is not None)
    wiz.btn_af.click()
    assert _wait(app, lambda: wiz.af_state == "idle" and wiz.sharp_after is not None)
    # (mock sharpness at 10x is noise-dominated, so whether the AF note shows is not asserted here)
    wiz.btn_next.click()  # -> 4 test exposure
    assert _wait(app, lambda: wiz.applied)
    wiz.btn_test.click()
    assert _wait(app, lambda: wiz.proposal_code is not None)
    assert "→" in wiz.proposal.text()
    wiz.btn_apply.click()
    wiz.btn_next.click()  # -> 5
    wiz.btn_next.click()  # -> 6
    assert not wiz.btn_next.isEnabled()
    _series(app, wiz, 4)
    assert wiz.btn_next.isEnabled()
    wiz.btn_next.click()  # -> 7
    assert wiz.btn_next.text() == "Finish"
    wiz.btn_next.click()
    assert wiz.result() == wiz.DialogCode.Accepted

    assert len([p for p in (folder / "raw").iterdir() if p.is_file()]) == 4
    assert len(list((folder / "calib").iterdir())) == 4
    assert len(list((folder / "raw" / "test").iterdir())) == 1
    meta = json.loads((folder / "metadata.json").read_text())
    assert meta["status"] == "captured; processing pending"
    assert meta["processing"] == [] and len(meta["light_frames"]) == 4 and len(meta["dark_frames"]) == 4
    assert meta["test_frames"] and meta["flat"].startswith("skipped")
    assert meta["lens"] == {"name": "EF-S 18-55mm f/3.5-5.6 IS STM (simulation)", "focal_length_mm": 35.0}
    assert wiz.focal_label.text() == "current focal length: 35 mm"
    assert not list(folder.rglob("result.tif"))  # no result.tif unless Process was clicked
    for prop, code in sent:
        assert code in cam.allowed_values(prop)


def test_back_keeps_values_and_zoom_warning(env):
    app, _ctrl, _cam, wiz, _sent, _root = env
    wiz.gel_name.setText("keep")
    wiz.note.setPlainText("ladder 100 bp")
    wiz.dye.setCurrentIndex(2)
    wiz.btn_next.click()
    wiz.checks["gel"].setChecked(True)
    wiz.show()
    assert wiz.zoom_note.isVisible()
    wiz.checks["zoom"].setChecked(True)
    assert not wiz.zoom_note.isVisible()
    wiz.checks["zoom"].setChecked(False)
    assert wiz.btn_next.isEnabled()  # a warning, not a blocker
    wiz.btn_back.click()
    assert wiz.gel_name.text() == "keep" and wiz.note.toPlainText() == "ladder 100 bp"
    assert wiz.profile.name == "SYBR Safe"
    wiz.btn_next.click()
    assert wiz.checks["gel"].isChecked() and wiz.folder is not None
    assert len(list(wiz.out_root.iterdir())) == 1  # folder created once


def test_af_failure_and_saturation_notes(env):
    from gelcam.processing.exposure import ExposureMeasurement

    _app, _ctrl, _cam, wiz, _sent, _root = env
    wiz.show()
    wiz.btn_next.click()
    wiz.btn_next.click()  # focus page
    wiz.sharp_before = 10.0
    wiz._af_measured(10.5)
    assert wiz.af_note.isVisible()
    wiz._af_measured(20.0)
    assert not wiz.af_note.isVisible()
    wiz.btn_next.click()  # test exposure page
    assert _wait(_app, lambda: wiz.applied)
    wiz._show_measurement(ExposureMeasurement(13000.0, 1.0, 0.008))
    assert wiz.sat_note.isVisible() and "0.80 %" in wiz.sat_note.text()


def test_series_interrupted_and_resumed(env, monkeypatch):
    app, ctrl, cam, wiz, _sent, _root = env
    wiz.btn_next.click()
    for _ in range(4):
        wiz.btn_next.click()
    assert wiz.idx == 5
    wiz.frames.setCurrentIndex(wiz.frames.findData(4))
    cam.simulate_disconnect(0.2)
    wiz.btn_series.click()
    assert _wait(app, lambda: wiz._box is not None and wiz._box.isVisible())
    assert "after 0 of 4" in wiz._box.text()
    resume = next(b for b in wiz._box.buttons() if b.text().startswith("Resume"))
    resume.click()
    assert _wait(app, lambda: wiz.series_done)
    assert len(wiz.light_frames) == 4


def test_late_capture_while_paused_is_kept(env):
    app, ctrl, cam, wiz, _sent, _root = env
    wiz.btn_next.click()
    dest = wiz.folder / "raw"
    dest.mkdir(exist_ok=True)
    wiz._batch = {"kind": "light", "dest": dest, "total": 3, "got": [], "paused": False, "resume": False}
    wiz._interrupt(lost=False)
    calls = []
    ctrl.capture = lambda d: calls.append(d)
    wiz._on_captured(dest / "a.CR2")  # in flight when the series was interrupted
    assert wiz._batch["got"] == [dest / "a.CR2"] and not calls
    resume = next(b for b in wiz._box.buttons() if b.text().startswith("Resume"))
    assert resume.text().endswith("2")
    resume.click()
    assert len(calls) == 1 and len(wiz._batch["got"]) == 1  # resume needs only the remaining frames
    wiz._batch["paused"] = True
    wiz._batch["total"] = 2
    wiz._on_captured(dest / "b.CR2")
    wiz._continue_batch()  # already complete: finishes instead of capturing
    assert wiz._batch is None and wiz.light_frames == [dest / "a.CR2", dest / "b.CR2"]


def test_done_restores_live_after_queued_stop(env):
    app, ctrl, cam, wiz, _sent, _root = env
    assert wiz._live_at_open
    ctrl.set_live_view(False)  # stop still queued
    wiz.done(0)
    assert _wait(app, lambda: ctrl.live and not ctrl._pool._work_queue.qsize())
    frames = []
    ctrl.frame_ready.connect(frames.append)
    assert _wait(app, lambda: (ctrl.request_frame(), bool(frames))[1])


def test_redundant_live_view_is_noop(env, monkeypatch):
    app, ctrl, cam, _wiz, _sent, _root = env
    n = []
    orig = cam.start_live_view
    monkeypatch.setattr(cam, "start_live_view", lambda: (n.append(1), orig())[1])
    ctrl.set_live_view(True)
    assert _wait(app, lambda: not ctrl._pool._work_queue.qsize())
    time.sleep(0.1)
    assert not n


def test_process_button_writes_result(env):
    app, _ctrl, _cam, wiz, _sent, _root = env
    wiz.gel_name.setText("proc")
    wiz.btn_next.click()
    folder = wiz.folder
    for _ in range(4):  # 2 -> 3 -> 4 -> 5 -> 6
        wiz.btn_next.click()
    assert _wait(app, lambda: wiz.applied)
    _series(app, wiz, 4)
    wiz.btn_next.click()  # -> 7
    wiz.btn_process.click()
    assert not wiz.btn_next.isEnabled()  # Finish waits for processing
    assert _wait(app, lambda: wiz.processed or wiz.status.isVisible(), timeout=60)
    assert wiz.processed, wiz.status.text()
    assert (folder / "result.tif").exists() and (folder / "preview.png").exists()
    assert not (folder / "work").exists()
    assert "→" in wiz.proc_stats.text() and wiz.btn_next.isEnabled()
    wiz.btn_next.click()
    assert wiz.result() == wiz.DialogCode.Accepted
    meta = json.loads((folder / "metadata.json").read_text())
    assert meta["status"] == "processed" and meta["processing"] and meta["result"] == "result.tif"


def test_profile_and_uv_frozen_after_first_frame(env):
    app, _ctrl, _cam, wiz, _sent, _root = env
    assert wiz.dye.isEnabled() and wiz.uv100.isEnabled()
    wiz.dye.setCurrentIndex(1)  # allowed before any frame
    wiz.uv100.setChecked(True)
    chosen = wiz.dye.currentData()
    for _ in range(5):  # -> step 6
        wiz.btn_next.click()
    assert _wait(app, lambda: wiz.applied)
    _series(app, wiz, 4)
    assert not wiz.dye.isEnabled() and not wiz.uv70.isEnabled() and not wiz.uv100.isEnabled()
    assert wiz.freeze_note.isHidden() is False
    wiz.dye.setEnabled(True)  # even a forced change does not reach the metadata
    wiz.dye.setCurrentIndex(0)
    wiz.uv70.setChecked(True)
    meta = wiz._metadata()
    assert meta["profile"]["name"] == chosen.name and meta["uv_level"] == 100
    assert wiz.profile is chosen
