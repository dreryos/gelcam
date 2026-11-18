"""RAW sharpness: separates blurred from sharp frames, independent of the exposure; focus assessment."""

import cv2
import numpy as np
import pytest

from gelcam.processing.focus import BLUR_LIMIT, assess_focus, raw_sharpness


def _scene(h=480, w=640, seed=0):
    rng = np.random.default_rng(seed)
    img = np.full((h, w), 0.2)
    for x in range(40, w, 70):  # lanes of bright bars
        img[100:380, x:x + 6] = 1.0
    img[::40, :] = 0.7
    return img + rng.normal(0, 0.0, img.shape)


def _expose(signal, level, rng, gain=1.0):
    return rng.poisson(np.clip(signal * level, 0, None)).astype(np.float32) * gain


def test_sharp_is_much_sharper_than_blurred_at_both_exposures():
    rng = np.random.default_rng(1)
    sharp, blurred = _scene(), cv2.GaussianBlur(_scene(), (0, 0), 6)
    for level in (700, 1400):
        ratio = raw_sharpness(_expose(sharp, level, rng)) / raw_sharpness(_expose(blurred, level, rng))
        assert ratio > 5


def test_exposure_time_does_not_change_the_value_of_a_sharp_frame():
    rng = np.random.default_rng(2)
    scene = _scene()
    a = raw_sharpness(_expose(scene, 700, rng))
    b = raw_sharpness(_expose(scene, 1400, rng))
    assert b / a == pytest.approx(1.0, abs=0.15)


def test_constant_or_dark_plane_is_zero():
    assert raw_sharpness(np.zeros((64, 64))) == 0.0
    assert raw_sharpness(np.full((64, 64), 500.0)) == pytest.approx(0.0, abs=1e-9)


def test_assess_focus_series_vs_reference():
    ok = assess_focus(1.0, [0.95, 1.0, 1.05, 0.98])
    assert not ok.series_blurred and ok.blurry_frames == () and ok.series_vs_reference == pytest.approx(0.99, abs=0.02)
    blurred = assess_focus(1.0, [0.3, 0.32, 0.29, 0.31])
    assert blurred.series_blurred and blurred.series_vs_reference < BLUR_LIMIT


def test_assess_focus_finds_single_blurry_frame():
    a = assess_focus(1.0, [1.0, 1.0, 0.3, 1.0, 1.0])
    assert a.blurry_frames == (3,) and a.worst_vs_series == pytest.approx(0.3)
    assert not a.series_blurred


def test_assess_focus_without_reference_or_with_short_series():
    a = assess_focus(None, [1.0, 1.0, 0.2])
    assert a.series_vs_reference is None and a.blurry_frames == (3,)
    b = assess_focus(1.0, [1.0, 0.2])  # two frames: no "rest of the series"
    assert b.blurry_frames == () and b.worst_vs_series is None
    assert assess_focus(1.0, []).series_vs_reference is None
