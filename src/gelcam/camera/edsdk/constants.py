"""Canon EDSDK constants used by GelCam.

The values were transcribed from publicly known EDSDK versions. Before the first
use, verify them against the headers in `vendor/edsdk/Header/`:

    uv run python tools/check_edsdk_constants.py

The names match those in EDSDKTypes.h / EDSDKErrors.h so that the check
can find them.
"""

from __future__ import annotations

# --- error codes (EDSDKErrors.h) ---
EDS_ERR_OK = 0x00000000
EDS_ERR_UNIMPLEMENTED = 0x00000001
EDS_ERR_INTERNAL_ERROR = 0x00000002
EDS_ERR_DEVICE_NOT_FOUND = 0x00000080
EDS_ERR_DEVICE_BUSY = 0x00000081
EDS_ERR_DEVICE_INVALID = 0x00000082
EDS_ERR_COMM_PORT_IS_IN_USE = 0x000000C0
EDS_ERR_COMM_DISCONNECTED = 0x000000C1
EDS_ERR_SESSION_NOT_OPEN = 0x00002003
EDS_ERR_OBJECT_NOTREADY = 0x0000A102
EDS_ERR_TAKE_PICTURE_AF_NG = 0x00008D01
EDS_ERR_TAKE_PICTURE_NO_CARD_NG = 0x00008D06
EDS_ERR_TAKE_PICTURE_CARD_PROTECT_NG = 0x00008D08

# --- property IDs (EdsPropertyID) ---
kEdsPropID_ProductName = 0x00000002
kEdsPropID_BodyIDEx = 0x00000015
kEdsPropID_BatteryLevel = 0x00000008
kEdsPropID_SaveTo = 0x0000000B
kEdsPropID_ImageQuality = 0x00000100
kEdsPropID_AEMode = 0x00000400
kEdsPropID_ISOSpeed = 0x00000402
kEdsPropID_Av = 0x00000405
kEdsPropID_Tv = 0x00000406
kEdsPropID_AEModeSelect = 0x00000436
kEdsPropID_Evf_OutputDevice = 0x00000500
kEdsPropID_Evf_Mode = 0x00000501
kEdsPropID_Evf_Zoom = 0x00000507
kEdsPropID_Evf_ZoomPosition = 0x00000508

# --- commands (EdsCameraCommand) ---
kEdsCameraCommand_TakePicture = 0x00000000
kEdsCameraCommand_ExtendShutDownTimer = 0x00000001
kEdsCameraCommand_PressShutterButton = 0x00000004
kEdsCameraCommand_DoEvfAf = 0x00000102
kEdsCameraCommand_DriveLensEvf = 0x00000103

# PressShutterButton parameters (EdsShutterButton)
kEdsCameraCommand_ShutterButton_OFF = 0x00000000
kEdsCameraCommand_ShutterButton_Halfway = 0x00000001
kEdsCameraCommand_ShutterButton_Completely = 0x00000003
kEdsCameraCommand_ShutterButton_Halfway_NonAF = 0x00010001
kEdsCameraCommand_ShutterButton_Completely_NonAF = 0x00010003

# DoEvfAf parameters (EdsEvfAf)
kEdsCameraCommand_EvfAf_OFF = 0
kEdsCameraCommand_EvfAf_ON = 1

# DriveLensEvf parameters (EdsEvfDriveLens)
kEdsEvfDriveLens_Near1 = 0x00000001
kEdsEvfDriveLens_Near2 = 0x00000002
kEdsEvfDriveLens_Near3 = 0x00000003
kEdsEvfDriveLens_Far1 = 0x00008001
kEdsEvfDriveLens_Far2 = 0x00008002
kEdsEvfDriveLens_Far3 = 0x00008003

# status commands (EdsCameraStatusCommand)
kEdsCameraStatusCommand_UILock = 0x00000000
kEdsCameraStatusCommand_UIUnLock = 0x00000001

# --- events ---
kEdsObjectEvent_All = 0x00000200
kEdsObjectEvent_DirItemRequestTransfer = 0x00000208
kEdsPropertyEvent_All = 0x00000100
kEdsPropertyEvent_PropertyChanged = 0x00000101
kEdsPropertyEvent_PropertyDescChanged = 0x00000102
kEdsStateEvent_All = 0x00000300
kEdsStateEvent_Shutdown = 0x00000301
kEdsStateEvent_WillSoonShutDown = 0x00000303

# --- property values ---
# EdsSaveTo
kEdsSaveTo_Camera = 1
kEdsSaveTo_Host = 2
kEdsSaveTo_Both = 3
# EdsEvfOutputDevice (bit mask)
kEdsEvfOutputDevice_TFT = 1
kEdsEvfOutputDevice_PC = 2
# EdsFileCreateDisposition, EdsAccess
kEdsFileCreateDisposition_CreateAlways = 1
kEdsAccess_ReadWrite = 2

# AEMode: manual mode M
AE_MODE_MANUAL = 3

#: Constants that the checker script compares with the headers (name → value).
CHECKED: dict[str, int] = {
    name: value
    for name, value in globals().items()
    if (name.startswith("kEds") or name.startswith("EDS_ERR_")) and isinstance(value, int)
}

ERROR_MESSAGES: dict[int, str] = {
    EDS_ERR_DEVICE_NOT_FOUND: "Camera not found. Is it switched on and connected by USB cable?",
    EDS_ERR_DEVICE_BUSY: "Camera is busy.",
    EDS_ERR_COMM_PORT_IS_IN_USE: "Another application is using the camera (EOS Utility, digiCamControl…). Close it.",
    EDS_ERR_COMM_DISCONNECTED: "Connection to the camera was interrupted.",
    EDS_ERR_SESSION_NOT_OPEN: "Connection to the camera is not open.",
    EDS_ERR_OBJECT_NOTREADY: "Live view frame is not ready yet.",
    EDS_ERR_TAKE_PICTURE_AF_NG: "Camera could not focus.",
    EDS_ERR_TAKE_PICTURE_NO_CARD_NG: "There is no memory card in the camera (or enable shutter release without a card).",
    EDS_ERR_TAKE_PICTURE_CARD_PROTECT_NG: "The card is write-protected.",
}


def describe_error(code: int) -> str:
    return ERROR_MESSAGES.get(code, f"EDSDK error 0x{code:08X}")
