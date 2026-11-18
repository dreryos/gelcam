"""The flat field in the wizard: picking from the library, metadata, processing, the UV cross-check, new flat."""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from gelcam.acquisition import flat as flat_acq  # noqa: E402
from gelcam.camera import MockCamera, Prop  # noqa: E402
from gelcam.camera.values import av_fnumber  # noqa: E402
from gelcam.processing.exposure import ExposureMeasurement  # noqa: E402
from gelcam.storage import flat_library as lib  # noqa: E402
from gelcam.testing.synthetic import SyntheticGel, expose  # noqa: E402
from gelcam.ui.controller import CameraController  # noqa: E402
from gelcam.ui.wizard import GelWizard  # noqa: E402


def _wait(app, cond, timeout=30.0):
    end = time.monotonic() + timeout
    while not cond():
        app.processEvents()
        if time.monotonic() > end:
            return False
        time.sleep(0.01)
    return True


def _make_flat(root: Path, light: str, aperture: float, *, centre_scale: float = 1.0) -> lib.FlatSet:
    """A complete flat set in the size of the mock's frames, with a known vignetting."""
    rng = np.random.default_rng(5)
    folder = lib.new_flat_dir(root, light, datetime.now())
    signal = SyntheticGel().flat_field()
    for i in range(1, 9):
        np.save(folder / "flat" / f"f_{i}.npy", expose(signal, rng, photons=4000.0 * centre_scale))
        np.save(folder / "dark" / f"d_{i}.npy", expose(signal * 0, rng, photons=0.0))
    return flat_acq.build_flat_set(folder, light=light, channel="R", iso=100, seconds=4.0, aperture=aperture,
                                   target="blank gel", zoom_marked=True, lens=None)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    app = QApplication.instance() or QApplication([])
    cams: list[MockCamera] = []
    ctrl = CameraController(lambda: cams.append(MockCamera(seed=1)) or cams[-1])
    ctrl.connect_camera()
    assert _wait(app, lambda: bool(cams) and cams[0].is_connected)
    ctrl.set_live_view(True)
    assert _wait(app, lambda: ctrl.live and ctrl.lens.name is not None)
    library = tmp_path / "flats"

    def wizard(light="uv70") -> GelWizard:
        w = GelWizard(ctrl, tmp_path / "gels", light, flat_library=library)
        assert _wait(app, lambda: bool(w.opts))
        return w

    yield app, ctrl, cams[0], wizard, library, tmp_path
    ctrl.shutdown()


def _to_step5(app, wiz, library_setup=None):
    """Walks to the calibration step; `library_setup(aperture)` fills the library once the exposure is known."""
    wiz.gel_name.setText("flat-test")
    for _ in range(3):
        wiz.btn_next.click()  # -> 4 test exposure
    assert _wait(app, lambda: wiz.applied)
    result = library_setup(av_fnumber(wiz.codes[Prop.AV])) if library_setup else None
    wiz.btn_next.click()  # -> 5 calibration
    return result


def test_without_a_library_the_flat_is_skipped(env):
    app, _ctrl, _cam, wizard, _library, _tmp = env
    wiz = wizard()
    _to_step5(app, wiz)
    assert not wiz.flat_stored.isEnabled() and wiz.flat_none.isChecked()
    assert "no flat field yet" in wiz.flat_hint.text()
    assert wiz.selected_flat is None
    meta = wiz._metadata()
    assert meta["flat"].startswith("skipped") and "flat_frames" not in meta
    wiz.close()


def test_a_matching_flat_is_preselected_and_recorded(env):
    app, _ctrl, _cam, wizard, library, _tmp = env
    wiz = wizard("uv70")
    flat = _to_step5(app, wiz, lambda ap: _make_flat(library, "uv70", ap))
    assert wiz.flat_stored.isEnabled() and wiz.flat_stored.isChecked()  # a matching one is used by default
    assert wiz.selected_flat.id == flat.id and wiz.flat_note.isHidden()
    meta = wiz._metadata()
    assert meta["flat"]["id"] == flat.id and meta["flat"]["assessment"]["status"] == "ok"
    assert meta["flat_frames"] == [str(p) for p in flat.flat_paths] and len(meta["flat_dark_frames"]) == 8
    assert all(Path(p).is_absolute() for p in meta["flat_frames"])
    wiz.flat_none.setChecked(True)  # the operator can still decline
    assert wiz._metadata()["flat"].startswith("skipped")
    wiz.close()


def test_a_flat_of_another_uv_level_is_offered_but_flagged(env):
    app, _ctrl, _cam, wizard, library, _tmp = env
    wiz = wizard("uv70")
    _to_step5(app, wiz, lambda ap: _make_flat(library, "uv100", ap))
    assert wiz.flat_stored.isEnabled() and wiz.flat_none.isChecked()  # not preselected: it does not match
    wiz.flat_stored.setChecked(True)
    assert not wiz.flat_note.isHidden() and "another light" in wiz.flat_note.text()
    assert wiz._metadata()["flat"]["assessment"]["status"] == "mismatch"
    wiz.close()


def test_processing_divides_out_the_selected_flat(env):
    app, _ctrl, _cam, wizard, library, _tmp = env
    wiz = wizard("uv70")
    flat = _to_step5(app, wiz, lambda ap: _make_flat(library, "uv70", ap))
    wiz.btn_next.click()  # -> 6
    wiz.frames.setCurrentIndex(wiz.frames.findData(4))
    wiz.btn_series.click()
    assert _wait(app, lambda: wiz.series_done)
    for cb in wiz.dark_checks:
        cb.setChecked(True)
    wiz.btn_darks.click()
    assert _wait(app, lambda: wiz.darks_done)
    wiz.btn_next.click()  # -> 7
    assert flat.id in wiz.summary.text()
    wiz.btn_process.click()
    assert _wait(app, lambda: wiz.processed or "failed" in wiz.proc_label.text().lower(), 120), wiz.proc_label.text()
    assert wiz.processed
    meta = json.loads((wiz.folder / "metadata.json").read_text(encoding="utf-8"))
    steps = {s["step"]: s for s in meta["processing"]}
    assert "skipped" not in steps["master_flat"] and steps["calibrate"]["formula"] == "(L - D) / F_hat"
    assert steps["master_flat"]["flats"] == [p.name for p in flat.flat_paths]
    wiz.accept()


def test_uv_cross_check_catches_a_lamp_that_is_off(env):
    app, _ctrl, _cam, wizard, library, _tmp = env
    wiz = wizard("uv70")
    wiz.gel_name.setText("uv-check")
    for _ in range(3):
        wiz.btn_next.click()
    assert _wait(app, lambda: wiz.applied)
    flat = _make_flat(library, "uv70", av_fnumber(wiz.codes[Prop.AV]))  # centre rate = centre_adu / 4 s
    seconds = 4.0
    wiz.codes[Prop.TV] = next(c for c in wiz.opts[Prop.TV][0] if abs((_secs(c) or 0) - seconds) < 0.01)
    wiz.show()

    def measure(factor: float) -> ExposureMeasurement:
        return ExposureMeasurement(1000.0, 0.1, 0.0, 5.0, flat.centre_adu * factor)

    wiz._check_uv(measure(0.9))
    assert wiz.uv_check.status == "ok" and wiz.uv_note.isHidden()
    wiz._check_uv(measure(0.05))  # nearly dark: the UV lamp is probably off
    assert wiz.uv_check.status == "warn" and not wiz.uv_note.isHidden()
    assert "0.1x as bright" in wiz.uv_note.text() and "cannot be detected" in wiz.uv_note.text()
    assert wiz._metadata()["uv_check"]["status"] == "warn"
    wiz.close()


def _secs(code: int):
    from gelcam.camera.values import tv_seconds

    return tv_seconds(code)


def test_take_new_flat_from_the_wizard_selects_it_and_restores_the_exposure(env, monkeypatch):
    app, ctrl, _cam, wizard, library, _tmp = env
    from gelcam.ui import flat_dialog

    wiz = wizard("uv70")
    _to_step5(app, wiz)
    series_codes = dict(wiz.codes)
    sent = []
    orig = ctrl.set_value
    ctrl.set_value = lambda prop, code: (sent.append((prop, code)), orig(prop, code))[1]

    def drive(dlg: flat_dialog.FlatDialog) -> int:  # what the operator does in the window
        dlg.zoom_ok.setChecked(True)
        dlg.count.setCurrentIndex(dlg.count.findData(8))
        dlg.btn_flats.click()
        assert _wait(app, lambda: dlg.flats_done)
        for cb in dlg.dark_checks:
            cb.setChecked(True)
        dlg.btn_darks.click()
        assert _wait(app, lambda: dlg.darks_done)
        dlg.btn_save.click()
        assert _wait(app, lambda: dlg.flat_set is not None)
        return 1

    monkeypatch.setattr(flat_dialog.FlatDialog, "exec", drive)
    wiz.btn_new_flat.click()
    assert wiz.flat_stored.isChecked() and wiz.selected_flat is not None
    assert wiz.selected_flat.light == "uv70" and len(wiz.selected_flat.flats) == 8
    assert wiz.selected_flat.camera == ctrl.camera_model
    for prop, code in series_codes.items():  # the series exposure is sent again after the flat's own
        assert (prop, code) in sent
    assert [f.id for f in lib.list_flats(library)] == [wiz.selected_flat.id]
    wiz.close()
