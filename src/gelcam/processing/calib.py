"""Master dark / flat construction and light-frame calibration (linear operations only)."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .stack import ITERATIONS, SIGMA, sigma_clip_mean

F32 = np.float32


def master_dark(darks, tile_rows: int = 256, check: Callable[[], None] | None = None) -> np.ndarray:
    """Per-pixel sigma-clipped mean of a (N, H, W) stack of dark frames; float32 (H, W), black level included.

    Robust to cosmic rays and transients like a median, but with ~20 % less noise (mean, not median).
    """
    return sigma_clip_mean(darks, SIGMA, ITERATIONS, tile_rows, check)[0]


def master_flat(
    flats, flat_dark: np.ndarray, min_value: float = 0.05, tile_rows: int = 256,
    check: Callable[[], None] | None = None,
) -> tuple[np.ndarray, int]:
    """Normalised flat F̂ = F / mean(F) with F = sigma-clipped mean(flats) − flat_dark.

    Pixels where F̂ < `min_value` (dead, unlit or saturated) are set to 1.0, i.e. left uncorrected.
    Returns (F̂ float32, number of such pixels).
    """
    f = sigma_clip_mean(flats, SIGMA, ITERATIONS, tile_rows, check)[0]
    f -= np.asarray(flat_dark, dtype=F32)
    pos = f > 0
    if not pos.any():
        raise ValueError("Flat has no positive pixels after dark subtraction")
    f /= F32(f[pos].mean(dtype=np.float64))  # scalar reduction: float64 for accuracy, no full-size buffer
    bad = ~(f >= F32(min_value))  # also NaN (saturated in every flat): left uncorrected
    f[bad] = F32(1.0)
    return f, int(bad.sum())


def calibrate(light: np.ndarray, dark: np.ndarray, flat: np.ndarray | None = None) -> np.ndarray:
    """(light − dark) / flat as float32; `flat=None` skips the division."""
    if light.shape != dark.shape or (flat is not None and flat.shape != light.shape):
        raise ValueError(
            f"Shape mismatch: light {light.shape}, dark {dark.shape}"
            + (f", flat {flat.shape}" if flat is not None else "")
        )
    out = np.subtract(light, dark, dtype=F32)
    if flat is not None:
        out /= flat.astype(F32, copy=False)
    return out
