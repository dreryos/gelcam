"""Loading RAW (CR2) into a non-demosaiced mosaic and describing its CFA pattern.

Project rule: RAW is never modified or demosaiced. `RawFrame` holds
the raw sensor numbers exactly as returned by LibRaw (`raw_image_visible`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class RawFrame:
    """One non-demosaiced exposure."""

    #: mosaic (H, W) uint16 – visible part of the sensor, raw values (including black level)
    mosaic: np.ndarray
    #: color index of each pixel in the mosaic (H, W) uint8, indexes `color_desc`
    colors: np.ndarray
    #: color letters by index, e.g. "RGBG" (index 3 is the second G)
    color_desc: str
    #: black level for each color index (length = len(color_desc))
    black_levels: tuple[float, ...]
    #: level from which LibRaw considers a pixel full (conservative saturation limit)
    white_level: int
    source: str = ""

    @property
    def shape(self) -> tuple[int, int]:
        return self.mosaic.shape  # type: ignore[return-value]

    @property
    def cfa_pattern(self) -> np.ndarray:
        """2×2 pattern of color indices at the top left of the visible area."""
        return self.colors[:2, :2]

    def black_level(self, letter: str) -> float:
        """Mean black level for the color given by a letter (R, G, B)."""
        idx = [i for i, ch in enumerate(self.color_desc) if ch == letter]
        if not idx:
            raise ValueError(f"Color {letter!r} is not in the CFA ({self.color_desc})")
        return float(np.mean([self.black_levels[i] for i in idx]))


def read_raw(path: str | Path) -> RawFrame:
    """Loads CR2 via rawpy without demosaicing; the file is not modified in any way."""
    import rawpy  # heavy dependency, imported only when used

    path = Path(path)
    with rawpy.imread(str(path)) as raw:
        desc = raw.color_desc.decode("ascii")
        return RawFrame(
            mosaic=np.array(raw.raw_image_visible, dtype=np.uint16, copy=True),
            colors=np.array(raw.raw_colors_visible, dtype=np.uint8, copy=True),
            color_desc=desc,
            black_levels=tuple(float(b) for b in raw.black_level_per_channel),
            white_level=int(raw.white_level),
            source=path.name,
        )
