"""Camera interface used by the rest of the application.

The GUI and capture control never call EDSDK directly; everything goes through `Camera`.
Property values (`Prop`) are raw camera codes. A value may be written to the camera
only if `allowed_values()` returns it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np


class Prop(Enum):
    """Camera properties that the application reads or sets."""

    ISO = "iso"
    TV = "tv"  # shutter speed
    AV = "av"  # aperture
    IMAGE_QUALITY = "image_quality"  # EdsImageQuality code; the application needs RAW
    AE_MODE = "ae_mode"  # read-only: exposure mode dial position
    BATTERY = "battery"  # read-only
    PRODUCT_NAME = "product_name"  # read-only


#: Properties the application may write. The others are read-only.
WRITABLE_PROPS: frozenset[Prop] = frozenset({Prop.ISO, Prop.TV, Prop.AV, Prop.IMAGE_QUALITY})


class FocusStep(Enum):
    """Relative focus step in live view (EDSDK DriveLensEvf)."""

    NEAR_3 = -3
    NEAR_2 = -2
    NEAR_1 = -1
    FAR_1 = 1
    FAR_2 = 2
    FAR_3 = 3


@dataclass(frozen=True)
class CameraInfo:
    model: str
    port: str = ""
    serial: str = ""
    sdk_version: str = ""


class CameraError(RuntimeError):
    """Camera communication error, with a message the operator can understand."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class CameraBusyError(CameraError):
    """Camera is temporarily busy; the operation can be retried."""


class ValueNotAllowedError(CameraError):
    """Requested value is not in the list offered by the camera."""


@runtime_checkable
class Camera(Protocol):
    def connect(self) -> CameraInfo: ...

    def disconnect(self) -> None: ...

    @property
    def is_connected(self) -> bool: ...

    def allowed_values(self, prop: Prop) -> list[int]:
        """Codes the camera currently offers for the property (always read from the camera)."""
        ...

    def get(self, prop: Prop) -> int | str: ...

    def set(self, prop: Prop, value: int) -> None:
        """Sets a code; it must come from `allowed_values(prop)`, otherwise ValueNotAllowedError."""
        ...

    def start_live_view(self) -> None: ...

    def live_view_frame(self) -> np.ndarray | None:
        """Latest live view frame as RGB uint8 (H, W, 3), or None if none is available yet."""
        ...

    def set_live_view_zoom(self, factor: int, x: int | None = None, y: int | None = None) -> None:
        """Live view zoom: 1, 5 or 10; x, y = centre in sensor coordinates."""
        ...

    def stop_live_view(self) -> None: ...

    def autofocus(self) -> None:
        """One-shot focus in live view (camera AF)."""
        ...

    def drive_focus(self, step: FocusStep) -> None:
        """Moves focus by a relative step, live view only."""
        ...

    def capture(self, dest_dir: Path) -> Path:
        """Takes a picture without AF, downloads the file to `dest_dir` and returns its path."""
        ...


def ensure_raw_quality(camera: Camera) -> int | None:
    """Ensures the camera saves RAW only; returns the code that was set, or None if it already is.

    Chooses only from values the camera offers (`allowed_values`). If the camera
    offers no RAW-only option, it raises CameraError.
    """
    from . import values

    current = int(camera.get(Prop.IMAGE_QUALITY))
    if values.is_raw_only(current):
        return None
    target = values.preferred_raw_quality(camera.allowed_values(Prop.IMAGE_QUALITY))
    if target is None:
        raise CameraError("Camera does not offer RAW-only quality. Set RAW in the camera menu.")
    camera.set(Prop.IMAGE_QUALITY, target)
    return target


def check_allowed(camera: Camera, prop: Prop, value: int) -> None:
    """Common check for `Camera.set` implementations."""
    if prop not in WRITABLE_PROPS:
        raise ValueNotAllowedError(f"Property {prop.value} is read-only.")
    allowed = camera.allowed_values(prop)
    if value not in allowed:
        raise ValueNotAllowedError(
            f"Value 0x{value:02X} for {prop.value} is not among the values the camera offers."
        )
