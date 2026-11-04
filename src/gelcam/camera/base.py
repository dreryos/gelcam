"""Rozhraní kamery, které používá zbytek aplikace.

GUI ani řízení snímání nikdy nevolají EDSDK přímo; vše jde přes `Camera`.
Hodnoty vlastností (`Prop`) jsou surové kódy foťáku. Do foťáku se smí
nastavit jen kód, který vrátil `allowed_values()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np


class Prop(Enum):
    """Vlastnosti foťáku, které aplikace čte nebo nastavuje."""

    ISO = "iso"
    TV = "tv"  # čas závěrky
    AV = "av"  # clona
    AE_MODE = "ae_mode"  # jen čtení: poloha voliče režimů
    BATTERY = "battery"  # jen čtení
    PRODUCT_NAME = "product_name"  # jen čtení


#: Vlastnosti, které aplikace smí zapisovat. Ostatní jsou jen pro čtení.
WRITABLE_PROPS: frozenset[Prop] = frozenset({Prop.ISO, Prop.TV, Prop.AV})


class FocusStep(Enum):
    """Relativní krok ostření v live view (EDSDK DriveLensEvf)."""

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
    """Chyba komunikace s foťákem, se srozumitelnou zprávou pro obsluhu."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class CameraBusyError(CameraError):
    """Foťák je dočasně zaneprázdněný; operaci lze zopakovat."""


class ValueNotAllowedError(CameraError):
    """Požadovaná hodnota není v seznamu, který foťák nabízí."""


@runtime_checkable
class Camera(Protocol):
    def connect(self) -> CameraInfo: ...

    def disconnect(self) -> None: ...

    @property
    def is_connected(self) -> bool: ...

    def allowed_values(self, prop: Prop) -> list[int]:
        """Kódy, které foťák pro vlastnost aktuálně nabízí (vždy čteno z foťáku)."""
        ...

    def get(self, prop: Prop) -> int | str: ...

    def set(self, prop: Prop, value: int) -> None:
        """Nastaví kód; musí být z `allowed_values(prop)`, jinak ValueNotAllowedError."""
        ...

    def start_live_view(self) -> None: ...

    def live_view_frame(self) -> np.ndarray | None:
        """Poslední snímek live view jako RGB uint8 (H, W, 3), nebo None, pokud ještě není."""
        ...

    def set_live_view_zoom(self, factor: int, x: int | None = None, y: int | None = None) -> None:
        """Lupa live view: 1, 5 nebo 10; x, y = střed v souřadnicích snímače."""
        ...

    def stop_live_view(self) -> None: ...

    def autofocus(self) -> None:
        """Jednorázové zaostření v live view (AF foťáku)."""
        ...

    def drive_focus(self, step: FocusStep) -> None:
        """Posun ostření o relativní krok, jen v live view."""
        ...

    def capture(self, dest_dir: Path) -> Path:
        """Vyfotí bez AF, stáhne soubor do `dest_dir` a vrátí jeho cestu."""
        ...


def check_allowed(camera: Camera, prop: Prop, value: int) -> None:
    """Společná kontrola pro implementace `Camera.set`."""
    if prop not in WRITABLE_PROPS:
        raise ValueNotAllowedError(f"Vlastnost {prop.value} je jen pro čtení.")
    allowed = camera.allowed_values(prop)
    if value not in allowed:
        raise ValueNotAllowedError(
            f"Hodnota 0x{value:02X} pro {prop.value} není mezi hodnotami, které foťák nabízí."
        )
