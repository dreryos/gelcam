"""Display-only image helpers (pure numpy). Never used for data: results stay linear."""

from __future__ import annotations

import numpy as np


def apply_display(frame: np.ndarray, black: int, white: int, gamma: float = 1.0, invert: bool = False) -> np.ndarray:
    """Maps black..white to 0..255 through a 256-entry LUT (levels, gamma, optional inversion)."""
    x = np.clip((np.arange(256, dtype=np.float32) - black) / max(white - black, 1), 0.0, 1.0)
    lut = np.round(255 * x ** (1.0 / gamma)).astype(np.uint8)
    if invert:
        lut = 255 - lut
    return lut[frame]


def auto_levels(frame: np.ndarray, channel: int) -> tuple[int, int]:
    lo, hi = np.percentile(frame[..., channel], (0.5, 99.8))
    black = int(lo)
    return black, max(int(hi), black + 1)


def histogram(frame: np.ndarray, channel: int, bins: int = 64) -> np.ndarray:
    return np.histogram(frame[..., channel], bins=bins, range=(0, 256))[0]


def clipped_mask(frame: np.ndarray, channel: int, threshold: int = 250) -> np.ndarray:
    return frame[..., channel] >= threshold


def overlay_clipping(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = frame.copy()
    out[mask] = (255, 40, 40)
    return out
