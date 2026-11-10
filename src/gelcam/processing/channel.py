"""Selects one color channel from a CFA mosaic without demosaicing.

No interpolation: the R or B channel consists directly of the pixels of that filter, and the G channel is
the mean of two G pixels in each 2×2 cell. The result has half the resolution.
"""

from __future__ import annotations

import numpy as np

from .raw_io import RawFrame

CHANNELS = ("R", "G", "B")


def _cell_positions(frame: RawFrame, letter: str) -> list[tuple[int, int]]:
    """Positions (row, column) in the 2×2 cell where the filter of the given color is."""
    if letter not in CHANNELS:
        raise ValueError(f"Unknown channel {letter!r}, allowed: {CHANNELS}")
    pat = frame.cfa_pattern
    pos = [(dy, dx) for dy in range(2) for dx in range(2) if frame.color_desc[int(pat[dy, dx])] == letter]
    if not pos:
        raise ValueError(f"Color {letter!r} is not in the CFA ({frame.color_desc})")
    return pos


def _plane(array: np.ndarray, positions: list[tuple[int, int]]) -> np.ndarray:
    h2, w2 = array.shape[0] // 2, array.shape[1] // 2
    return [array[dy:dy + 2 * h2:2, dx:dx + 2 * w2:2] for dy, dx in positions]


def select_channel(frame: RawFrame, letter: str) -> np.ndarray:
    """Raw channel values (including black level) as float32 with shape (H/2, W/2)."""
    planes = _plane(frame.mosaic, _cell_positions(frame, letter))
    return np.mean(planes, axis=0, dtype=np.float32)


def saturation_mask(frame: RawFrame, letter: str) -> np.ndarray:
    """True where at least one channel pixel in the cell is at `white_level` or above."""
    planes = _plane(frame.mosaic, _cell_positions(frame, letter))
    return np.any([p >= frame.white_level for p in planes], axis=0)
