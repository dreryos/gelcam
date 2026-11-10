"""Conversions of ISO, shutter speed and aperture codes (Canon EDSDK) to readable values.

The codes are logarithmic: 8 units = 1 EV. The conversions are used only for display
and exposure calculations; the original code from the camera's list is always sent to the camera.
"""

from __future__ import annotations

import math

_ISO_SERIES = [
    50, 64, 80, 100, 125, 160, 200, 250, 320, 400, 500, 640, 800, 1000, 1250, 1600,
    2000, 2500, 3200, 4000, 5000, 6400, 8000, 10000, 12800, 16000, 20000, 25600,
]
_F_SERIES = [
    1.0, 1.1, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.5, 2.8, 3.2, 3.5, 4.0, 4.5, 5.0, 5.6, 6.3,
    7.1, 8.0, 9.0, 10.0, 11.0, 13.0, 14.0, 16.0, 18.0, 20.0, 22.0, 25.0, 29.0, 32.0,
    36.0, 40.0, 45.0, 51.0, 57.0, 64.0, 72.0, 80.0, 91.0,
]
_TV_LONG = [30, 25, 20, 15, 13, 10, 8, 6, 5, 4, 3.2, 3, 2.5, 2, 1.6, 1.5, 1.3, 1, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]
_TV_SHORT_DEN = [
    4, 5, 6, 8, 10, 13, 15, 20, 25, 30, 40, 45, 50, 60, 80, 90, 100, 125, 160, 180, 200,
    250, 320, 350, 400, 500, 640, 750, 800, 1000, 1250, 1500, 1600, 2000, 2500, 3000,
    3200, 4000, 5000, 6400, 8000,
]

ISO_AUTO = 0x00
ISO_100 = 0x48
TV_BULB = 0x0C
TV_1S = 0x38
AV_F1 = 0x08


def _nearest(series: list[float], value: float) -> float:
    return min(series, key=lambda s: abs(math.log(s) - math.log(value)))


def iso_value(code: int) -> int | None:
    """ISO code → nominal ISO; None for Auto."""
    if code == ISO_AUTO:
        return None
    raw = 100 * 2 ** ((code - ISO_100) / 8)
    return int(_nearest(_ISO_SERIES, raw))


def iso_label(code: int) -> str:
    v = iso_value(code)
    return "ISO Auto" if v is None else f"ISO {v}"


def tv_seconds(code: int) -> float | None:
    """Shutter code → duration in seconds (nominal); None for Bulb."""
    if code == TV_BULB:
        return None
    raw = 2 ** ((TV_1S - code) / 8)
    if raw >= 0.29:
        return float(_nearest(_TV_LONG, raw))
    return 1 / _nearest(_TV_SHORT_DEN, 1 / raw)


def tv_label(code: int) -> str:
    s = tv_seconds(code)
    if s is None:
        return "Bulb"
    if s >= 0.29:
        return f'{s:g}"'
    return f"1/{round(1 / s)}"


def av_fnumber(code: int) -> float:
    raw = math.sqrt(2) ** ((code - AV_F1) / 8)
    return _nearest(_F_SERIES, raw)


def av_label(code: int) -> str:
    return f"f/{av_fnumber(code):g}"


# --- image quality (EdsImageQuality) ---
# Code 0xSSTTJJKK: SS = RAW size, TT = RAW type (0x64) or 0, JJ/KK = JPEG;
# 0xFF0F in the lower 16 bits means "no second image".
_Q_RAW_TYPE = 0x64
_Q_NO_SECOND = 0xFF0F
_Q_SIZES = {0: "L", 1: "M", 2: "S"}


def is_raw_only(code: int) -> bool:
    """True when the camera saves RAW only (no JPEG)."""
    return (code >> 16) & 0xFF == _Q_RAW_TYPE and code & 0xFFFF == _Q_NO_SECOND


def has_raw(code: int) -> bool:
    return (code >> 16) & 0xFF == _Q_RAW_TYPE


def preferred_raw_quality(allowed: list[int]) -> int | None:
    """From the offered codes, picks full-size RAW without JPEG (otherwise None)."""
    candidates = [c for c in allowed if is_raw_only(c)]
    full = [c for c in candidates if (c >> 24) & 0xFF == 0]
    return (full or candidates or [None])[0]


def quality_label(code: int) -> str:
    size = _Q_SIZES.get((code >> 24) & 0xFF, "?")
    if is_raw_only(code):
        return f"RAW ({size})" if size != "L" else "RAW"
    if has_raw(code):
        return "RAW + JPEG"
    return "JPEG"
