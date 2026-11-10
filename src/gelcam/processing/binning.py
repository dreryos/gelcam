"""Software binning."""

from __future__ import annotations

import numpy as np


def bin2x2(img: np.ndarray) -> np.ndarray:
    """Mean of each 2×2 block (float32); an odd trailing row/column is cropped.

    Mean rather than sum, so the value scale stays comparable with the unbinned image.
    """
    h, w = img.shape[0] // 2 * 2, img.shape[1] // 2 * 2
    a = img[:h, :w]
    return (
        (a[0::2, 0::2].astype(np.float32) + a[0::2, 1::2] + a[1::2, 0::2] + a[1::2, 1::2]) * np.float32(0.25)
    )
