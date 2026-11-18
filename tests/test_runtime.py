"""Packaged-app support: log file, crash hook, language choice, frozen paths and the self-test."""

import logging
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gelcam import runtime  # noqa: E402


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Data folder in tmp, and the root logger / excepthook restored afterwards."""
    monkeypatch.setattr(runtime, "data_dir", lambda: tmp_path)
    root = logging.getLogger()
    handlers, level, hook = list(root.handlers), root.level, sys.excepthook
    yield tmp_path
    for h in list(root.handlers):
        if h not in handlers:
            root.removeHandler(h)
            h.close()
    root.setLevel(level)
    sys.excepthook = hook


def test_setup_logging_writes_under_the_data_folder(isolated):
    path = runtime.setup_logging()
    assert path == isolated / runtime.LOG_NAME and path.exists()
    logging.getLogger("gelcam").info("hello from the test")
    for h in logging.getLogger().handlers:
        h.flush()
    assert "hello from the test" in path.read_text(encoding="utf-8")


def test_setup_logging_survives_an_unwritable_folder(monkeypatch):
    monkeypatch.setattr(runtime, "log_path", lambda: Path("Z:/no/such/folder/x.log"))
    assert runtime.setup_logging() is None


def test_excepthook_logs_and_tells_the_operator(isolated, monkeypatch):
    runtime.setup_logging()
    shown = []
    runtime.install_excepthook(lambda title, text: shown.append((title, text)))
    monkeypatch.setattr(sys, "__excepthook__", lambda *a: None)  # keep pytest's output clean
    try:
        raise ValueError("boom")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    for h in logging.getLogger().handlers:
        h.flush()
    assert "Uncaught exception" in (isolated / runtime.LOG_NAME).read_text(encoding="utf-8")
    assert shown and shown[0][0] == "GelCam crashed" and "boom" in shown[0][1] and runtime.LOG_NAME in shown[0][1]


def test_language_choice(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "translations_dir", lambda: tmp_path)
    monkeypatch.delenv("GELCAM_LANG", raising=False)
    assert runtime.choose_language(None, "cs_CZ") == "en"  # Czech system, but no translation installed
    (tmp_path / "gelcam_cs.qm").write_bytes(b"")
    assert runtime.choose_language(None, "cs_CZ") == "cs"
    assert runtime.choose_language(None, "de_DE") == "en"
    assert runtime.choose_language(None, "en_US") == "en"
    monkeypatch.setenv("GELCAM_LANG", "de")
    assert runtime.choose_language(None, "cs_CZ") == "de"  # the variable beats the system language
    assert runtime.choose_language("EN", "cs_CZ") == "en"  # an explicit request beats everything


def test_translator_is_optional(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(runtime, "translations_dir", lambda: tmp_path)
    assert runtime.install_translator(app, "en") is False  # the source language needs none
    assert runtime.install_translator(app, "cs") is False  # file missing: English, no crash


def test_frozen_paths(monkeypatch, tmp_path):
    exe = tmp_path / "GelCam" / "GelCam.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert runtime.is_frozen() and runtime.app_dir() == exe.parent.resolve()
    monkeypatch.setattr(sys, "_MEIPASS", str(exe.parent / "_internal"), raising=False)  # PyInstaller's data folder
    assert runtime.translations_dir() == exe.parent / "_internal" / "translations"


def test_selftest_passes_without_a_camera():
    pytest.importorskip("PySide6")
    lines: list[str] = []
    assert runtime.selftest(check_camera=False, out=lines.append) == 0
    assert lines[-1] == "RESULT: all required checks passed"
    assert any(line.startswith("OK    main window") for line in lines)
