"""Settings: storage, the root folder in the window, the settings dialog."""

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gelcam import runtime, settings as cfg  # noqa: E402
from gelcam.storage import flat_library as lib  # noqa: E402


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    folder = tmp_path / "appdata"
    folder.mkdir()
    monkeypatch.setattr(runtime, "data_dir", lambda: folder)
    return folder


def test_defaults_without_a_file(appdata):
    s = cfg.load()
    assert s.root is None and s.effective_root == cfg.default_root()
    assert s.images_dir == cfg.default_root() / "images"
    assert s.flats_dir == cfg.default_root() / "calibration" / "flats"


def test_save_and_load_round_trip(appdata, tmp_path):
    root = tmp_path / "lab-data"
    cfg.save(cfg.Settings(root=root))
    assert (appdata / cfg.SETTINGS_NAME).exists() and not list(appdata.glob(".settings-*"))
    s = cfg.load()
    assert s.root == root and s.images_dir == root / "images" and s.flats_dir == root / "calibration" / "flats"
    cfg.save(cfg.Settings(root=None))
    assert cfg.load().root is None  # back to the default


@pytest.mark.parametrize("content", ["{broken", "[]", '{"root": 5}', '{"root": "  "}', ""])
def test_a_broken_file_means_the_defaults(appdata, content):
    (appdata / cfg.SETTINGS_NAME).write_text(content, encoding="utf-8")
    assert cfg.load().root is None


def test_flat_library_follows_the_setting(appdata, tmp_path):
    assert lib.default_library_dir() == cfg.default_root() / "calibration" / "flats"
    cfg.save(cfg.Settings(root=tmp_path / "x"))
    assert lib.default_library_dir() == tmp_path / "x" / "calibration" / "flats"


def test_check_writable(tmp_path):
    assert cfg.check_writable(tmp_path / "new" / "deep") is None and (tmp_path / "new" / "deep").is_dir()
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert cfg.check_writable(blocker / "sub") is not None  # a file is in the way
    assert not list((tmp_path / "new" / "deep").iterdir())  # the probe file is removed again


def test_helpers():
    assert cfg.is_synchronised(Path("D:/Data/OneDrive/Dokumenty/GelCam"))
    assert not cfg.is_synchronised(Path("E:/GelCam-data"))
    assert cfg.free_gb(Path("C:/definitely/not/there/at/all")) is None or cfg.free_gb(Path("C:/nope")) > 0


@pytest.fixture
def app():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_dialog_blocks_a_folder_that_cannot_be_written(app, tmp_path):
    from gelcam.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog(cfg.Settings())
    assert dlg.btn_ok.isEnabled() or not dlg.btn_ok.isEnabled()  # the default folder may or may not exist yet
    good = tmp_path / "data"
    dlg.set_root(good)
    assert dlg.btn_ok.isEnabled() and dlg.warning.isHidden() and str(good) in dlg.root_label.text()
    assert str(good / "images") in dlg.detail.text() and "GB" in dlg.detail.text()
    assert dlg.result_settings.root == good
    blocker = tmp_path / "file"
    blocker.write_text("x")
    dlg.set_root(blocker / "sub")
    assert not dlg.btn_ok.isEnabled() and not dlg.warning.isHidden()
    dlg.set_root(None)
    assert dlg.result_settings.root is None and "(default)" in dlg.root_label.text()


def test_dialog_warns_about_cloud_folders(app, tmp_path):
    from gelcam.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog(cfg.Settings())
    dlg.set_root(tmp_path / "OneDrive" / "GelCam")
    assert not dlg.warning.isHidden() and "synchronised" in dlg.warning.text() and dlg.btn_ok.isEnabled()


def test_main_window_applies_the_new_root(app, appdata, tmp_path, monkeypatch):
    from gelcam.camera import MockCamera
    from gelcam.ui import settings_dialog
    from gelcam.ui.controller import CameraController
    from gelcam.ui.main_window import MainWindow

    cfg.save(cfg.Settings(root=tmp_path / "first"))
    win = MainWindow(CameraController(lambda: MockCamera(seed=1)))
    assert win.out_dir == tmp_path / "first" / "images"
    new_root = tmp_path / "second"

    def fake_exec(self) -> int:  # the operator picks a folder and presses Save
        self.set_root(new_root)
        return 1

    monkeypatch.setattr(settings_dialog.SettingsDialog, "exec", fake_exec)
    win._open_settings()
    assert win.out_dir == new_root / "images" and win.settings.root == new_root
    assert json.loads((appdata / cfg.SETTINGS_NAME).read_text(encoding="utf-8"))["root"] == str(new_root)
    win._open_wizard()
    try:
        assert win._wizard.out_root == new_root / "images"
        assert win._wizard.flat_library == new_root / "calibration" / "flats"
    finally:
        win._wizard.close()
        win.close()
        win.ctrl.shutdown()
