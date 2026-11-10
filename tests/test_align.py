import time
from pathlib import Path

import numpy as np
import pytest

from gelcam.processing.align import estimate_shift, needs_alignment, shift_image
from gelcam.testing.synthetic import SyntheticGel, expose

# lane brightness is kept within a factor of 2: a strong brightness gradient across the
# windowed crop would bias any windowed phase correlation
SIG = SyntheticGel(height=480, width=720, lane_scale=(1.0, 0.8, 1.0, 0.7, 1.0, 0.9, 0.6, 1.0)).signal()
SIG_F = SIG.astype(np.float32)


def noisy(sig: np.ndarray, seed: int) -> np.ndarray:
    return expose(sig, np.random.default_rng(seed)).astype(np.float32)


@pytest.mark.parametrize("s", [(3, -7), (-12, 5)])
def test_integer_shift_recovered(s):
    ref = noisy(SIG, 1)
    img = noisy(np.roll(SIG, s, axis=(0, 1)), 2)
    dy, dx = estimate_shift(ref, img)
    assert (dy, dx) == pytest.approx((-s[0], -s[1]), abs=0.1)


def test_subpixel_shift_recovered():
    ref = noisy(SIG, 1)
    img = noisy(shift_image(SIG, 0.4, -1.3), 2)
    dy, dx = estimate_shift(ref, img)
    assert (dy, dx) == pytest.approx((-0.4, 1.3), abs=0.15)


def test_identical_frames_zero_shift():
    ref = noisy(SIG, 1)
    dy, dx = estimate_shift(ref, ref)
    assert abs(dy) < 0.05 and abs(dx) < 0.05


def test_noise_only_does_not_need_alignment():
    dy, dx = estimate_shift(noisy(SIG, 1), noisy(SIG, 2))
    assert not needs_alignment(dy, dx)


def test_needs_alignment_threshold():
    assert needs_alignment(0.6, 0) and needs_alignment(0, -0.6)
    assert not needs_alignment(0.5, -0.5)


def test_shift_image_integer_equals_roll():
    out = shift_image(SIG_F, 3, -7)
    assert out.dtype == np.float32
    np.testing.assert_array_equal(out[3:, :-7], np.roll(SIG_F, (3, -7), axis=(0, 1))[3:, :-7])


def test_shift_image_edge_replicated():
    out = shift_image(SIG_F, 2, 0)
    np.testing.assert_array_equal(out[0], SIG_F[0])


def test_shift_image_roundtrip():
    back = shift_image(shift_image(SIG_F, 2.3, -1.7), -2.3, 1.7)
    err = np.abs(back[10:-10, 10:-10] - SIG_F[10:-10, 10:-10]).max()
    assert err < 0.05 * float(np.ptp(SIG_F))


def test_estimate_shift_speed():
    rng = np.random.default_rng(0)
    a = rng.random((1738, 2604), dtype=np.float32)
    b = rng.random((1738, 2604), dtype=np.float32)
    estimate_shift(a, b)
    t = time.perf_counter()
    estimate_shift(a, b)
    assert time.perf_counter() - t < 1.0


SCENE = Path(__file__).resolve().parents[1] / "testdata" / "calib" / "2026-11-04_scene_4s_iso100_uv100"


@pytest.mark.skipif(not SCENE.exists(), reason="real data missing")
def test_real_scene_frames_static():
    from gelcam.processing.channel import select_channel
    from gelcam.processing.raw_io import read_raw

    fr = [select_channel(read_raw(p), "R") for p in sorted(SCENE.glob("*.CR2"))[:3]]
    for k in (1, 2):
        s = estimate_shift(fr[0], fr[k])
        print("real shift", k, s)
        assert not needs_alignment(*s)
