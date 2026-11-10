"""Implementation of the `Camera` interface on top of Canon EDSDK.

Safety rules (see CLAUDE.md):
- only ISO, shutter speed, aperture and image quality (RAW) are written to the camera, and only
  values the camera itself offers in `allowed_values()`; no other settings are changed,
- the only other writes are the standard host settings used by every EDSDK application:
  SaveTo = Host, host capacity, live view output,
- all SDK calls run on the `EdsdkWorker` thread.
"""

from __future__ import annotations

import ctypes
import io
import time
from ctypes import byref, c_char, c_uint32, c_uint64, c_void_p, sizeof
from pathlib import Path

import numpy as np

from .. import values
from ..base import CameraError, CameraInfo, FocusStep, Prop, check_allowed, ensure_raw_quality
from .blockers import find_blockers
from . import constants as C
from .binding import EdsCapacity, EdsDeviceInfo, EdsPoint, EdsPropertyDesc, Edsdk, check
from .binding import ObjectEventHandler, PropertyEventHandler, StateEventHandler
from .worker import EdsdkWorker

_PROP_IDS = {
    Prop.ISO: C.kEdsPropID_ISOSpeed,
    Prop.TV: C.kEdsPropID_Tv,
    Prop.AV: C.kEdsPropID_Av,
    Prop.IMAGE_QUALITY: C.kEdsPropID_ImageQuality,
    Prop.AE_MODE: C.kEdsPropID_AEMode,
    Prop.BATTERY: C.kEdsPropID_BatteryLevel,
}

_FOCUS_PARAMS = {
    FocusStep.NEAR_1: C.kEdsEvfDriveLens_Near1,
    FocusStep.NEAR_2: C.kEdsEvfDriveLens_Near2,
    FocusStep.NEAR_3: C.kEdsEvfDriveLens_Near3,
    FocusStep.FAR_1: C.kEdsEvfDriveLens_Far1,
    FocusStep.FAR_2: C.kEdsEvfDriveLens_Far2,
    FocusStep.FAR_3: C.kEdsEvfDriveLens_Far3,
}

SHUTDOWN_TIMER_INTERVAL = 60.0  # s; otherwise the 100D goes to sleep after the set time


class EdsdkCamera:
    def __init__(self, vendor_dir: Path | None = None) -> None:
        self._vendor_dir = vendor_dir
        self._worker: EdsdkWorker | None = None
        self._sdk: Edsdk | None = None
        self._list = c_void_p()
        self._cam = c_void_p()
        self._connected = False
        self._live = False
        self._handlers: list[object] = []  # keeps references to the callbacks
        self._capture_dir: Path | None = None
        self._transfers: list[Path] = []
        self._transfer_error: Exception | None = None
        self.warnings: list[str] = []
        self._remembered: dict[Prop, int] = {}

    # ------------------------------------------------------------------ connection
    def connect(self) -> CameraInfo:
        if self._connected:
            raise CameraError("Camera is already connected.")
        blockers = find_blockers()
        self._worker = EdsdkWorker()
        try:
            info = self._worker.call(self._connect)
        except CameraError as exc:
            self._worker.stop()
            self._worker = None
            if blockers and exc.code in (C.EDS_ERR_DEVICE_NOT_FOUND, C.EDS_ERR_COMM_PORT_IS_IN_USE,
                                         C.EDS_ERR_DEVICE_BUSY):
                raise CameraError(f"{exc} Running application that may hold the camera: {', '.join(blockers)}. "
                                  "Close it and try again.", exc.code) from exc
            raise
        except Exception:
            self._worker.stop()
            self._worker = None
            raise
        if blockers:
            self.warnings.append(f"Running application that may interfere with the camera: {', '.join(blockers)}.")
        return info

    def reconnect(self, attempts: int = 5, delay: float = 2.0) -> CameraInfo:
        """Re-establishes the connection after sleep, cable disconnection or camera power-off.

        Restores the last set ISO, shutter speed and aperture (only if the camera still offers them).
        """
        remembered = dict(self._remembered)
        try:
            self.disconnect()
        except Exception:  # noqa: BLE001 - the connection may already be dead
            self._worker = None
            self._connected = False
        last: Exception | None = None
        for i in range(attempts):
            try:
                info = self.connect()
                break
            except CameraError as exc:
                last = exc
                time.sleep(delay)
        else:
            raise CameraError(f"Reconnection failed: {last}") from last
        for prop, value in remembered.items():
            try:
                self.set(prop, value)
            except CameraError:
                self.warnings.append(f"After reconnecting, {prop.value} could not be restored.")
        return info

    def _connect(self) -> CameraInfo:
        sdk = self._sdk = Edsdk(self._vendor_dir)
        check(sdk.EdsInitializeSDK(), "EDSDK initialization")
        try:
            return self._open(sdk)
        except BaseException:
            self._abort_connect()  # otherwise the SDK stays initialized and the next attempt fails (error 0x2)
            raise

    def _abort_connect(self) -> None:
        sdk = self._sdk
        assert sdk is not None
        if self._connected:
            sdk.EdsCloseSession(self._cam)
        for ref in (self._cam, self._list):
            if ref.value:
                sdk.EdsRelease(ref)
        self._cam, self._list = c_void_p(), c_void_p()
        self._connected = False
        self._live = False
        sdk.EdsTerminateSDK()

    def _open(self, sdk: Edsdk) -> CameraInfo:
        check(sdk.EdsGetCameraList(byref(self._list)), "Camera list")
        count = c_uint32()
        check(sdk.EdsGetChildCount(self._list, byref(count)), "Camera list")
        if count.value == 0:
            raise CameraError(C.describe_error(C.EDS_ERR_DEVICE_NOT_FOUND), C.EDS_ERR_DEVICE_NOT_FOUND)
        check(sdk.EdsGetChildAtIndex(self._list, 0, byref(self._cam)), "Camera selection")
        dev = EdsDeviceInfo()
        check(sdk.EdsGetDeviceInfo(self._cam, byref(dev)), "Camera information")

        obj_cb = ObjectEventHandler(self._on_object_event)
        prop_cb = PropertyEventHandler(self._on_property_event)
        state_cb = StateEventHandler(self._on_state_event)
        self._handlers = [obj_cb, prop_cb, state_cb]
        check(sdk.EdsSetObjectEventHandler(self._cam, C.kEdsObjectEvent_All, obj_cb, None), "Events")
        check(sdk.EdsSetPropertyEventHandler(self._cam, C.kEdsPropertyEvent_All, prop_cb, None), "Events")
        check(sdk.EdsSetCameraStateEventHandler(self._cam, C.kEdsStateEvent_All, state_cb, None), "Events")

        check(sdk.EdsOpenSession(self._cam), "Opening session")
        self._connected = True

        # Images are sent to the PC; the camera must know the free space on the host.
        self._set_u32(C.kEdsPropID_SaveTo, C.kEdsSaveTo_Host)
        cap = EdsCapacity(0x7FFFFFFF, 0x1000, 1)
        check(sdk.EdsSetCapacity(self._cam, cap), "Setting capacity")

        self._worker.every(SHUTDOWN_TIMER_INTERVAL, self._extend_shutdown_timer)

        self.warnings = []
        if self._get_u32(C.kEdsPropID_AEMode) != C.AE_MODE_MANUAL:
            self.warnings.append("Mode dial is not in M. Switch the camera to manual mode.")
        try:
            if not values.is_raw_only(self._get_u32(C.kEdsPropID_ImageQuality)):
                self.warnings.append("Camera is not saving RAW only. The application will switch it to RAW before shooting.")
        except CameraError:
            pass

        return CameraInfo(
            model=self._get_str(C.kEdsPropID_ProductName),
            port=dev.szPortName.decode(errors="replace"),
            serial=self._try_str(C.kEdsPropID_BodyIDEx),
        )

    def disconnect(self) -> None:
        if self._worker is None:
            return
        try:
            self._worker.call(self._disconnect, timeout=10)
        finally:
            self._worker.stop()
            self._worker = None

    def _disconnect(self) -> None:
        sdk = self._sdk
        assert sdk is not None
        if self._live:
            try:
                self._stop_live_view()
            except CameraError:
                pass
        if self._connected:
            sdk.EdsCloseSession(self._cam)
        for ref in (self._cam, self._list):
            if ref.value:
                sdk.EdsRelease(ref)
        self._cam, self._list = c_void_p(), c_void_p()
        self._connected = False
        sdk.EdsTerminateSDK()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _call(self, fn, *args, timeout: float | None = 30.0):
        if self._worker is None or not self._connected:
            raise CameraError("Camera is not connected.")
        return self._worker.call(fn, *args, timeout=timeout)

    # ------------------------------------------------------------------ properties
    def allowed_values(self, prop: Prop) -> list[int]:
        return self._call(self._allowed_values, prop)

    def _allowed_values(self, prop: Prop) -> list[int]:
        if prop not in (Prop.ISO, Prop.TV, Prop.AV, Prop.IMAGE_QUALITY):
            return []
        desc = EdsPropertyDesc()
        check(self._sdk.EdsGetPropertyDesc(self._cam, _PROP_IDS[prop], byref(desc)), "Allowed values")
        return [v & 0xFFFFFFFF for v in desc.propDesc[: desc.numElements]]

    def get(self, prop: Prop) -> int | str:
        return self._call(self._get, prop)

    def _get(self, prop: Prop) -> int | str:
        if prop is Prop.PRODUCT_NAME:
            return self._get_str(C.kEdsPropID_ProductName)
        return self._get_u32(_PROP_IDS[prop])

    def set(self, prop: Prop, value: int) -> None:
        self._call(self._set, prop, value)

    def _set(self, prop: Prop, value: int) -> None:
        check_allowed(self, prop, value)  # re-reads the list from the camera just before writing
        self._retry_busy(lambda: self._set_u32(_PROP_IDS[prop], value))
        if prop in (Prop.ISO, Prop.TV, Prop.AV):
            self._remembered[prop] = value

    # ------------------------------------------------------------------ live view
    def start_live_view(self) -> None:
        self._call(self._start_live_view)

    def _start_live_view(self) -> None:
        dev = self._get_u32(C.kEdsPropID_Evf_OutputDevice)
        self._retry_busy(lambda: self._set_u32(C.kEdsPropID_Evf_OutputDevice, dev | C.kEdsEvfOutputDevice_PC))
        self._live = True

    def stop_live_view(self) -> None:
        if self._connected:
            self._call(self._stop_live_view)

    def _stop_live_view(self) -> None:
        dev = self._get_u32(C.kEdsPropID_Evf_OutputDevice)
        self._retry_busy(lambda: self._set_u32(C.kEdsPropID_Evf_OutputDevice, dev & ~C.kEdsEvfOutputDevice_PC))
        self._live = False

    def live_view_frame(self) -> np.ndarray | None:
        data = self._call(self._evf_jpeg, timeout=10)
        if data is None:
            return None
        from PIL import Image  # decoding outside the SDK thread

        return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))

    def _evf_jpeg(self) -> bytes | None:
        if not self._live:
            return None
        sdk = self._sdk
        stream, evf = c_void_p(), c_void_p()
        try:
            check(sdk.EdsCreateMemoryStream(0, byref(stream)), "Memory for live view")
            check(sdk.EdsCreateEvfImageRef(stream, byref(evf)), "Live view")
            err = sdk.EdsDownloadEvfImage(self._cam, evf)
            if err == C.EDS_ERR_OBJECT_NOTREADY:
                return None
            check(err, "Downloading live view frame")
            ptr, length = c_void_p(), c_uint64()
            check(sdk.EdsGetPointer(stream, byref(ptr)), "Live view")
            check(sdk.EdsGetLength(stream, byref(length)), "Live view")
            return ctypes.string_at(ptr, length.value)
        finally:
            for ref in (evf, stream):
                if ref.value:
                    sdk.EdsRelease(ref)

    def set_live_view_zoom(self, factor: int, x: int | None = None, y: int | None = None) -> None:
        if factor not in (1, 5, 10):
            raise CameraError("Zoom supports only 1×, 5× and 10×.")
        self._call(self._set_zoom, factor, x, y)

    def _set_zoom(self, factor: int, x: int | None, y: int | None) -> None:
        if x is not None and y is not None:
            pt = EdsPoint(int(x), int(y))
            self._retry_busy(lambda: check(
                self._sdk.EdsSetPropertyData(self._cam, C.kEdsPropID_Evf_ZoomPosition, 0, sizeof(pt), byref(pt)),
                "Zoom position"))
        self._retry_busy(lambda: self._set_u32(C.kEdsPropID_Evf_Zoom, factor))

    # ------------------------------------------------------------------ focus
    def autofocus(self) -> None:
        self._call(self._autofocus, timeout=15)

    def _autofocus(self) -> None:
        if not self._live:
            raise CameraError("Focus works only in live view.")
        sdk = self._sdk
        self._retry_busy(lambda: check(
            sdk.EdsSendCommand(self._cam, C.kEdsCameraCommand_DoEvfAf, C.kEdsCameraCommand_EvfAf_ON), "Autofocus"))
        try:
            self._worker.wait_until(lambda: False, timeout=2.0)  # lets AF finish while processing messages
        finally:
            sdk.EdsSendCommand(self._cam, C.kEdsCameraCommand_DoEvfAf, C.kEdsCameraCommand_EvfAf_OFF)

    def drive_focus(self, step: FocusStep) -> None:
        self._call(self._drive_focus, step)

    def _drive_focus(self, step: FocusStep) -> None:
        if not self._live:
            raise CameraError("Focus works only in live view.")
        self._retry_busy(lambda: check(
            self._sdk.EdsSendCommand(self._cam, C.kEdsCameraCommand_DriveLensEvf, _FOCUS_PARAMS[step]),
            "Focus step"))

    # ------------------------------------------------------------------ capture
    def capture(self, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        ensure_raw_quality(self)
        tv = values.tv_seconds(int(self.get(Prop.TV)))
        if tv is None:
            raise CameraError("GelCam does not support Bulb mode yet. Choose a shutter speed up to 30 s.")
        return self._call(self._capture, dest_dir, tv + 60.0, timeout=tv + 90.0)

    def _capture(self, dest_dir: Path, timeout: float) -> Path:
        sdk = self._sdk
        self._capture_dir = dest_dir
        self._transfers = []
        self._transfer_error = None
        try:
            self._retry_busy(lambda: check(
                sdk.EdsSendCommand(self._cam, C.kEdsCameraCommand_PressShutterButton,
                                   C.kEdsCameraCommand_ShutterButton_Completely_NonAF), "Shutter"))
            check(sdk.EdsSendCommand(self._cam, C.kEdsCameraCommand_PressShutterButton,
                                     C.kEdsCameraCommand_ShutterButton_OFF), "Shutter")
            got_any = self._worker.wait_until(lambda: bool(self._transfers) or self._transfer_error is not None,
                                              timeout)
            if self._transfer_error is not None:
                raise self._transfer_error
            if not got_any:
                raise CameraError("Image did not arrive at the PC (timed out).")
            # with RAW+JPEG two files arrive; wait briefly for the CR2
            self._worker.wait_until(lambda: self._raw_path() is not None, 5.0)
            raw = self._raw_path()
            if raw is None:
                names = ", ".join(p.name for p in self._transfers)
                raise CameraError(f"Camera did not send RAW (received: {names}). Set image quality to RAW.")
            return raw
        finally:
            self._capture_dir = None

    def _raw_path(self) -> Path | None:
        return next((p for p in self._transfers if p.suffix.upper() == ".CR2"), None)

    # ------------------------------------------------------------------ events (SDK thread)
    def _on_object_event(self, event: int, ref: int, _ctx) -> int:
        item = c_void_p(ref)
        try:
            if event == C.kEdsObjectEvent_DirItemRequestTransfer:
                self._download(item)
        except Exception as exc:  # noqa: BLE001 - exception must not propagate into C
            self._transfer_error = exc
        finally:
            if item.value:
                self._sdk.EdsRelease(item)
        return C.EDS_ERR_OK

    def _download(self, item: c_void_p) -> None:
        sdk = self._sdk
        info = sdk.DirectoryItemInfo()
        check(sdk.EdsGetDirectoryItemInfo(item, byref(info)), "Image information")
        dest_dir = self._capture_dir or Path.cwd()
        name = info.szFileName.decode(errors="replace") or f"IMG_{int(time.time())}.CR2"
        dest = dest_dir / name
        stream = c_void_p()
        try:
            check(sdk.EdsCreateFileStream(str(dest).encode("mbcs"), C.kEdsFileCreateDisposition_CreateAlways,
                                          C.kEdsAccess_ReadWrite, byref(stream)), "File for image")
            check(sdk.EdsDownload(item, info.size, stream), "Downloading image")
            check(sdk.EdsDownloadComplete(item), "Completing download")
        except Exception:
            sdk.EdsDownloadCancel(item)
            raise
        finally:
            if stream.value:
                sdk.EdsRelease(stream)
        self._transfers.append(dest)

    def _on_property_event(self, event: int, prop_id: int, param: int, _ctx) -> int:
        return C.EDS_ERR_OK

    def _on_state_event(self, event: int, param: int, _ctx) -> int:
        if event == C.kEdsStateEvent_Shutdown:
            self._connected = False
            self._live = False
        elif event == C.kEdsStateEvent_WillSoonShutDown:
            self._extend_shutdown_timer()
        return C.EDS_ERR_OK

    def _extend_shutdown_timer(self) -> None:
        if self._connected:
            self._sdk.EdsSendCommand(self._cam, C.kEdsCameraCommand_ExtendShutDownTimer, 0)

    # ------------------------------------------------------------------ helpers
    def _get_u32(self, prop_id: int) -> int:
        v = c_uint32()
        check(self._sdk.EdsGetPropertyData(self._cam, prop_id, 0, sizeof(v), byref(v)), f"Read 0x{prop_id:X}")
        return v.value

    def _set_u32(self, prop_id: int, value: int) -> None:
        v = c_uint32(value)
        check(self._sdk.EdsSetPropertyData(self._cam, prop_id, 0, sizeof(v), byref(v)), f"Write 0x{prop_id:X}")

    def _get_str(self, prop_id: int) -> str:
        dtype, size = c_uint32(), c_uint32()
        check(self._sdk.EdsGetPropertySize(self._cam, prop_id, 0, byref(dtype), byref(size)), f"Read 0x{prop_id:X}")
        buf = (c_char * max(size.value, 1))()
        check(self._sdk.EdsGetPropertyData(self._cam, prop_id, 0, size.value, buf), f"Read 0x{prop_id:X}")
        return buf.value.decode(errors="replace")

    def _try_str(self, prop_id: int) -> str:
        try:
            return self._get_str(prop_id)
        except CameraError:
            return ""

    def _retry_busy(self, fn, attempts: int = 20, delay: float = 0.1):
        from ..base import CameraBusyError

        for i in range(attempts):
            try:
                return fn()
            except CameraBusyError:
                if i == attempts - 1:
                    raise
                self._worker.wait_until(lambda: False, timeout=delay)
