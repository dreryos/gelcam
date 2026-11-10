"""Sigma-clipped mean along the frame axis, computed in horizontal tiles (float32 only)."""

from __future__ import annotations

import numpy as np

# 1.4826 (MAD -> sigma) x 1.9: small-N correction, keeps Gaussian rejections ~1 % at N=8
_MAD_TO_SIGMA = np.float32(1.4826 * 1.9)
_MIN_SCALE = np.float32(0.5)  # ADU floor so constant pixels do not reject everything


def sigma_clip_mean(
    stack: np.ndarray, sigma: float = 3.0, iterations: int = 3, tile_rows: int = 256
) -> tuple[np.ndarray, int]:
    """Mean of `stack` (N, H, W) after iterative rejection around the median, with a robust (MAD) scale so the outliers
    do not inflate their own threshold.

    Returns (mean float32 (H, W), number of rejected samples). All-rejected pixels fall back to the median.
    """
    n, h, w = stack.shape
    out = np.empty((h, w), np.float32)
    rejected = 0
    for r0 in range(0, h, tile_rows):
        tile = np.asarray(stack[:, r0:r0 + tile_rows], dtype=np.float32)
        if n < 3:
            out[r0:r0 + tile_rows] = tile.mean(axis=0, dtype=np.float32)
            continue
        med = np.median(tile, axis=0)
        keep = np.ones(tile.shape, bool)
        for _ in range(iterations):
            dev = np.abs(tile - med)
            mad = np.nanmedian(np.where(keep, dev, np.nan), axis=0)
            scale = np.maximum(_MAD_TO_SIGMA * mad, _MIN_SCALE)
            new = dev <= sigma * scale
            if np.array_equal(new, keep):
                break
            keep = new
        cnt = keep.sum(axis=0, dtype=np.float32)
        res = np.where(keep, tile, 0).sum(axis=0, dtype=np.float32) / np.maximum(cnt, 1)
        out[r0:r0 + tile_rows] = np.where(cnt > 0, res, med)
        rejected += int(keep.size - keep.sum())
    return out, rejected
