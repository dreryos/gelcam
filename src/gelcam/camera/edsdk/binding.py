"""Thin ctypes binding over EDSDK.dll.

The module can be imported outside Windows (for tests); the library is loaded
only when `load()` is called. All EDSDK calls may run only on the
`EdsdkWorker` thread (see worker.py).
"""

from __future__ import annotations

import ctypes
import os
import re
import sys
from ctypes import POINTER, Structure, byref, c_char, c_char_p, c_int32, c_uint32, c_uint64, c_void_p
from pathlib import Path

from . import constants as C

EdsError = c_uint32
EdsBaseRef = c_void_p
EdsUInt32 = c_uint32
EdsInt32 = c_int32
EdsBool = c_int32

if sys.platform == "win32":
    _FUNCTYPE = ctypes.WINFUNCTYPE  # EDSAPI = __stdcall (no difference on x64)
else:  # pragma: no cover - only for importing outside Windows
    _FUNCTYPE = ctypes.CFUNCTYPE

ObjectEventHandler = _FUNCTYPE(EdsError, EdsUInt32, EdsBaseRef, c_void_p)
PropertyEventHandler = _FUNCTYPE(EdsError, EdsUInt32, EdsUInt32, EdsUInt32, c_void_p)
StateEventHandler = _FUNCTYPE(EdsError, EdsUInt32, EdsUInt32, c_void_p)


class EdsDeviceInfo(Structure):
    _fields_ = [
        ("szPortName", c_char * 256),
        ("szDeviceDescription", c_char * 256),
        ("deviceSubType", EdsUInt32),
        ("reserved", EdsUInt32),
    ]


class EdsPropertyDesc(Structure):
    _fields_ = [
        ("form", EdsInt32),
        ("access", EdsInt32),
        ("numElements", EdsInt32),
        ("propDesc", EdsInt32 * 128),
    ]


class EdsCapacity(Structure):
    _fields_ = [
        ("numberOfFreeClusters", EdsInt32),
        ("bytesPerSector", EdsInt32),
        ("reset", EdsBool),
    ]


class EdsPoint(Structure):
    _fields_ = [("x", EdsInt32), ("y", EdsInt32)]


def _diritem_struct(size_type: type) -> type[Structure]:
    class EdsDirectoryItemInfo(Structure):
        _fields_ = [
            ("size", size_type),
            ("isFolder", EdsBool),
            ("groupID", EdsUInt32),
            ("option", EdsUInt32),
            ("szFileName", c_char * 256),
            ("format", EdsUInt32),
            ("dateTime", EdsUInt32),
        ]

    return EdsDirectoryItemInfo


def diritem_size_is_64bit(header_dir: Path | None) -> bool:
    """Newer EDSDK (13.x) use `EdsUInt64 size`, older ones use `EdsUInt32 size`.

    The header decides if it is available; otherwise the newer SDK is assumed.
    """
    if header_dir is None:
        return True
    types_h = header_dir / "EDSDKTypes.h"
    if not types_h.exists():
        return True
    text = types_h.read_text(encoding="latin-1")
    m = re.search(r"typedef\s+struct\s+tagEdsDirectoryItemInfo\s*\{(.*?)\}", text, re.S)
    if not m:
        return True
    first = m.group(1).strip().splitlines()[0]
    return "UInt64" in first


def default_vendor_dir() -> Path:
    """`vendor/edsdk` next to the sources, or next to the exe in a packaged build."""
    env = os.environ.get("GELCAM_EDSDK_DIR")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "edsdk"
    return Path(__file__).resolve().parents[4] / "vendor" / "edsdk"


class Edsdk:
    """Loaded library with function signatures."""

    def __init__(self, vendor_dir: Path | None = None) -> None:
        vendor_dir = vendor_dir or default_vendor_dir()
        dll_dir = vendor_dir / "Dll" if (vendor_dir / "Dll").exists() else vendor_dir
        dll_path = dll_dir / "EDSDK.dll"
        if sys.platform != "win32":
            raise OSError("The Windows EDSDK can only be loaded on Windows.")
        if not dll_path.exists():
            raise FileNotFoundError(
                f"Not found: {dll_path}. Copy the 64-bit DLLs from EDSDK into vendor/edsdk/Dll/."
            )
        if ctypes.sizeof(c_void_p) != 8:
            raise OSError("GelCam requires 64-bit Python (EDSDK_64).")
        os.add_dll_directory(str(dll_dir))  # EdsImage.dll is loaded from the same folder
        self.dll = ctypes.WinDLL(str(dll_path))  # type: ignore[attr-defined]
        header_dir = vendor_dir / "Header"
        self.DirectoryItemInfo = _diritem_struct(
            c_uint64 if diritem_size_is_64bit(header_dir if header_dir.exists() else None) else c_uint32
        )
        self._declare()

    def _fn(self, name: str, *argtypes) -> None:
        f = getattr(self.dll, name)
        f.argtypes = list(argtypes)
        f.restype = EdsError
        setattr(self, name, f)

    def _declare(self) -> None:
        P = POINTER
        self._fn("EdsInitializeSDK")
        self._fn("EdsTerminateSDK")
        self._fn("EdsRelease", EdsBaseRef)
        self._fn("EdsGetCameraList", P(EdsBaseRef))
        self._fn("EdsGetChildCount", EdsBaseRef, P(EdsUInt32))
        self._fn("EdsGetChildAtIndex", EdsBaseRef, EdsInt32, P(EdsBaseRef))
        self._fn("EdsGetDeviceInfo", EdsBaseRef, P(EdsDeviceInfo))
        self._fn("EdsOpenSession", EdsBaseRef)
        self._fn("EdsCloseSession", EdsBaseRef)
        self._fn("EdsGetPropertySize", EdsBaseRef, EdsUInt32, EdsInt32, P(EdsUInt32), P(EdsUInt32))
        self._fn("EdsGetPropertyData", EdsBaseRef, EdsUInt32, EdsInt32, EdsUInt32, c_void_p)
        self._fn("EdsSetPropertyData", EdsBaseRef, EdsUInt32, EdsInt32, EdsUInt32, c_void_p)
        self._fn("EdsGetPropertyDesc", EdsBaseRef, EdsUInt32, P(EdsPropertyDesc))
        self._fn("EdsSendCommand", EdsBaseRef, EdsUInt32, EdsInt32)
        self._fn("EdsSendStatusCommand", EdsBaseRef, EdsUInt32, EdsInt32)
        self._fn("EdsSetCapacity", EdsBaseRef, EdsCapacity)
        self._fn("EdsSetObjectEventHandler", EdsBaseRef, EdsUInt32, ObjectEventHandler, c_void_p)
        self._fn("EdsSetPropertyEventHandler", EdsBaseRef, EdsUInt32, PropertyEventHandler, c_void_p)
        self._fn("EdsSetCameraStateEventHandler", EdsBaseRef, EdsUInt32, StateEventHandler, c_void_p)
        self._fn("EdsGetDirectoryItemInfo", EdsBaseRef, P(self.DirectoryItemInfo))
        self._fn("EdsCreateFileStream", c_char_p, EdsUInt32, EdsUInt32, P(EdsBaseRef))
        self._fn("EdsCreateMemoryStream", c_uint64, P(EdsBaseRef))
        self._fn("EdsDownload", EdsBaseRef, c_uint64, EdsBaseRef)
        self._fn("EdsDownloadComplete", EdsBaseRef)
        self._fn("EdsDownloadCancel", EdsBaseRef)
        self._fn("EdsCreateEvfImageRef", EdsBaseRef, P(EdsBaseRef))
        self._fn("EdsDownloadEvfImage", EdsBaseRef, EdsBaseRef)
        self._fn("EdsGetPointer", EdsBaseRef, P(c_void_p))
        self._fn("EdsGetLength", EdsBaseRef, P(c_uint64))
        # EdsGetEvent exists only in newer SDKs; if missing, the message pump is enough.
        try:
            self._fn("EdsGetEvent")
            self.has_get_event = True
        except AttributeError:
            self.has_get_event = False


def check(err: int, what: str) -> None:
    """Converts an error code to an exception with a readable message."""
    if err == C.EDS_ERR_OK:
        return
    from ..base import CameraBusyError, CameraError

    msg = f"{what}: {C.describe_error(err)}"
    if err == C.EDS_ERR_DEVICE_BUSY:
        raise CameraBusyError(msg, err)
    raise CameraError(msg, err)


__all__ = ["Edsdk", "check", "byref", "EdsPoint", "EdsCapacity", "EdsPropertyDesc", "EdsDeviceInfo"]
