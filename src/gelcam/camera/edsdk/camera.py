"""Implementace rozhraní `Camera` nad Canon EDSDK.

Bezpečnostní zásady (viz CLAUDE.md):
- do foťáku se zapisují jen ISO, čas, clona a kvalita obrazu (RAW) a jen
  hodnoty, které foťák sám nabídne v `allowed_values()`; jiné nastavení neměníme,
- jediné další zápisy jsou standardní nastavení hostitele, která používá
  každá aplikace nad EDSDK: SaveTo = Host, kapacita hostitele, výstup live view,
- všechna volání SDK běží ve vlákně `EdsdkWorker`.
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

SHUTDOWN_TIMER_INTERVAL = 60.0  # s; 100D se jinak po nastavené době uspí


class EdsdkCamera:
    def __init__(self, vendor_dir: Path | None = None) -> None:
        self._vendor_dir = vendor_dir
        self._worker: EdsdkWorker | None = None
        self._sdk: Edsdk | None = None
        self._list = c_void_p()
        self._cam = c_void_p()
        self._connected = False
        self._live = False
        self._handlers: list[object] = []  # drží reference na callbacky
        self._capture_dir: Path | None = None
        self._transfers: list[Path] = []
        self._transfer_error: Exception | None = None
        self.warnings: list[str] = []
        self._remembered: dict[Prop, int] = {}

    # ------------------------------------------------------------------ připojení
    def connect(self) -> CameraInfo:
        if self._connected:
            raise CameraError("Foťák už je připojený.")
        blockers = find_blockers()
        self._worker = EdsdkWorker()
        try:
            info = self._worker.call(self._connect)
        except CameraError as exc:
            self._worker.stop()
            self._worker = None
            if blockers and exc.code in (C.EDS_ERR_DEVICE_NOT_FOUND, C.EDS_ERR_COMM_PORT_IS_IN_USE,
                                         C.EDS_ERR_DEVICE_BUSY):
                raise CameraError(f"{exc} Běží aplikace, která může foťák držet: {', '.join(blockers)}. "
                                  "Zavřete ji a zkuste to znovu.", exc.code) from exc
            raise
        except Exception:
            self._worker.stop()
            self._worker = None
            raise
        if blockers:
            self.warnings.append(f"Běží aplikace, která může foťák rušit: {', '.join(blockers)}.")
        return info

    def reconnect(self, attempts: int = 5, delay: float = 2.0) -> CameraInfo:
        """Znovu naváže spojení po uspání, odpojení kabelu nebo vypnutí foťáku.

        Obnoví naposledy nastavené ISO, čas a clonu (jen pokud je foťák stále nabízí).
        """
        remembered = dict(self._remembered)
        try:
            self.disconnect()
        except Exception:  # noqa: BLE001 - spojení už může být mrtvé
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
            raise CameraError(f"Obnovení spojení se nezdařilo: {last}") from last
        for prop, value in remembered.items():
            try:
                self.set(prop, value)
            except CameraError:
                self.warnings.append(f"Po obnovení spojení se nepodařilo vrátit {prop.value}.")
        return info

    def _connect(self) -> CameraInfo:
        sdk = self._sdk = Edsdk(self._vendor_dir)
        check(sdk.EdsInitializeSDK(), "Inicializace EDSDK")
        try:
            return self._open(sdk)
        except BaseException:
            self._abort_connect()  # jinak zůstane SDK inicializované a další pokus selže (chyba 0x2)
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
        check(sdk.EdsGetCameraList(byref(self._list)), "Seznam foťáků")
        count = c_uint32()
        check(sdk.EdsGetChildCount(self._list, byref(count)), "Seznam foťáků")
        if count.value == 0:
            raise CameraError(C.describe_error(C.EDS_ERR_DEVICE_NOT_FOUND), C.EDS_ERR_DEVICE_NOT_FOUND)
        check(sdk.EdsGetChildAtIndex(self._list, 0, byref(self._cam)), "Výběr foťáku")
        dev = EdsDeviceInfo()
        check(sdk.EdsGetDeviceInfo(self._cam, byref(dev)), "Informace o foťáku")

        obj_cb = ObjectEventHandler(self._on_object_event)
        prop_cb = PropertyEventHandler(self._on_property_event)
        state_cb = StateEventHandler(self._on_state_event)
        self._handlers = [obj_cb, prop_cb, state_cb]
        check(sdk.EdsSetObjectEventHandler(self._cam, C.kEdsObjectEvent_All, obj_cb, None), "Události")
        check(sdk.EdsSetPropertyEventHandler(self._cam, C.kEdsPropertyEvent_All, prop_cb, None), "Události")
        check(sdk.EdsSetCameraStateEventHandler(self._cam, C.kEdsStateEvent_All, state_cb, None), "Události")

        check(sdk.EdsOpenSession(self._cam), "Otevření spojení")
        self._connected = True

        # Snímky se posílají do PC; foťák musí znát „volné místo“ na hostiteli.
        self._set_u32(C.kEdsPropID_SaveTo, C.kEdsSaveTo_Host)
        cap = EdsCapacity(0x7FFFFFFF, 0x1000, 1)
        check(sdk.EdsSetCapacity(self._cam, cap), "Nastavení kapacity")

        self._worker.every(SHUTDOWN_TIMER_INTERVAL, self._extend_shutdown_timer)

        self.warnings = []
        if self._get_u32(C.kEdsPropID_AEMode) != C.AE_MODE_MANUAL:
            self.warnings.append("Volič režimů není v poloze M. Přepněte foťák do ručního režimu.")
        try:
            if not values.is_raw_only(self._get_u32(C.kEdsPropID_ImageQuality)):
                self.warnings.append("Foťák neukládá samotné RAW. Aplikace ho před focením přepne na RAW.")
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
            raise CameraError("Foťák není připojený.")
        return self._worker.call(fn, *args, timeout=timeout)

    # ------------------------------------------------------------------ vlastnosti
    def allowed_values(self, prop: Prop) -> list[int]:
        return self._call(self._allowed_values, prop)

    def _allowed_values(self, prop: Prop) -> list[int]:
        if prop not in (Prop.ISO, Prop.TV, Prop.AV, Prop.IMAGE_QUALITY):
            return []
        desc = EdsPropertyDesc()
        check(self._sdk.EdsGetPropertyDesc(self._cam, _PROP_IDS[prop], byref(desc)), "Povolené hodnoty")
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
        check_allowed(self, prop, value)  # znovu čte seznam z foťáku těsně před zápisem
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
        from PIL import Image  # dekódování mimo vlákno SDK

        return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))

    def _evf_jpeg(self) -> bytes | None:
        if not self._live:
            return None
        sdk = self._sdk
        stream, evf = c_void_p(), c_void_p()
        try:
            check(sdk.EdsCreateMemoryStream(0, byref(stream)), "Paměť pro live view")
            check(sdk.EdsCreateEvfImageRef(stream, byref(evf)), "Live view")
            err = sdk.EdsDownloadEvfImage(self._cam, evf)
            if err == C.EDS_ERR_OBJECT_NOTREADY:
                return None
            check(err, "Stažení snímku live view")
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
            raise CameraError("Lupa podporuje jen 1×, 5× a 10×.")
        self._call(self._set_zoom, factor, x, y)

    def _set_zoom(self, factor: int, x: int | None, y: int | None) -> None:
        if x is not None and y is not None:
            pt = EdsPoint(int(x), int(y))
            self._retry_busy(lambda: check(
                self._sdk.EdsSetPropertyData(self._cam, C.kEdsPropID_Evf_ZoomPosition, 0, sizeof(pt), byref(pt)),
                "Poloha lupy"))
        self._retry_busy(lambda: self._set_u32(C.kEdsPropID_Evf_Zoom, factor))

    # ------------------------------------------------------------------ ostření
    def autofocus(self) -> None:
        self._call(self._autofocus, timeout=15)

    def _autofocus(self) -> None:
        if not self._live:
            raise CameraError("Ostření funguje jen v live view.")
        sdk = self._sdk
        self._retry_busy(lambda: check(
            sdk.EdsSendCommand(self._cam, C.kEdsCameraCommand_DoEvfAf, C.kEdsCameraCommand_EvfAf_ON), "Autofokus"))
        try:
            self._worker.wait_until(lambda: False, timeout=2.0)  # nechá AF doběhnout, zpracovává zprávy
        finally:
            sdk.EdsSendCommand(self._cam, C.kEdsCameraCommand_DoEvfAf, C.kEdsCameraCommand_EvfAf_OFF)

    def drive_focus(self, step: FocusStep) -> None:
        self._call(self._drive_focus, step)

    def _drive_focus(self, step: FocusStep) -> None:
        if not self._live:
            raise CameraError("Ostření funguje jen v live view.")
        self._retry_busy(lambda: check(
            self._sdk.EdsSendCommand(self._cam, C.kEdsCameraCommand_DriveLensEvf, _FOCUS_PARAMS[step]),
            "Posun ostření"))

    # ------------------------------------------------------------------ focení
    def capture(self, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        ensure_raw_quality(self)
        tv = values.tv_seconds(int(self.get(Prop.TV)))
        if tv is None:
            raise CameraError("Režim Bulb zatím GelCam nepodporuje. Zvolte čas do 30 s.")
        return self._call(self._capture, dest_dir, tv + 60.0, timeout=tv + 90.0)

    def _capture(self, dest_dir: Path, timeout: float) -> Path:
        sdk = self._sdk
        self._capture_dir = dest_dir
        self._transfers = []
        self._transfer_error = None
        try:
            self._retry_busy(lambda: check(
                sdk.EdsSendCommand(self._cam, C.kEdsCameraCommand_PressShutterButton,
                                   C.kEdsCameraCommand_ShutterButton_Completely_NonAF), "Spoušť"))
            check(sdk.EdsSendCommand(self._cam, C.kEdsCameraCommand_PressShutterButton,
                                     C.kEdsCameraCommand_ShutterButton_OFF), "Spoušť")
            got_any = self._worker.wait_until(lambda: bool(self._transfers) or self._transfer_error is not None,
                                              timeout)
            if self._transfer_error is not None:
                raise self._transfer_error
            if not got_any:
                raise CameraError("Snímek nedorazil do PC (vypršel časový limit).")
            # u RAW+JPEG přijdou dva soubory; počkáme chvíli na CR2
            self._worker.wait_until(lambda: self._raw_path() is not None, 5.0)
            raw = self._raw_path()
            if raw is None:
                names = ", ".join(p.name for p in self._transfers)
                raise CameraError(f"Foťák neposlal RAW (přišlo: {names}). Nastavte kvalitu RAW.")
            return raw
        finally:
            self._capture_dir = None

    def _raw_path(self) -> Path | None:
        return next((p for p in self._transfers if p.suffix.upper() == ".CR2"), None)

    # ------------------------------------------------------------------ události (vlákno SDK)
    def _on_object_event(self, event: int, ref: int, _ctx) -> int:
        item = c_void_p(ref)
        try:
            if event == C.kEdsObjectEvent_DirItemRequestTransfer:
                self._download(item)
        except Exception as exc:  # noqa: BLE001 - výjimka nesmí projít do C
            self._transfer_error = exc
        finally:
            if item.value:
                self._sdk.EdsRelease(item)
        return C.EDS_ERR_OK

    def _download(self, item: c_void_p) -> None:
        sdk = self._sdk
        info = sdk.DirectoryItemInfo()
        check(sdk.EdsGetDirectoryItemInfo(item, byref(info)), "Informace o snímku")
        dest_dir = self._capture_dir or Path.cwd()
        name = info.szFileName.decode(errors="replace") or f"IMG_{int(time.time())}.CR2"
        dest = dest_dir / name
        stream = c_void_p()
        try:
            check(sdk.EdsCreateFileStream(str(dest).encode("mbcs"), C.kEdsFileCreateDisposition_CreateAlways,
                                          C.kEdsAccess_ReadWrite, byref(stream)), "Soubor pro snímek")
            check(sdk.EdsDownload(item, info.size, stream), "Stažení snímku")
            check(sdk.EdsDownloadComplete(item), "Dokončení stažení")
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

    # ------------------------------------------------------------------ pomocné
    def _get_u32(self, prop_id: int) -> int:
        v = c_uint32()
        check(self._sdk.EdsGetPropertyData(self._cam, prop_id, 0, sizeof(v), byref(v)), f"Čtení 0x{prop_id:X}")
        return v.value

    def _set_u32(self, prop_id: int, value: int) -> None:
        v = c_uint32(value)
        check(self._sdk.EdsSetPropertyData(self._cam, prop_id, 0, sizeof(v), byref(v)), f"Zápis 0x{prop_id:X}")

    def _get_str(self, prop_id: int) -> str:
        dtype, size = c_uint32(), c_uint32()
        check(self._sdk.EdsGetPropertySize(self._cam, prop_id, 0, byref(dtype), byref(size)), f"Čtení 0x{prop_id:X}")
        buf = (c_char * max(size.value, 1))()
        check(self._sdk.EdsGetPropertyData(self._cam, prop_id, 0, size.value, buf), f"Čtení 0x{prop_id:X}")
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
