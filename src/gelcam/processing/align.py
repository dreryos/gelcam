"""Frame alignment: translation by phase correlation (numpy FFT) and bilinear shifting."""

from __future__ import annotations

import numpy as np


def _crop(a: np.ndarray, size: int) -> np.ndarray:
    h, w = a.shape
    y0, x0 = (h - min(h, size)) // 2, (w - min(w, size)) // 2
    return a[y0 : y0 + min(h, size), x0 : x0 + min(w, size)]


def _prepare(a: np.ndarray, size: int) -> np.ndarray:
    c = _crop(np.asarray(a, dtype=np.float32), size)
    bad = np.isnan(c)
    if bad.any():  # NaN (saturated samples) must not poison the FFT: use the median of the valid pixels
        c = np.where(bad, np.float32(np.median(c[~bad]) if not bad.all() else 0.0), c)
    c = c - c.mean()
    return c * np.outer(np.hanning(c.shape[0]).astype(np.float32), np.hanning(c.shape[1]).astype(np.float32))


def _refine(m: np.ndarray, i: int, j: int) -> tuple[float, float]:
    """Parabolic sub-pixel offset of the peak at (i, j), per axis, with wrap-around."""
    h, w = m.shape
    c = float(m[i, j])

    def off(lo: float, hi: float) -> float:
        d = lo - 2 * c + hi
        return 0.0 if d == 0 else 0.5 * (lo - hi) / d

    return off(m[(i - 1) % h, j], m[(i + 1) % h, j]), off(m[i, (j - 1) % w], m[i, (j + 1) % w])


def estimate_shift(ref: np.ndarray, img: np.ndarray, max_size: int = 512) -> tuple[float, float]:
    """Translation (dy, dx) that moves ``img`` onto ``ref`` (phase correlation, centred crop)."""
    a, b = _prepare(ref, max_size), _prepare(img, max_size)
    cross = np.fft.rfft2(a) * np.conj(np.fft.rfft2(b))
    mag = np.abs(cross)
    # regularised normalisation: noise-dominated (weak) frequencies are not boosted to unit weight
    cross /= mag + 0.5 * float(mag.mean()) + 1e-30
    m = np.fft.irfft2(cross, s=a.shape)
    i, j = np.unravel_index(int(np.argmax(m)), m.shape)
    fy, fx = _refine(m, int(i), int(j))
    h, w = m.shape
    dy = i + fy - (h if i > h // 2 else 0)
    dx = j + fx - (w if j > w // 2 else 0)
    return float(dy), float(dx)


def _axis_weights(n: int, d: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    src = np.arange(n, dtype=np.float64) - d  # 1-D per-axis vector: float64 keeps the sub-pixel position exact
    lo = np.floor(src)
    t = (src - lo).astype(np.float32)
    return np.clip(lo, 0, n - 1).astype(np.intp), np.clip(lo + 1, 0, n - 1).astype(np.intp), t


def shift_image(img: np.ndarray, dy: float, dx: float) -> np.ndarray:
    """Move image content by (dy, dx) with bilinear resampling; edges are replicated.

    NaN samples (saturated) stay NaN: where any contributing neighbour is NaN the result is NaN.
    """
    a = np.asarray(img, dtype=np.float32)
    y0, y1, ty = _axis_weights(a.shape[0], dy)
    x0, x1, tx = _axis_weights(a.shape[1], dx)

    def resample(b: np.ndarray) -> np.ndarray:
        rows = b[y0] * (1 - ty)[:, None] + b[y1] * ty[:, None]
        return (rows[:, x0] * (1 - tx) + rows[:, x1] * tx).astype(np.float32)

    bad = np.isnan(a)
    if not bad.any():
        return resample(a)
    out = resample(np.where(bad, np.float32(np.median(a[~bad]) if not bad.all() else 0.0), a))
    out[resample((~bad).astype(np.float32)) < 0.999] = np.nan  # validity mask resampled alongside the data
    return out


def needs_alignment(dy: float, dx: float, threshold: float = 0.5) -> bool:
    return max(abs(dy), abs(dx)) > threshold
