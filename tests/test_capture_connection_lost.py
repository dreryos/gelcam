"""A capture must fail at once when the camera disappears, not after the full timeout."""

import threading
import time

import pytest

from gelcam.camera import CameraError
from gelcam.camera.edsdk import EdsdkCamera
from gelcam.camera.edsdk import constants as C


class _FakeSdk:
    def EdsSendCommand(self, *_args) -> int:  # noqa: N802 - mirrors the SDK name
        return 0


class _FakeWorker:
    def wait_until(self, predicate, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                return False
            time.sleep(0.005)
        return True


def _camera() -> EdsdkCamera:
    cam = EdsdkCamera()
    cam._sdk = _FakeSdk()  # type: ignore[assignment]
    cam._worker = _FakeWorker()  # type: ignore[assignment]
    cam._connected = True
    return cam


def test_capture_stops_as_soon_as_the_camera_is_gone(tmp_path):
    cam = _camera()
    threading.Timer(0.1, lambda: setattr(cam, "_connected", False)).start()
    t0 = time.monotonic()
    with pytest.raises(CameraError) as exc:
        cam._capture(tmp_path, timeout=30.0)
    assert time.monotonic() - t0 < 5.0
    assert exc.value.code == C.EDS_ERR_COMM_DISCONNECTED


def test_capture_still_times_out_when_the_camera_is_alive(tmp_path):
    cam = _camera()
    with pytest.raises(CameraError, match="timed out"):
        cam._capture(tmp_path, timeout=0.2)


def test_downloads_never_overwrite_existing_frames(tmp_path):
    from gelcam.camera.edsdk.camera import unique_path

    first = tmp_path / "IMG_0001.CR2"
    assert unique_path(first) == first
    first.write_bytes(b"original")
    second = unique_path(first)
    assert second == tmp_path / "IMG_0001_1.CR2"
    second.write_bytes(b"x")
    assert unique_path(first) == tmp_path / "IMG_0001_2.CR2"
    assert first.read_bytes() == b"original"
