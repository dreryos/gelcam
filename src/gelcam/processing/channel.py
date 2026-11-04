"""Výběr jednoho barevného kanálu z CFA mozaiky bez demozaikování.

Žádná interpolace: kanál R nebo B jsou přímo pixely daného filtru, kanál G je
průměr dvou G pixelů v každé buňce 2×2. Výsledek má poloviční rozlišení.
"""

from __future__ import annotations

import numpy as np

from .raw_io import RawFrame

CHANNELS = ("R", "G", "B")


def _cell_positions(frame: RawFrame, letter: str) -> list[tuple[int, int]]:
    """Pozice (řádek, sloupec) v buňce 2×2, kde je filtr dané barvy."""
    if letter not in CHANNELS:
        raise ValueError(f"Neznámý kanál {letter!r}, povoleno: {CHANNELS}")
    pat = frame.cfa_pattern
    pos = [(dy, dx) for dy in range(2) for dx in range(2) if frame.color_desc[int(pat[dy, dx])] == letter]
    if not pos:
        raise ValueError(f"Barva {letter!r} není v CFA ({frame.color_desc})")
    return pos


def _plane(array: np.ndarray, positions: list[tuple[int, int]]) -> np.ndarray:
    h2, w2 = array.shape[0] // 2, array.shape[1] // 2
    return [array[dy:dy + 2 * h2:2, dx:dx + 2 * w2:2] for dy, dx in positions]


def select_channel(frame: RawFrame, letter: str) -> np.ndarray:
    """Surové hodnoty kanálu (včetně black levelu) jako float32 o rozměru (H/2, W/2)."""
    planes = _plane(frame.mosaic, _cell_positions(frame, letter))
    return np.mean(planes, axis=0, dtype=np.float32)


def saturation_mask(frame: RawFrame, letter: str) -> np.ndarray:
    """True tam, kde je aspoň jeden pixel kanálu v buňce na úrovni `white_level` nebo výš."""
    planes = _plane(frame.mosaic, _cell_positions(frame, letter))
    return np.any([p >= frame.white_level for p in planes], axis=0)
