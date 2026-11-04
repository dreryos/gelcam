"""Konstanty Canon EDSDK, které GelCam používá.

Hodnoty jsou přepsané podle veřejně známých verzí EDSDK. Před prvním
použitím je ověř proti hlavičkám ve `vendor/edsdk/Header/`:

    uv run python tools/check_edsdk_constants.py

Jména odpovídají jménům v EDSDKTypes.h / EDSDKErrors.h, aby je kontrola
mohla najít.
"""

from __future__ import annotations

# --- chybové kódy (EDSDKErrors.h) ---
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

# --- ID vlastností (EdsPropertyID) ---
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

# --- příkazy (EdsCameraCommand) ---
kEdsCameraCommand_TakePicture = 0x00000000
kEdsCameraCommand_ExtendShutDownTimer = 0x00000001
kEdsCameraCommand_PressShutterButton = 0x00000004
kEdsCameraCommand_DoEvfAf = 0x00000102
kEdsCameraCommand_DriveLensEvf = 0x00000103

# parametry PressShutterButton (EdsShutterButton)
kEdsCameraCommand_ShutterButton_OFF = 0x00000000
kEdsCameraCommand_ShutterButton_Halfway = 0x00000001
kEdsCameraCommand_ShutterButton_Completely = 0x00000003
kEdsCameraCommand_ShutterButton_Halfway_NonAF = 0x00010001
kEdsCameraCommand_ShutterButton_Completely_NonAF = 0x00010003

# parametry DoEvfAf (EdsEvfAf)
kEdsCameraCommand_EvfAf_OFF = 0
kEdsCameraCommand_EvfAf_ON = 1

# parametry DriveLensEvf (EdsEvfDriveLens)
kEdsEvfDriveLens_Near1 = 0x00000001
kEdsEvfDriveLens_Near2 = 0x00000002
kEdsEvfDriveLens_Near3 = 0x00000003
kEdsEvfDriveLens_Far1 = 0x00008001
kEdsEvfDriveLens_Far2 = 0x00008002
kEdsEvfDriveLens_Far3 = 0x00008003

# stavové příkazy (EdsCameraStatusCommand)
kEdsCameraStatusCommand_UILock = 0x00000000
kEdsCameraStatusCommand_UIUnLock = 0x00000001

# --- události ---
kEdsObjectEvent_All = 0x00000200
kEdsObjectEvent_DirItemRequestTransfer = 0x00000208
kEdsPropertyEvent_All = 0x00000100
kEdsPropertyEvent_PropertyChanged = 0x00000101
kEdsPropertyEvent_PropertyDescChanged = 0x00000102
kEdsStateEvent_All = 0x00000300
kEdsStateEvent_Shutdown = 0x00000301
kEdsStateEvent_WillSoonShutDown = 0x00000303

# --- hodnoty vlastností ---
# EdsSaveTo
kEdsSaveTo_Camera = 1
kEdsSaveTo_Host = 2
kEdsSaveTo_Both = 3
# EdsEvfOutputDevice (bitová maska)
kEdsEvfOutputDevice_TFT = 1
kEdsEvfOutputDevice_PC = 2
# EdsFileCreateDisposition, EdsAccess
kEdsFileCreateDisposition_CreateAlways = 1
kEdsAccess_ReadWrite = 2

# AEMode: ruční režim M
AE_MODE_MANUAL = 3

#: Konstanty, které kontrolní skript porovná s hlavičkami (jméno → hodnota).
CHECKED: dict[str, int] = {
    name: value
    for name, value in globals().items()
    if (name.startswith("kEds") or name.startswith("EDS_ERR_")) and isinstance(value, int)
}

ERROR_MESSAGES: dict[int, str] = {
    EDS_ERR_DEVICE_NOT_FOUND: "Foťák nebyl nalezen. Je zapnutý a připojený kabelem USB?",
    EDS_ERR_DEVICE_BUSY: "Foťák je zaneprázdněný.",
    EDS_ERR_COMM_PORT_IS_IN_USE: "Foťák používá jiná aplikace (EOS Utility, digiCamControl…). Zavřete ji.",
    EDS_ERR_COMM_DISCONNECTED: "Spojení s foťákem bylo přerušeno.",
    EDS_ERR_SESSION_NOT_OPEN: "Spojení s foťákem není otevřené.",
    EDS_ERR_OBJECT_NOTREADY: "Snímek live view ještě není připravený.",
    EDS_ERR_TAKE_PICTURE_AF_NG: "Foťák nedokázal zaostřit.",
    EDS_ERR_TAKE_PICTURE_NO_CARD_NG: "Ve foťáku není karta (nebo zapněte spoušť bez karty).",
    EDS_ERR_TAKE_PICTURE_CARD_PROTECT_NG: "Karta je chráněná proti zápisu.",
}


def describe_error(code: int) -> str:
    return ERROR_MESSAGES.get(code, f"Chyba EDSDK 0x{code:08X}")
