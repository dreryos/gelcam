import pytest

from gelcam.camera import values


@pytest.mark.parametrize("code,iso", [(0x48, 100), (0x4B, 125), (0x50, 200), (0x58, 400), (0x60, 800),
                                      (0x68, 1600), (0x70, 3200), (0x78, 6400), (0x80, 12800)])
def test_iso(code, iso):
    assert values.iso_value(code) == iso


def test_iso_auto():
    assert values.iso_value(0x00) is None
    assert values.iso_label(0x00) == "ISO Auto"


@pytest.mark.parametrize("code,label", [(0x10, '30"'), (0x18, '15"'), (0x38, '1"'), (0x30, '2"'),
                                        (0x40, '0.5"'), (0x48, "1/4"), (0x60, "1/30"), (0x70, "1/125"),
                                        (0x98, "1/4000"), (0x0C, "Bulb")])
def test_tv(code, label):
    assert values.tv_label(code) == label


def test_tv_seconds():
    assert values.tv_seconds(0x10) == 30
    assert values.tv_seconds(0x38) == 1
    assert values.tv_seconds(0x0C) is None


@pytest.mark.parametrize("code,f", [(0x20, 2.8), (0x28, 4.0), (0x30, 5.6), (0x35, 7.1), (0x38, 8.0),
                                    (0x40, 11.0), (0x48, 16.0), (0x50, 22.0)])
def test_av(code, f):
    assert values.av_fnumber(code) == f
