"""Black-and-white TIFF of a single frame: the exporter, the controller job, the options in the main window."""

import json
import os
import time

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gelcam import runtime, settings as cfg  # noqa: E402
from gelcam.processing.export import frame_tiff_name, write_frame_tiff  # noqa: E402
from gelcam.processing.raw_io import RawFrame  # noqa: E402


def _frame() -> RawFrame:
    """4x4 mosaic RGGB; black level 100, white level 1100 (span 1000)."""
    mosaic = np.full((4, 4), 100, np.uint16)
    mosaic[0::2, 0::2] = [[100, 600], [1100, 2000]]  # red pixels: 0 %, 50 %, 100 %, above saturation
    colors = np.zeros((4, 4), np.uint8)
    colors[0::2, 1::2] = 1
    colors[1::2, 0::2] = 3
    colors[1::2, 1::2] = 2
    return RawFrame(mosaic=mosaic, colors=colors, color_desc="RGBG", black_levels=(100.0,) * 4,
                    white_level=1100, source="IMG_0001.CR2")


def test_names():
    assert frame_tiff_name("a/IMG_0001.CR2", False) == "IMG_0001.tif"
    assert frame_tiff_name("a/IMG_0001.CR2", True) == "IMG_0001_inverted.tif"


def test_linear_scaling_and_metadata(tmp_path):
    tifffile = pytest.importorskip("tifffile")
    info = write_frame_tiff(tmp_path / "f.tif", _frame(), "R")
    out = tifffile.imread(tmp_path / "f.tif")
    assert out.dtype == np.uint16 and out.shape == (2, 2)
    assert out.tolist() == [[0, 32768], [65535, 65535]]  # 0 %, 50 %, 100 %, clipped
    assert info["inverted"] is False and info["scale"] == pytest.approx(65.535)
    with tifffile.TiffFile(tmp_path / "f.tif") as tf:
        meta = json.loads(tf.pages[0].description)
    assert meta["channel"] == "R" and meta["black_level"] == 100.0 and meta["source"] == "IMG_0001.CR2"


def test_inverted_is_the_complement(tmp_path):
    tifffile = pytest.importorskip("tifffile")
    write_frame_tiff(tmp_path / "a.tif", _frame(), "R")
    info = write_frame_tiff(tmp_path / "b.tif", _frame(), "R", inverted=True)
    a, b = tifffile.imread(tmp_path / "a.tif"), tifffile.imread(tmp_path / "b.tif")
    assert (a.astype(int) + b == 65535).all() and info["inverted"] is True
    with tifffile.TiffFile(tmp_path / "b.tif") as tf:
        assert json.loads(tf.pages[0].description)["inverted"] is True


def test_never_overwrites_and_rejects_bad_levels(tmp_path):
    write_frame_tiff(tmp_path / "f.tif", _frame(), "R")
    with pytest.raises(FileExistsError):
        write_frame_tiff(tmp_path / "f.tif", _frame(), "R")
    import dataclasses

    with pytest.raises(ValueError):
        write_frame_tiff(tmp_path / "g.tif", dataclasses.replace(_frame(), white_level=50), "R")
    assert not (tmp_path / "g.tif").exists()


def test_settings_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "data_dir", lambda: tmp_path)
    assert cfg.load().frame_tiff is True and cfg.load().frame_tiff_inverted is False
    cfg.save(cfg.Settings(frame_tiff=False, frame_tiff_inverted=True))
    got = cfg.load()
    assert got.frame_tiff is False and got.frame_tiff_inverted is True


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _wait(app, cond, timeout=8.0):
    end = time.monotonic() + timeout
    while not cond():
        app.processEvents()
        if time.monotonic() > end:
            return False
        time.sleep(0.01)
    return True


def test_controller_writes_the_tiff_next_to_the_raw(app, tmp_path):
    pytest.importorskip("tifffile")
    from gelcam.camera import MockCamera
    from gelcam.ui.controller import CameraController

    cam = MockCamera(seed=1)
    cam.connect()
    raw = cam.capture(tmp_path)
    before = raw.read_bytes()
    ctrl = CameraController(lambda: cam)
    got = []
    ctrl.tiff_exported.connect(lambda r, t: got.append((r, t)))
    ctrl.export_tiff(raw, "G", True)
    assert _wait(app, lambda: got)
    assert got[0][1] == raw.with_name(raw.stem + "_inverted.tif") and got[0][1].exists()
    assert raw.read_bytes() == before  # the RAW frame is untouched
    errors = []
    ctrl.error.connect(errors.append)
    ctrl.export_tiff(raw, "G", True)  # the same file again: reported, not overwritten
    assert _wait(app, lambda: errors) and raw.name in errors[0]
    ctrl.shutdown()


def test_main_window_options_are_saved_and_used(app, tmp_path, monkeypatch):
    pytest.importorskip("tifffile")
    monkeypatch.setattr(runtime, "data_dir", lambda: tmp_path)
    from gelcam.camera import MockCamera
    from gelcam.ui.controller import CameraController
    from gelcam.ui.main_window import MainWindow

    cfg.save(cfg.Settings(root=tmp_path / "root"))
    win = MainWindow(CameraController(lambda: MockCamera(seed=1)))
    assert win.chk_tiff.isChecked() and not win.chk_inverted.isChecked()
    win.chk_inverted.setChecked(True)
    assert cfg.load().frame_tiff_inverted is True and cfg.load().root == tmp_path / "root"
    win.chk_tiff.setChecked(False)
    assert not win.chk_inverted.isEnabled() and cfg.load().frame_tiff is False
    win.chk_tiff.setChecked(True)

    cam = MockCamera(seed=1)
    cam.connect()
    raw = cam.capture(tmp_path / "root" / "images")
    win._awaiting_capture = True
    win._on_captured(raw)
    tif = raw.with_name(raw.stem + "_inverted.tif")
    assert _wait(app, lambda: tif.exists() and tif.name in win.lbl_file.text())
    win.ctrl.shutdown()
