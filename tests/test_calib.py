from pathlib import Path

import numpy as np
import pytest

from gelcam.processing.calib import calibrate, master_dark, master_flat
from gelcam.testing.synthetic import SyntheticGel, expose

CALIB = Path(__file__).resolve().parents[1] / "testdata" / "calib"
DARK_DIR = CALIB / "2026-11-04_dark_8s_iso100"
FLAT_DIR = CALIB / "2026-11-04_flat_8s_iso100_bile"
BLACK = 2048.0


def stack(signal, n, rng, **kw):
    return np.stack([expose(signal, rng, **kw) for _ in range(n)]).astype(np.float32)


def test_hot_pixels_removed():
    rng = np.random.default_rng(1)
    gel = SyntheticGel()
    sig = gel.signal()
    hot = np.zeros(sig.shape)
    ys, xs = rng.integers(10, 470, 20), rng.integers(10, 710, 20)
    hot[ys, xs] = 800
    darks = stack(np.zeros_like(sig), 9, rng, hot_pixels=hot)
    light = expose(sig, rng, hot_pixels=hot).astype(np.float32)
    raw_excess = light[ys, xs] - light[ys, xs - 1]
    cal = calibrate(light, master_dark(darks))
    assert raw_excess.min() > 500
    # neighbours at ys, xs+-1 can be hot too (rare); compare with the image-wide noise instead
    noise = np.std(cal[:50, :50])
    assert np.all(np.abs(cal[ys, xs] - sig[ys, xs] * 2000) < 6 * noise + 50)


def test_vignetting_corrected():
    rng = np.random.default_rng(2)
    gel = SyntheticGel(vignetting=0.4)
    sig, ff = gel.signal(), gel.flat_field()
    zero = np.zeros_like(sig)
    dark = master_dark(stack(zero, 9, rng))
    lights = stack(sig * ff, 9, rng).mean(axis=0)
    flat, count = master_flat(stack(ff * 0.6, 9, rng), dark)
    cal = calibrate(lights, dark, flat)
    assert count == 0
    h, w = sig.shape

    def ratio(img):
        return img[:20, :20].mean() / img[h // 2 - 10:h // 2 + 10, w // 2 - 10:w // 2 + 10].mean()

    # signal here: background corner vs centre (lanes avoided? centre may hold bands, so compare to truth)
    true = ratio(sig)
    assert ratio(cal) == pytest.approx(true, rel=0.05)
    assert abs(ratio(lights - dark) - true) > 0.15  # the uncorrected ratio is visibly off


@pytest.mark.parametrize("tile_rows", [7, 10000])
def test_ndarray_vs_memmap_and_tiling(tmp_path, tile_rows):
    rng = np.random.default_rng(3)
    arr = stack(SyntheticGel(height=60, width=80).signal(), 5, rng)
    mm = np.memmap(tmp_path / "s.dat", dtype=np.float32, mode="w+", shape=arr.shape)
    mm[:] = arr
    mm.flush()
    ref = master_dark(arr, tile_rows=10000)
    assert np.array_equal(master_dark(arr, tile_rows), ref)
    assert np.array_equal(master_dark(mm, tile_rows), ref)
    zero = np.zeros(arr.shape[1:], np.float32)
    f_ref, c_ref = master_flat(arr, zero, tile_rows=10000)
    f_mm, c_mm = master_flat(mm, zero, tile_rows=tile_rows)
    assert np.array_equal(f_ref, f_mm) and c_ref == c_mm


def test_dtypes_float32():
    rng = np.random.default_rng(4)
    arr = stack(SyntheticGel(height=40, width=40).signal(), 4, rng)  # even N: median of 2 values
    d = master_dark(arr.astype(np.uint16))
    f, _ = master_flat(arr, np.zeros_like(d))
    assert d.dtype == f.dtype == np.float32
    assert calibrate(arr[0], d, f).dtype == np.float32
    assert calibrate(arr[0].astype(np.uint16), d).dtype == np.float32


def test_calibrate_shape_mismatch():
    with pytest.raises(ValueError, match="Shape mismatch"):
        calibrate(np.zeros((4, 4), np.float32), np.zeros((4, 5), np.float32))
    with pytest.raises(ValueError, match="Shape mismatch"):
        calibrate(np.zeros((4, 4), np.float32), np.zeros((4, 4), np.float32), np.ones((3, 4), np.float32))


def test_master_flat_dead_column_neutralised():
    rng = np.random.default_rng(5)
    ff = SyntheticGel(height=40, width=60).flat_field()
    flats = stack(ff * 0.6, 5, rng)
    flats[:, :, 10] = 2048  # dead column: black level only
    zero = np.full(ff.shape, 2048.0, np.float32)
    flat, count = master_flat(flats, zero)
    assert count == 40
    assert np.all(flat[:, 10] == 1.0)
    assert flat[flat != 1.0].mean() == pytest.approx(1.0, abs=0.05)


@pytest.mark.skipif(not (DARK_DIR.is_dir() and FLAT_DIR.is_dir()), reason="real calibration data missing")
def test_real_data_master_dark_and_flat():
    from gelcam.processing.channel import select_channel
    from gelcam.processing.raw_io import read_raw

    def load(d):
        return np.stack([select_channel(read_raw(p), "R") for p in sorted(d.glob("*.CR2"))[:4]])

    dark = master_dark(load(DARK_DIR))
    assert dark.mean() == pytest.approx(2047.5, abs=5)
    flat, count = master_flat(load(FLAT_DIR), dark)
    print("real flat: dead =", count)
    h, w = flat.shape
    cs = [flat[:50, :50], flat[:50, -50:], flat[-50:, :50], flat[-50:, -50:]]
    centre = flat[h // 2 - 50:h // 2 + 50, w // 2 - 50:w // 2 + 50].mean()
    ratios = [float(c.mean() / centre) for c in cs]
    print("real flat: corner/centre =", ratios, "mean =", flat.mean())
    assert flat.mean() == pytest.approx(1.0, abs=0.01)
    # measured: three corners are almost unlit (cabinet geometry), the brightest one is ~0.7 of the centre
    assert 0.6 < max(ratios) < 0.85


def test_master_dark_noise_is_mean_like():
    rng = np.random.default_rng(7)
    darks = rng.normal(100, 10, (16, 200, 200)).astype(np.float32)
    assert master_dark(darks).std() == pytest.approx(10 / 4, rel=0.08)  # median would give ~3.1
