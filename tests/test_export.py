import numpy as np
import pytest

from gelcam.processing.export import write_preview_png, write_result_tiff


def test_result_tiff_clips_rounds_and_reports(tmp_path):
    tifffile = pytest.importorskip("tifffile")
    img = np.array([[-5.0, 0.4], [1.6, 70000.0]], dtype=np.float32)
    info = write_result_tiff(tmp_path / "result.tif", img)
    out = tifffile.imread(tmp_path / "result.tif")
    assert out.dtype == np.uint16 and out.tolist() == [[0, 0], [2, 65535]]
    assert info == {"file": "result.tif", "dtype": "uint16", "units": "ADU above master dark",
                    "shape": [2, 2], "clipped_low": 1, "clipped_high": 1}


def test_never_overwrites(tmp_path):
    img = np.zeros((4, 4), np.float32)
    write_result_tiff(tmp_path / "r.tif", img)
    write_preview_png(tmp_path / "p.png", img)
    with pytest.raises(FileExistsError):
        write_result_tiff(tmp_path / "r.tif", img)
    with pytest.raises(FileExistsError):
        write_preview_png(tmp_path / "p.png", img)


def test_preview_stretch_and_invert(tmp_path):
    from PIL import Image

    img = np.linspace(0, 1000, 100 * 100, dtype=np.float32).reshape(100, 100)
    d = write_preview_png(tmp_path / "a.png", img)
    inv = write_preview_png(tmp_path / "b.png", img, invert=True)
    a, b = np.asarray(Image.open(tmp_path / "a.png")), np.asarray(Image.open(tmp_path / "b.png"))
    assert a.dtype == np.uint8 and a.shape == (100, 100)
    assert a[0, 0] == 0 and a[-1, -1] == 255 and (a.astype(int) + b == 255).all()
    assert d["inverted"] is False and inv["inverted"] is True and d["black"] < d["white"]
