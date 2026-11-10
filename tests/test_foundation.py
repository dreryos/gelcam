"""Pure-logic tests: focus, exposure, values, profiles, storage, preview, MockCamera extras."""

import json
from datetime import date

import numpy as np
import pytest

from gelcam.acquisition.profiles import DEFAULT_PROFILES, profile_by_name
from gelcam.camera import CameraError, MockCamera
from gelcam.camera.values import tv_code_at_most
from gelcam.processing.channel import select_channel
from gelcam.processing.exposure import measure, propose_seconds
from gelcam.processing.focus import sharpness, sharpness_rgb
from gelcam.processing.raw_io import RawFrame, read_frame
from gelcam.storage.gel_folder import create_gel_folder, write_metadata
from gelcam.testing.synthetic import SIM_BLACK, SIM_WHITE
from gelcam.ui import preview


def _bands(n=64):
    img = np.zeros((n, n, 3), np.uint8)
    img[::8] = 255
    return img


def test_sharpness_constant_is_zero():
    assert sharpness(np.full((10, 10), 7)) == 0.0


def test_sharp_beats_blurred():
    sharp = _bands()
    k = np.ones(3) / 3
    blur = np.apply_along_axis(lambda c: np.convolve(c, k, mode="same"), 0, sharp.astype(float))
    assert sharpness_rgb(sharp) > sharpness_rgb(blur.astype(np.uint8))


def _frame(level_adu, white=SIM_WHITE):
    mosaic = np.full((8, 8), SIM_BLACK + level_adu, np.uint16)
    colors = np.tile(np.array([[0, 1], [3, 2]], np.uint8), (4, 4))
    return RawFrame(mosaic, colors, "RGBG", (float(SIM_BLACK),) * 4, white)


def test_measure():
    m = measure(_frame(5000), "R")
    assert m.brightest_adu == pytest.approx(5000)
    assert m.fraction == pytest.approx(5000 / (SIM_WHITE - SIM_BLACK))
    assert m.saturated_fraction == 0.0
    assert measure(_frame(SIM_WHITE), "G").saturated_fraction == 1.0


def test_propose_seconds():
    assert propose_seconds(2.0, 0.375) == pytest.approx(4.0)
    assert propose_seconds(2.0, 0.0) == 30.0
    assert propose_seconds(20.0, 0.1) == 30.0


def test_tv_code_at_most():
    allowed = [0x0C, 0x10, 0x38, 0x48]  # Bulb, 30", 1", 1/4
    assert tv_code_at_most(allowed, 1.0) == 0x38
    assert tv_code_at_most(allowed, 5.0) == 0x38
    assert tv_code_at_most(allowed, 0.01) == 0x48  # none fits: shortest
    assert tv_code_at_most([0x0C], 1.0) is None
    assert tv_code_at_most([], 1.0) is None


def test_read_frame_npy(tmp_path):
    cam = MockCamera(seed=1)
    cam.connect()
    frame = read_frame(cam.capture(tmp_path))
    assert frame.color_desc == "RGBG" and frame.white_level == SIM_WHITE
    plane = select_channel(frame, "R")
    assert plane.shape == (frame.shape[0] // 2, frame.shape[1] // 2)
    assert plane.mean() > SIM_BLACK


def test_profiles():
    assert [p.name for p in DEFAULT_PROFILES] == ["EtBr", "GelRed", "SYBR Safe"]
    assert profile_by_name("SYBR Safe").channel == "G"
    with pytest.raises(KeyError):
        profile_by_name("nope")


def test_gel_folder(tmp_path):
    a = create_gel_folder(tmp_path, "my gel/1", date(2026, 11, 10))
    assert a.name == "2026-11-10_my-gel-1"
    assert (a / "raw").is_dir() and (a / "calib").is_dir()
    assert create_gel_folder(tmp_path, "my gel/1", date(2026, 11, 10)).name.endswith("_2")
    assert create_gel_folder(tmp_path, "", date(2026, 11, 10)).name == "2026-11-10_gel"


def test_write_metadata(tmp_path):
    out = write_metadata(tmp_path, {"raw": tmp_path / "raw" / "a.CR2", "other": tmp_path.parent / "x", "n": "ž"})
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["raw"] == "raw/a.CR2" and doc["other"] == str(tmp_path.parent / "x")
    assert "app_version" in doc and doc["written"][-6] in "+-"
    assert "ž" in out.read_text(encoding="utf-8")


def test_mock_unavailable_and_outage():
    with pytest.raises(CameraError, match="No camera found"):
        MockCamera(available=False).connect()
    cam = MockCamera()
    cam.connect()
    cam.start_live_view()
    cam.simulate_disconnect(0.2)
    assert not cam.is_connected
    with pytest.raises(CameraError):
        cam.live_view_frame()
    with pytest.raises(CameraError):
        cam.reconnect(attempts=2, delay=0.01)
    assert cam.reconnect(attempts=20, delay=0.05).model and cam.is_connected


def test_preview_helpers():
    f = np.zeros((4, 4, 3), np.uint8)
    f[0, 0] = 255
    out = preview.apply_display(f, 0, 255)
    assert out[0, 0, 0] == 255 and out[1, 1, 0] == 0
    assert preview.apply_display(f, 0, 255, invert=True)[1, 1, 0] == 255
    assert preview.apply_display(np.full((1, 1, 3), 128, np.uint8), 0, 255, gamma=2.0)[0, 0, 0] > 128
    b, w = preview.auto_levels(np.full((4, 4, 3), 100, np.uint8), 0)
    assert w > b
    h = preview.histogram(f, 0, bins=64)
    assert h.shape == (64,) and h.sum() == 16
    mask = preview.clipped_mask(f, 0)
    assert mask.sum() == 1
    painted = preview.overlay_clipping(f, mask)
    assert tuple(painted[0, 0]) == (255, 40, 40) and tuple(f[0, 0]) == (255, 255, 255)
