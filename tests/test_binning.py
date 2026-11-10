import numpy as np

from gelcam.processing.binning import bin2x2


def test_bin2x2_exact_values():
    a = np.array([[1, 2, 3, 4], [5, 6, 7, 8]], dtype=np.float32)
    out = bin2x2(a)
    assert out.dtype == np.float32
    assert np.array_equal(out, [[3.5, 5.5]])


def test_bin2x2_odd_sizes_cropped():
    a = np.arange(35, dtype=np.float32).reshape(5, 7)
    out = bin2x2(a)
    assert out.shape == (2, 3)
    assert out[0, 0] == (0 + 1 + 7 + 8) / 4


def test_bin2x2_float32_from_uint16():
    out = bin2x2(np.full((4, 4), 65535, dtype=np.uint16))
    assert out.dtype == np.float32 and np.all(out == 65535)
