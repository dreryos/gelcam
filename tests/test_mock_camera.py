from pathlib import Path

import numpy as np
import pytest

from gelcam.camera import Camera, CameraError, FocusStep, MockCamera, Prop, ValueNotAllowedError


@pytest.fixture
def cam():
    c = MockCamera(seed=1)
    c.connect()
    yield c
    c.disconnect()


def test_is_camera(cam):
    assert isinstance(cam, Camera)


def test_requires_connection():
    with pytest.raises(CameraError):
        MockCamera().get(Prop.ISO)


def test_set_only_allowed(cam):
    allowed = cam.allowed_values(Prop.ISO)
    cam.set(Prop.ISO, allowed[-1])
    assert cam.get(Prop.ISO) == allowed[-1]
    with pytest.raises(ValueNotAllowedError):
        cam.set(Prop.ISO, 0x49)  # kód, který foťák nenabízí


def test_read_only_props(cam):
    with pytest.raises(ValueNotAllowedError):
        cam.set(Prop.AE_MODE, 3)


def test_live_view_and_zoom(cam):
    assert cam.live_view_frame() is None
    cam.start_live_view()
    frame = cam.live_view_frame()
    assert frame is not None and frame.dtype == np.uint8 and frame.ndim == 3
    cam.set_live_view_zoom(10)
    assert cam.live_view_frame().shape == frame.shape
    with pytest.raises(CameraError):
        cam.set_live_view_zoom(3)


def test_focus_only_in_live_view(cam):
    with pytest.raises(CameraError):
        cam.autofocus()
    cam.start_live_view()
    before = cam.defocus
    cam.autofocus()
    assert cam.defocus < before
    cam.drive_focus(FocusStep.FAR_3)
    assert cam.defocus > 1.5


def test_capture_synthetic(cam, tmp_path: Path):
    p = cam.capture(tmp_path)
    data = np.load(p)
    assert data.dtype == np.uint16 and data.max() <= 15000


def test_capture_from_source(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "A.CR2").write_bytes(b"raw-a")
    (src / "B.CR2").write_bytes(b"raw-b")
    cam = MockCamera(src)
    cam.connect()
    out = tmp_path / "out"
    first, second, third = (cam.capture(out) for _ in range(3))
    assert first.read_bytes() == b"raw-a" and second.read_bytes() == b"raw-b" and third.read_bytes() == b"raw-a"
    assert first.suffix == ".CR2"
