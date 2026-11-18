"""The Czech translation: complete, in step with the sources, and really shown in the windows."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import translations  # noqa: E402

from PySide6.QtCore import QTranslator  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gelcam import runtime  # noqa: E402

CS = translations.ts_path("cs")


def test_every_text_is_translated_with_matching_placeholders():
    assert translations.problems(CS) == []


def test_translation_file_is_in_step_with_the_sources(tmp_path):
    """A new or changed tr() text without an update of the .ts file is caught here."""
    fresh = tmp_path / "fresh.ts"
    sources = sorted(str(p) for p in translations.SRC.rglob("*.py"))
    code = subprocess.call([translations._tool("pyside6-lupdate"), *sources, "-ts", str(fresh), "-no-obsolete"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if code != 0:
        pytest.skip("pyside6-lupdate is not available")
    wanted = {(c, s) for c, s, _t, _u in translations.read_ts(fresh)}
    have = {(c, s) for c, s, _t, _u in translations.read_ts(CS)}
    assert wanted - have == set(), "texts missing from gelcam_cs.ts - run tools/translations.py update"
    assert have - wanted == set(), "obsolete texts in gelcam_cs.ts - run tools/translations.py update"


@pytest.fixture
def czech(tmp_path, monkeypatch):
    """The Czech .qm compiled into a temp folder and installed like the application does."""
    import shutil

    folder = tmp_path / "translations"
    folder.mkdir()
    shutil.copy(CS, folder / CS.name)
    if subprocess.call([translations._tool("pyside6-lrelease"), str(folder / CS.name), "-qm",
                        str(folder / "gelcam_cs.qm")], stdout=subprocess.DEVNULL) != 0:
        pytest.skip("pyside6-lrelease is not available")
    monkeypatch.setattr(runtime, "translations_dir", lambda: folder)
    app = QApplication.instance() or QApplication([])
    assert runtime.install_translator(app, "cs")
    yield app
    for tr in getattr(app, "_gelcam_translators", []):
        app.removeTranslator(tr)


def test_compiled_translation_translates(czech):
    tr = QTranslator()
    assert tr.load(str(runtime.translations_dir() / "gelcam_cs.qm"))
    assert tr.translate("MainWindow", "Connected") == "Připojeno"
    assert tr.translate("GelWizard", "Finish") == "Dokončit"


def test_main_window_and_wizard_are_shown_in_czech(czech):
    from gelcam.camera import MockCamera
    from gelcam.ui.controller import CameraController
    from gelcam.ui.main_window import MainWindow
    from gelcam.ui.wizard import GelWizard

    ctrl = CameraController(lambda: MockCamera(seed=1))
    win = MainWindow(ctrl)
    assert win.btn_af.text() == "Spustit autofokus"
    assert win.light_combo.itemText(0) == "Světlo: Bílé světlo"  # a text that goes through a variable
    assert win.btn_capture.text() == "Pořídit snímek"
    wiz = GelWizard(ctrl, Path(os.environ.get("TEMP", ".")), "white", flat_library=Path(os.environ.get("TEMP", ".")) / "gelcam-no-flats")
    assert wiz.btn_af.text() == "Spustit autofokus"
    assert "filtr: oranžový" in wiz.profile_hint.text()  # profile filter name through a mapping
    assert wiz._progress_text("Stacking") == "Slučuji snímky"
    wiz.close()
    win.close()
    ctrl.shutdown()


def test_without_the_translation_the_app_stays_english(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "translations_dir", lambda: tmp_path)
    app = QApplication.instance() or QApplication([])
    assert runtime.install_translator(app, "cs") is False
    from gelcam.camera import MockCamera
    from gelcam.ui.controller import CameraController
    from gelcam.ui.main_window import MainWindow

    ctrl = CameraController(lambda: MockCamera(seed=1))
    win = MainWindow(ctrl)
    assert win.btn_af.text() == "Run autofocus"
    win.close()
    ctrl.shutdown()
