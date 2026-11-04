"""Načtení RAW (CR2) do nedemozaikované mozaiky a popis jejího CFA vzoru.

Pravidlo projektu: RAW se nikdy nemění a nedemozaikuje. `RawFrame` drží
surová čísla ze snímače tak, jak je vrátil LibRaw (`raw_image_visible`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class RawFrame:
    """Jedna nedemozaikovaná expozice."""

    #: mozaika (H, W) uint16 – viditelná část snímače, surové hodnoty (včetně black levelu)
    mosaic: np.ndarray
    #: index barvy každého pixelu v mozaice (H, W) uint8, indexuje `color_desc`
    colors: np.ndarray
    #: písmena barev podle indexu, např. "RGBG" (index 3 je druhé G)
    color_desc: str
    #: black level pro každý index barvy (délka = len(color_desc))
    black_levels: tuple[float, ...]
    #: úroveň, od které LibRaw považuje pixel za plný (konzervativní hranice saturace)
    white_level: int
    source: str = ""

    @property
    def shape(self) -> tuple[int, int]:
        return self.mosaic.shape  # type: ignore[return-value]

    @property
    def cfa_pattern(self) -> np.ndarray:
        """Vzor 2×2 s indexy barev vlevo nahoře viditelné oblasti."""
        return self.colors[:2, :2]

    def black_level(self, letter: str) -> float:
        """Průměrný black level pro barvu zadanou písmenem (R, G, B)."""
        idx = [i for i, ch in enumerate(self.color_desc) if ch == letter]
        if not idx:
            raise ValueError(f"Barva {letter!r} není v CFA ({self.color_desc})")
        return float(np.mean([self.black_levels[i] for i in idx]))


def read_raw(path: str | Path) -> RawFrame:
    """Načte CR2 přes rawpy bez demozaikování; soubor se nijak nemění."""
    import rawpy  # těžká závislost, načítá se až při použití

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
