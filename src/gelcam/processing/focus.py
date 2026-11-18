"""Focus sharpness metric for live view frames (display/guidance only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

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


def raw_sharpness(plane: np.ndarray, sigma: float = 1.5) -> float:
    """Scale-free sharpness of a RAW channel plane, for comparing frames of the same scene.

    Mean gradient energy after Gaussian smoothing, divided by the squared mean signal. The smoothing
    removes the pixel noise (which dominates the plain Laplacian variance), the normalisation makes the
    value independent of the exposure time. Measured on real 100D frames: sharp vs. defocused 20-22x,
    repeated sharp frames 1.01, 1 s vs. 2 s exposure of a sharp frame 1.01. Only ratios are meaningful.
    """
    import cv2  # lazy: only needed when a frame is measured

    p = np.asarray(plane, dtype=np.float32)
    mean = float(p.mean())
    if mean <= 0:
        return 0.0
    g = cv2.GaussianBlur(p, (0, 0), sigma)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1)
    return float(np.mean(gx * gx + gy * gy) / (mean * mean))


#: A frame (or series) with less than this fraction of the reference sharpness counts as blurred.
BLUR_LIMIT = 0.6


@dataclass(frozen=True)
class FocusAssessment:
    series_vs_reference: float | None  # median sharpness of the series / reference sharpness
    blurry_frames: tuple[int, ...]  # 1-based numbers of frames blurrier than the rest of the series
    worst_vs_series: float | None  # sharpness of the blurriest frame / median of the series

    @property
    def series_blurred(self) -> bool:
        return self.series_vs_reference is not None and self.series_vs_reference < BLUR_LIMIT


def assess_focus(reference: float | None, series: Sequence[float], limit: float = BLUR_LIMIT) -> FocusAssessment:
    """Is the series as sharp as the reference (the test frame taken after focusing), and are all its frames alike?"""
    vals = [float(v) for v in series]
    if not vals:
        return FocusAssessment(None, (), None)
    median = float(np.median(vals))
    vs_ref = median / reference if reference and reference > 0 else None
    blurry: tuple[int, ...] = ()
    worst = None
    if len(vals) >= 3 and median > 0:  # with fewer frames "the rest of the series" says nothing
        blurry = tuple(i + 1 for i, v in enumerate(vals) if v < limit * median)
        worst = min(vals) / median
    return FocusAssessment(vs_ref, blurry, worst)
