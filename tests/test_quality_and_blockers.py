import pytest

from gelcam.camera import CameraError, MockCamera, Prop, ValueNotAllowedError, ensure_raw_quality, values
from gelcam.camera.edsdk.blockers import parse_tasklist

LR, LRLJF, LJF = 0x64FF0F, 0x640013, 0x13FF0F


def test_quality_classification():
    assert values.is_raw_only(LR)
    assert not values.is_raw_only(LRLJF) and values.has_raw(LRLJF)
    assert not values.has_raw(LJF)
    assert values.is_raw_only(0x0164FF0F)  # M-RAW je taky jen RAW
    assert values.quality_label(LR) == "RAW"
    assert values.quality_label(LRLJF) == "RAW + JPEG"
    assert values.quality_label(LJF) == "JPEG"


def test_preferred_raw_prefers_full_size():
    assert values.preferred_raw_quality([LJF, LRLJF, 0x0164FF0F, LR]) == LR
    assert values.preferred_raw_quality([0x0164FF0F]) == 0x0164FF0F
    assert values.preferred_raw_quality([LJF, LRLJF]) is None


def test_ensure_raw_switches_from_jpeg():
    cam = MockCamera()
    cam.connect()
    cam.set(Prop.IMAGE_QUALITY, LJF)
    assert ensure_raw_quality(cam) == LR
    assert cam.get(Prop.IMAGE_QUALITY) == LR
    assert ensure_raw_quality(cam) is None  # už RAW, nic se nemění


def test_quality_set_only_allowed():
    cam = MockCamera()
    cam.connect()
    with pytest.raises(ValueNotAllowedError):
        cam.set(Prop.IMAGE_QUALITY, 0x1234)


def test_ensure_raw_without_raw_option():
    class NoRaw(MockCamera):
        def allowed_values(self, prop):
            return [LJF] if prop is Prop.IMAGE_QUALITY else super().allowed_values(prop)

    cam = NoRaw()
    cam.connect()
    cam._values[Prop.IMAGE_QUALITY] = LJF
    with pytest.raises(CameraError):
        ensure_raw_quality(cam)


def test_capture_forces_raw(tmp_path):
    cam = MockCamera()
    cam.connect()
    cam.set(Prop.IMAGE_QUALITY, LJF)
    cam.capture(tmp_path)
    assert cam.get(Prop.IMAGE_QUALITY) == LR


def test_parse_tasklist():
    out = '"System","4","Services","0","1 K"\n"EOS Utility.exe","123","Console","1","9 K"\n"digiCamControl.exe","5","Console","1","1 K"\n'
    assert parse_tasklist(out) == ["EOS Utility", "digiCamControl"]
    assert parse_tasklist("") == []
