from pathlib import Path

import numpy as np
import pytest

from gelcam.processing.channel import saturation_mask, select_channel
from gelcam.processing.raw_io import RawFrame, read_raw

REAL = Path(__file__).resolve().parents[1] / "testdata" / "edsdk_smoke" / "IMG_0001.CR2"


def make_frame(h: int = 8, w: int = 8, pattern=((0, 1), (3, 2)), white: int = 1000) -> RawFrame:
    """RGGB mosaic where each pixel carries a unique value (row*100 + column)."""
    yy, xx = np.mgrid[0:h, 0:w]
    mosaic = (yy * 100 + xx).astype(np.uint16)
    pat = np.array(pattern, dtype=np.uint8)
    colors = np.tile(pat, (h // 2, w // 2))
    return RawFrame(mosaic, colors, "RGBG", (10.0, 10.0, 10.0, 12.0), white)


def test_red_channel_is_exact_pixels_no_interpolation():
    f = make_frame()
    r = select_channel(f, "R")
    assert r.shape == (4, 4)
    # R is at the top left of the cell: pixels (0,0), (0,2), (2,0) …
    assert r[0, 0] == f.mosaic[0, 0] and r[1, 2] == f.mosaic[2, 4]
    assert np.array_equal(r, f.mosaic[0::2, 0::2])


def test_blue_channel_position():
    f = make_frame()
    assert np.array_equal(select_channel(f, "B"), f.mosaic[1::2, 1::2])


def test_green_is_mean_of_two_green_pixels():
    f = make_frame()
    g = select_channel(f, "G")
    expected = (f.mosaic[0::2, 1::2].astype(np.float32) + f.mosaic[1::2, 0::2]) / 2
    assert np.allclose(g, expected)


def test_other_cfa_phase():
    f = make_frame(pattern=((1, 0), (2, 3)))  # GRBG
    assert np.array_equal(select_channel(f, "R"), f.mosaic[0::2, 1::2])


def test_odd_size_is_cropped_to_even():
    f = make_frame(8, 8)
    odd = RawFrame(f.mosaic[:7, :7], f.colors[:7, :7], f.color_desc, f.black_levels, f.white_level)
    assert select_channel(odd, "R").shape == (3, 3)


def test_input_is_not_modified():
    f = make_frame()
    before = f.mosaic.copy()
    select_channel(f, "G")
    saturation_mask(f, "R")
    assert np.array_equal(f.mosaic, before)


def test_saturation_mask_and_black_level():
    f = make_frame(white=300)
    m = saturation_mask(f, "R")
    assert m.shape == (4, 4)
    assert not m[0, 0] and m[3, 3]  # R at (6,6) = 606 >= 300
    assert f.black_level("G") == 11.0  # mean of two G
    with pytest.raises(ValueError):
        select_channel(f, "X")


@pytest.mark.skipif(not REAL.exists(), reason="testdata/ missing (not committed)")
def test_real_cr2():
    f = read_raw(REAL)
    assert f.mosaic.dtype == np.uint16 and f.mosaic.shape == (3476, 5208)
    assert f.color_desc == "RGBG"
    assert set(np.unique(f.cfa_pattern)) == {0, 1, 2, 3}
    r, g = select_channel(f, "R"), select_channel(f, "G")
    assert r.shape == g.shape == (1738, 2604)
    assert 0 < f.white_level < 16384 and all(2000 < b < 2100 for b in f.black_levels)
