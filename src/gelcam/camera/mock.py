"""Simulovaný foťák pro vývoj a testy bez připojeného 100D.

- live view: syntetický gel se šumem, lupa zvětšuje výřez,
- ostření: simulované rozostření, které AF i kroky ostření zlepšují,
- capture: kopíruje další soubor z `source_dir` (např. CR2 z testovacích sad),
  nebo bez zdroje uloží syntetický 14bit snímek jako .npy.
"""

from __future__ import annotations

import itertools
import shutil
import time
from pathlib import Path

import numpy as np

from .base import CameraError, CameraInfo, FocusStep, Prop, check_allowed, ensure_raw_quality
from ..testing.synthetic import SyntheticGel, expose, to_preview_rgb

# Hodnoty, jaké nabízí 100D v režimu M (kódy EDSDK)
_ISO_CODES = [0x00, 0x48, 0x50, 0x58, 0x60, 0x68, 0x70, 0x78, 0x80]
_TV_CODES = [0x0C, 0x10, 0x13, 0x15, 0x18, 0x1B, 0x1D, 0x20, 0x23, 0x25, 0x28, 0x2B, 0x2D, 0x30,
             0x33, 0x35, 0x38, 0x3B, 0x3D, 0x40, 0x43, 0x45, 0x48, 0x4B, 0x4D, 0x50, 0x53, 0x55,
             0x58, 0x5B, 0x5D, 0x60, 0x63, 0x65, 0x68, 0x6B, 0x6D, 0x70, 0x73, 0x75, 0x78, 0x7B,
             0x7D, 0x80, 0x83, 0x85, 0x88, 0x8B, 0x8D, 0x90, 0x93, 0x95, 0x98]
_AV_CODES = [0x25, 0x28, 0x2B, 0x2D, 0x30, 0x33, 0x35, 0x38, 0x3B, 0x3D, 0x40, 0x43, 0x45, 0x48,
             0x4B, 0x4D, 0x50]


_QUALITY_CODES = [0x13FF0F, 0x12FF0F, 0x640013, 0x64FF0F]  # jako 100D: JPEG, RAW+JPEG, RAW


class MockCamera:
    def __init__(self, source_dir: Path | None = None, *, seed: int = 0, latency: float = 0.0) -> None:
        self._source = sorted(source_dir.glob("*.CR2")) + sorted(source_dir.glob("*.cr2")) if source_dir else []
        self._cycle = itertools.cycle(self._source) if self._source else None
        self._rng = np.random.default_rng(seed)
        self._latency = latency
        self._connected = False
        self._live = False
        self._zoom = (1, 0, 0)
        self._defocus = 6.0
        self._counter = 0
        self._gel = SyntheticGel()
        self._signal = self._gel.signal() * self._gel.flat_field()
        self._values: dict[Prop, int | str] = {
            Prop.ISO: 0x48, Prop.TV: 0x38, Prop.AV: 0x30, Prop.IMAGE_QUALITY: 0x64FF0F, Prop.AE_MODE: 3,
            Prop.BATTERY: 100, Prop.PRODUCT_NAME: "Canon EOS 100D (simulace)",
        }

    # --- připojení ---
    def connect(self) -> CameraInfo:
        self._connected = True
        return CameraInfo(model=str(self._values[Prop.PRODUCT_NAME]), port="mock")

    def disconnect(self) -> None:
        self._live = False
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _require(self) -> None:
        if not self._connected:
            raise CameraError("Foťák není připojený.")

    # --- vlastnosti ---
    def allowed_values(self, prop: Prop) -> list[int]:
        self._require()
        return {Prop.ISO: _ISO_CODES, Prop.TV: _TV_CODES, Prop.AV: _AV_CODES,
                Prop.IMAGE_QUALITY: _QUALITY_CODES}.get(prop, [])

    def get(self, prop: Prop) -> int | str:
        self._require()
        return self._values[prop]

    def set(self, prop: Prop, value: int) -> None:
        self._require()
        check_allowed(self, prop, value)
        self._values[prop] = value

    # --- live view a ostření ---
    def start_live_view(self) -> None:
        self._require()
        self._live = True

    def stop_live_view(self) -> None:
        self._live = False

    def set_live_view_zoom(self, factor: int, x: int | None = None, y: int | None = None) -> None:
        if factor not in (1, 5, 10):
            raise CameraError("Lupa podporuje jen 1×, 5× a 10×.")
        h, w = self._signal.shape
        self._zoom = (factor, w // 2 if x is None else x, h // 2 if y is None else y)

    def live_view_frame(self) -> np.ndarray | None:
        if not self._live:
            return None
        img = self._blurred(self._signal, self._defocus)
        factor, cx, cy = self._zoom
        if factor > 1:
            h, w = img.shape
            ch, cw = max(h // factor, 8), max(w // factor, 8)
            y0 = int(np.clip(cy - ch // 2, 0, h - ch))
            x0 = int(np.clip(cx - cw // 2, 0, w - cw))
            crop = img[y0:y0 + ch, x0:x0 + cw]
            img = np.kron(crop, np.ones((factor, factor)))[:h, :w]
        return to_preview_rgb(img, self._rng)

    def autofocus(self) -> None:
        self._require()
        if not self._live:
            raise CameraError("Ostření funguje jen v live view.")
        time.sleep(self._latency)
        self._defocus = float(self._rng.uniform(0.0, 1.5))

    def drive_focus(self, step: FocusStep) -> None:
        self._require()
        if not self._live:
            raise CameraError("Ostření funguje jen v live view.")
        size = {1: 0.5, 2: 2.0, 3: 6.0}[abs(step.value)]
        # simulace: "near" ostří blíž; optimum je na 0
        self._defocus = abs(self._defocus - size) if step.value < 0 else self._defocus + size

    @property
    def defocus(self) -> float:
        """Jen pro testy: aktuální simulované rozostření."""
        return self._defocus

    # --- focení ---
    def capture(self, dest_dir: Path) -> Path:
        self._require()
        ensure_raw_quality(self)
        dest_dir.mkdir(parents=True, exist_ok=True)
        time.sleep(self._latency)
        self._counter += 1
        if self._cycle is not None:
            src = next(self._cycle)
            dest = dest_dir / f"IMG_{self._counter:04d}{src.suffix.upper()}"
            shutil.copy2(src, dest)
            return dest
        frame = expose(self._signal, self._rng)
        dest = dest_dir / f"IMG_{self._counter:04d}.npy"
        np.save(dest, frame)
        return dest

    @staticmethod
    def _blurred(img: np.ndarray, sigma: float) -> np.ndarray:
        if sigma < 0.3:
            return img
        radius = int(3 * sigma)
        x = np.arange(-radius, radius + 1)
        k = np.exp(-(x ** 2) / (2 * sigma ** 2))
        k /= k.sum()
        out = np.apply_along_axis(lambda r: np.convolve(r, k, mode="same"), 1, img)
        return np.apply_along_axis(lambda c: np.convolve(c, k, mode="same"), 0, out)
