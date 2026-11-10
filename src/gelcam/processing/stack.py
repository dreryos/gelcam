"""Sigma-clipped mean along the frame axis, computed in horizontal tiles (float32 only)."""

from __future__ import annotations

import warnings
from collections.abc import Callable

import numpy as np

# 1.4826 (MAD -> sigma) x 1.9: small-N correction, keeps Gaussian rejections ~1 % at N=8
_MAD_TO_SIGMA = np.float32(1.4826 * 1.9)
_MIN_SCALE = np.float32(0.5)  # ADU floor so constant pixels do not reject everything


def _nanmedian(a: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():  # all-NaN columns (saturated in every frame) are expected and give NaN
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(a, axis=0)


def sigma_clip_mean(
    stack: np.ndarray, sigma: float = 3.0, iterations: int = 3, tile_rows: int = 256,
    check: Callable[[], None] | None = None,
) -> tuple[np.ndarray, int]:
    """Mean of `stack` (N, H, W) after iterative rejection around the median, with a robust (MAD) scale so the outliers
    do not inflate their own threshold.

    NaN samples (saturated) are ignored from the start and are not counted as rejected. Returns (mean float32 (H, W),
    number of samples rejected by clipping). All-rejected pixels fall back to the median; pixels with no valid
    sample are NaN. `check` is called per tile (cooperative cancellation: it may raise).
    """
    n, h, w = stack.shape
    out = np.empty((h, w), np.float32)
    rejected = 0
    for r0 in range(0, h, tile_rows):
        if check is not None:
            check()
        tile = np.asarray(stack[:, r0:r0 + tile_rows], dtype=np.float32)
        valid = ~np.isnan(tile)
        all_valid = bool(valid.all())
        if n < 3:
            cnt = valid.sum(axis=0, dtype=np.float32)
            tot = np.where(valid, tile, 0).sum(axis=0, dtype=np.float32)
            out[r0:r0 + tile_rows] = np.where(cnt > 0, tot / np.maximum(cnt, 1), np.nan)
            continue
        med = np.median(tile, axis=0) if all_valid else _nanmedian(tile)
        keep = valid
        for _ in range(iterations):
            dev = np.abs(tile - med)
            mad = _nanmedian(np.where(keep, dev, np.nan))
            scale = np.maximum(_MAD_TO_SIGMA * mad, _MIN_SCALE)
            new = dev <= sigma * scale  # False for NaN
            if np.array_equal(new, keep):
                break
            keep = new
        cnt = keep.sum(axis=0, dtype=np.float32)
        res = np.where(keep, tile, 0).sum(axis=0, dtype=np.float32) / np.maximum(cnt, 1)
        out[r0:r0 + tile_rows] = np.where(cnt > 0, res, med)
        rejected += int(valid.sum() - keep.sum())
    return out, rejected
