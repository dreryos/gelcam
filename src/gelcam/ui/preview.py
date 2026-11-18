"""Display-only image helpers (pure numpy). Never used for data: results stay linear."""

from __future__ import annotations

import numpy as np


def apply_display(frame: np.ndarray, black: int, white: int, gamma: float = 1.0, invert: bool = False) -> np.ndarray:
    """Maps black..white to 0..255 through a 256-entry LUT (levels, gamma, optional inversion).

    With the default settings the display is the frame itself: it is returned as it is (not a copy, callers
    never modify it) instead of running every pixel through an identity table on every frame.
    """
    if black <= 0 and white >= 255 and gamma == 1.0 and not invert:
        return frame
    x = np.clip((np.arange(256, dtype=np.float32) - black) / max(white - black, 1), 0.0, 1.0)
    lut = np.round(255 * x ** (1.0 / gamma)).astype(np.uint8)
    if invert:
        lut = 255 - lut
    return lut[frame]


def auto_levels(frame: np.ndarray, channel: int) -> tuple[int, int]:
    lo, hi = np.percentile(frame[..., channel], (0.5, 99.8))
    black = int(lo)
    return black, max(int(hi), black + 1)


SUBSAMPLE_FROM = 250_000  # pixels; live view frames (960 x 640) are above it, small test images are not


def histogram(frame: np.ndarray, channel: int, bins: int = 64, step: int | None = None) -> np.ndarray:
    """Counts of one channel in `bins` equal bins over 0..255, from every `step`-th pixel in both directions
    (default: every 2nd for large frames, all pixels for small ones).

    `bincount` on 8-bit data is about 4x faster than `np.histogram` (measured 9.7 ms -> 2.3 ms at full
    resolution, 0.7 ms at half); a histogram drawn in 64 bars loses nothing visible from the subsampling.
    """
    step = step or (2 if frame.shape[0] * frame.shape[1] >= SUBSAMPLE_FROM else 1)
    data = frame[::step, ::step, channel]
    if 256 % bins:
        return np.histogram(data, bins=bins, range=(0, 256))[0]
    return np.bincount(data.ravel(), minlength=256).reshape(bins, 256 // bins).sum(axis=1)


def clipped_mask(frame: np.ndarray, channel: int, threshold: int = 250) -> np.ndarray:
    return frame[..., channel] >= threshold


def overlay_clipping(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = frame.copy()
    out[mask] = (255, 40, 40)
    return out
