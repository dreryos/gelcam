"""Focus sharpness metric for live view frames (display/guidance only)."""

from __future__ import annotations

import numpy as np


def sharpness(gray: np.ndarray) -> float:
    """Variance of the 4-neighbour Laplacian; 0.0 for a constant image."""
    g = gray.astype(np.float32)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    lap = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(lap.var())


def sharpness_rgb(frame: np.ndarray) -> float:
    """Sharpness of an RGB uint8 frame: channel mean, every second pixel."""
    gray = frame.astype(np.float32).mean(axis=2)
    return sharpness(gray[::2, ::2])
