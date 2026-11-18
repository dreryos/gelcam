"""Flat capture window over the simulated camera: exposure test, flat and dark frames, saving, interruptions."""

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from gelcam.camera import MockCamera, Prop  # noqa: E402
from gelcam.storage import flat_library as lib  # noqa: E402
from gelcam.ui.controller import CameraController  # noqa: E402
from gelcam.ui.flat_dialog import FlatDialog  # noqa: E402


def _wait(app, cond, timeout=20.0):
    end = time.monotonic() + timeout
    while not cond():
        app.processEvents()
        if time.monotonic() > end:
            return False
        time.sleep(0.01)
    return True


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    app = QApplication.instance() or QApplication([])
    cams: list[MockCamera] = []
    ctrl = CameraController(lambda: cams.append(MockCamera(seed=1, latency=0.02)) or cams[-1])
    got = {}
    ctrl.options_ready.connect(lambda o: got.update(opts=o))
    ctrl.connect_camera()
    assert _wait(app, lambda: bool(cams) and cams[0].is_connected)
    ctrl.refresh_options()
    assert _wait(app, lambda: "opts" in got)
    opts = got["opts"]
    codes = {p: v[1] for p, v in opts.items()}
    root = tmp_path / "library"

    def make(light="uv70") -> FlatDialog:
        d = FlatDialog(ctrl, root, channel="R", light=light, opts=opts, codes=codes, lens="EF-S18-55", camera="Mock")
        d.zoom_ok.setChecked(True)
        d.target.setText("blank gel")
        return d

    yield app, ctrl, cams[0], make, root
    ctrl.shutdown()


def _take(app, dlg, n=8):
    dlg.count.setCurrentIndex(dlg.count.findData(n))
    dlg.btn_flats.click()
    assert _wait(app, lambda: dlg.flats_done)


def _darks(app, dlg):
    assert not dlg.btn_darks.isEnabled()  # the lights-off checklist comes first
    for cb in dlg.dark_checks:
        cb.setChecked(True)
    assert dlg.btn_darks.isEnabled()
    dlg.btn_darks.click()
    assert _wait(app, lambda: dlg.darks_done)


def test_whole_flow_saves_a_complete_set(env):
    app, _ctrl, _cam, make, root = env
    dlg = make("uv70")
    assert not dlg.btn_save.isEnabled() and not dlg.btn_darks.isEnabled()
    dlg.btn_test.click()
    assert _wait(app, lambda: dlg.stats is not None)
    assert dlg.st_centre.isHidden() is False
    _take(app, dlg, 8)
    assert dlg.flat_bar.value() == 8 and not dlg.btn_flats.isEnabled() and not dlg.light.isEnabled()
    _darks(app, dlg)
    dlg.btn_save.click()
    assert _wait(app, lambda: dlg.flat_set is not None)
    s = dlg.flat_set
    assert s.light == "uv70" and s.channel == "R" and s.zoom_marked and s.target == "blank gel"
    assert len(s.flats) == 8 and len(s.darks) == 8 and s.lens == "EF-S18-55" and s.camera == "Mock"
    assert not (s.path / "test").exists()  # the test frame is not part of the set
    assert [f.id for f in lib.list_flats(root)] == [s.id]
    assert dlg.result() == dlg.DialogCode.Accepted
    arr = lib.Arrangement("uv70", s.aperture, "EF-S18-55")
    assert lib.assess(s, arr).status == "ok"


def test_exposure_proposal_is_applied_and_sent_to_the_camera(env):
    app, ctrl, cam, make, _root = env
    dlg = make()
    sent = []
    orig = ctrl.set_value
    ctrl.set_value = lambda prop, code: (sent.append((prop, code)), orig(prop, code))[1]
    dlg.btn_test.click()
    assert _wait(app, lambda: dlg.stats is not None)
    advice = dlg.advice.text()
    if dlg.proposal_code is not None and dlg.proposal_code != dlg.codes[Prop.TV]:
        assert dlg.btn_apply.isEnabled() and "Proposal" in advice
        before = dlg.codes[Prop.TV]
        dlg.btn_apply.click()
        assert dlg.codes[Prop.TV] == dlg.proposal_code or dlg.codes[Prop.TV] != before
        assert (Prop.TV, dlg.codes[Prop.TV]) in sent
        assert dlg.codes[Prop.TV] in cam.allowed_values(Prop.TV)  # only values the camera offers
    dlg.reject()


def test_cancel_removes_an_unfinished_set(env):
    app, _ctrl, _cam, make, root = env
    dlg = make()
    _take(app, dlg, 8)
    folder = dlg.folder
    assert folder is not None and folder.exists()
    dlg.reject()  # QMessageBox.question is patched to "Yes"
    assert not folder.exists() and lib.list_flats(root) == []


def test_interrupted_flat_series_resumes_after_reconnect(env):
    app, ctrl, cam, make, _root = env
    dlg = make()
    dlg.count.setCurrentIndex(dlg.count.findData(8))
    dlg.btn_flats.click()
    assert _wait(app, lambda: dlg._batch is not None and len(dlg._batch["got"]) >= 3)
    cam.simulate_disconnect(1.0)
    assert _wait(app, lambda: dlg._batch is not None and dlg._batch["paused"], 10)
    kept = len(dlg._batch["got"])
    assert kept >= 3 and not dlg.status.isHidden() and "kept" in dlg.status.text()
    assert _wait(app, lambda: dlg.flats_done, 40)  # reconnect, then the missing frames
    assert len(list((dlg.folder / "flat").iterdir())) >= 8
    dlg.reject()


def test_unfinished_set_is_not_in_the_library_and_save_needs_darks(env):
    app, _ctrl, _cam, make, root = env
    dlg = make()
    _take(app, dlg, 8)
    assert not dlg.btn_save.isEnabled()
    assert lib.list_flats(root) == []  # flat.json is written only by Save
    dlg.reject()
