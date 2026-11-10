import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from gelcam.processing import framestack
from gelcam.processing.pipeline import process, process_gel_folder
from gelcam.processing.raw_io import RawFrame
from gelcam.testing.synthetic import SyntheticGel, expose

GEL = SyntheticGel(vignetting=0.4)
SIG = GEL.signal()
FF = GEL.flat_field()
CALIB = Path(__file__).resolve().parents[1] / "testdata" / "calib"


def _save(folder: Path, name: str, i: int, plane: np.ndarray) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{name}_{i:02d}.npy"
    np.save(p, np.repeat(np.repeat(plane, 2, 0), 2, 1))  # R plane = mosaic[0::2, 0::2] = plane
    return p


def make_set(root: Path, n=16, shifts=None, flat=True, seed=0, photons=2000.0, ncal=16):
    rng = np.random.default_rng(seed)
    hot = np.zeros(SIG.shape)
    ys, xs = rng.integers(20, 460, 20), rng.integers(20, 700, 20)
    hot[ys, xs] = 800
    lights = []
    for i in range(n):
        sig = SIG
        if shifts:
            sig = np.roll(SIG, shifts[i % len(shifts)], axis=(0, 1))
        lights.append(_save(root / "raw", "L", i, expose(sig * FF, rng, photons=photons, hot_pixels=hot)))
    darks = [_save(root / "calib", "D", i, expose(np.zeros_like(SIG), rng, hot_pixels=hot)) for i in range(ncal)]
    flats, fdarks = [], []
    if flat:
        flats = [_save(root / "calib", "F", i, expose(FF * 0.6, rng, photons=photons)) for i in range(ncal)]
        fdarks = [_save(root / "calib", "FD", i, expose(np.zeros_like(SIG), rng)) for i in range(ncal)]
    return lights, darks, flats, fdarks, (ys, xs)


def band_sums(img):
    h, w = img.shape
    lw = w / 9
    bg = np.median(img)

    def s(lane):
        cx, cy = int(lw * (lane + 1)), int(0.4 * h)
        return float((img[cy - 7:cy + 8, cx - int(lw * .3):cx + int(lw * .3)] - bg).sum())
    return s(0), s(2)


def read_tif(p):
    return pytest.importorskip("tifffile").imread(p)


@pytest.fixture(scope="module")
def basic(tmp_path_factory):
    root = tmp_path_factory.mktemp("basic")
    lights, darks, flats, fdarks, hot = make_set(root)
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in lights + darks + flats + fdarks}
    steps = []
    res = process(lights, darks, "R", root / "out", flats=flats, flat_darks=fdarks,
                  progress=lambda m, f: steps.append((m, f)))
    return root, res, hashes, hot, steps


def test_noise_drops_sqrt_n(basic):
    ratio = basic[1].stats["background_noise_ratio"]
    assert 0.2 < ratio < 0.32  # 1/sqrt(16) = 0.25


def test_band_ratios_preserved(basic):
    img = read_tif(basic[1].result).astype(np.float64)
    a, b = band_sums(img)
    ta, tb = band_sums(SIG)
    assert a / b == pytest.approx(ta / tb, rel=0.03)


def test_hot_pixels_removed(basic):
    img = read_tif(basic[1].result).astype(np.float64)
    ys, xs = basic[3]
    assert np.abs(img[ys, xs] - img[ys, xs - 1]).max() < 100  # uncorrected would be ~800 above


def test_vignetting_removed(basic):
    img = read_tif(basic[1].result).astype(np.float64)
    corner, centre = img[:20, :20].mean(), img[230:250, 350:370].mean()
    assert corner / centre == pytest.approx(1.0, rel=0.05)  # uncorrected: ~0.6


def test_outputs_and_housekeeping(basic):
    root, res, hashes, _, progress = basic
    img = read_tif(res.result)
    assert img.dtype == np.uint16 and img.shape == SIG.shape and res.preview.exists()
    assert not (root / "out" / "work").exists()
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes} == hashes
    names = [s["step"] for s in res.steps]
    assert names == ["read_lights", "master_dark", "master_flat", "calibrate", "align", "stack",
                     "export_result", "export_preview"]
    assert res.stats["saturated_pixels"] == 0 and res.stats["frames_used"] == 16
    json.dumps(res.steps), json.dumps(res.stats)
    assert progress[-1] == ("Done", 1.0)


def test_integer_shifts_detected_and_corrected(tmp_path):
    shifts = [(0, 0), (3, -2), (-4, 5), (2, 2), (-1, -3), (5, 0), (0, -4), (-3, 3)]
    ref_set = make_set(tmp_path / "a", n=8, flat=False, photons=8000.0)
    sh_set = make_set(tmp_path / "b", n=8, shifts=shifts, flat=False, photons=8000.0)
    ref = process(ref_set[0], ref_set[1], "R", tmp_path / "oa")
    res = process(sh_set[0], sh_set[1], "R", tmp_path / "ob")
    found = next(s for s in res.steps if s["step"] == "align")["shifts_dy_dx"]
    for (dy, dx), (ty, tx) in zip(found, shifts):
        assert (dy, dx) == pytest.approx((-ty, -tx), abs=0.6)
    assert res.stats["shift_max_px"] >= 4
    peak = lambda r: float(read_tif(r.result)[180:205, :].max())  # noqa: E731
    assert peak(res) >= 0.9 * peak(ref)


def test_flats_without_flat_darks_rejected(tmp_path):
    lights, darks, flats, _, _ = make_set(tmp_path, n=3)
    with pytest.raises(ValueError, match="flat darks"):
        process(lights, darks, "R", tmp_path / "out", flats=flats)


def test_work_dir_removed_on_error(tmp_path):
    lights, darks, *_ = make_set(tmp_path, n=3, flat=False)
    np.save(darks[1], np.zeros((10, 10), np.uint16))  # shape mismatch
    with pytest.raises(ValueError):
        process(lights, darks, "R", tmp_path / "out")
    assert not (tmp_path / "out" / "work").exists()


def test_process_gel_folder_and_no_overwrite(tmp_path):
    lights, darks, *_ = make_set(tmp_path, n=4, flat=False)
    meta = {"profile": {"channel": "R"}, "light_frames": [str(p) for p in lights],
            "dark_frames": [p.relative_to(tmp_path).as_posix() for p in darks], "flat": "skipped",
            "processing": [], "status": "captured; processing pending", "gel_name": "x"}
    (tmp_path / "metadata.json").write_text(json.dumps(meta))
    res = process_gel_folder(tmp_path)
    out = json.loads((tmp_path / "metadata.json").read_text())
    assert out["status"] == "processed" and out["gel_name"] == "x" and out["result"] == "result.tif"
    assert [s["step"] for s in out["processing"]] == [s["step"] for s in res.steps]
    assert "background_noise_ratio" in out["stats"]
    with pytest.raises(FileExistsError):
        process_gel_folder(tmp_path)


def test_build_stack_crops_to_image_area(tmp_path, monkeypatch):
    def fake(path):
        m = np.arange(20 * 40, dtype=np.uint16).reshape(20, 40)
        colors = np.tile(np.array([[0, 1], [3, 2]], np.uint8), (10, 20))
        return RawFrame(m, colors, "RGBG", (0.0,) * 4, 60000, "f", image_area=(2, 4, 10, 20))

    monkeypatch.setattr(framestack, "read_frame", fake)
    st = framestack.build_stack([tmp_path / "a"], "R", tmp_path / "s.f32")
    assert st.array.shape == (1, 5, 10) and st.saturated.shape == (5, 10)
    assert st.array[0, 0, 0] == 2 * 40 + 4
    st.discard()
    st = framestack.build_stack([tmp_path / "a"], "R", tmp_path / "s.f32", crop=False)
    assert st.array.shape == (1, 10, 20)
    st.discard()
    monkeypatch.setattr(framestack, "read_frame", lambda p: RawFrame(
        np.zeros((20, 40), np.uint16), np.zeros((20, 40), np.uint8), "RGBG", (0.0,) * 4, 1, "f",
        image_area=(1, 4, 10, 20)))
    with pytest.raises(ValueError, match="even"):
        framestack.build_stack([tmp_path / "a"], "R", tmp_path / "s.f32")


_SCENE = CALIB / "2026-11-04_scene_4s_iso100_uv100"
_DARK = CALIB / "2026-11-04_dark_4s_iso100"


@pytest.mark.skipif(not (_SCENE.exists() and _DARK.exists()), reason="testdata missing")
def test_real_data_r_channel(tmp_path):
    pytest.importorskip("rawpy")
    res = process(sorted(_SCENE.glob("*.CR2"))[:8], sorted(_DARK.glob("*.CR2"))[:8], "R", tmp_path)
    assert read_tif(res.result).shape == (1728, 2592)
    assert 0.35 < res.stats["background_noise_ratio"] < 0.55  # 8 lights; the median master dark of 8 adds common noise
