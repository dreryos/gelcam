"""Generátor syntetických gelů se známým signálem a šumem.

Používá ho `MockCamera` (live view, snímky) i testy pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class SyntheticGel:
    height: int = 480
    width: int = 720
    lanes: int = 8
    #: relativní intenzity pruhů v každé dráze (dvojnásobné ředění)
    band_rows: tuple[float, ...] = (0.25, 0.4, 0.55, 0.7)
    lane_scale: tuple[float, ...] = field(default_factory=lambda: tuple(2.0 ** -i for i in range(8)))
    background: float = 0.05
    vignetting: float = 0.3

    def signal(self) -> np.ndarray:
        """Bezšumový obraz signálu (float, max ~1)."""
        h, w = self.height, self.width
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
        img = np.full((h, w), self.background)
        lane_w = w / (self.lanes + 1)
        for i in range(self.lanes):
            cx = lane_w * (i + 1)
            scale = self.lane_scale[i % len(self.lane_scale)]
            lane_profile = np.exp(-(((xx - cx) / (lane_w * 0.3)) ** 6))
            for r in self.band_rows:
                cy = r * h
                img += scale * lane_profile * np.exp(-(((yy - cy) / (h * 0.008)) ** 2))
        return img

    def flat_field(self) -> np.ndarray:
        """Vinětace a nerovnoměrnost lampy (normalizováno na průměr 1)."""
        h, w = self.height, self.width
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
        r2 = ((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2
        f = 1.0 - self.vignetting * r2 / 2
        return f / f.mean()


def expose(
    signal: np.ndarray,
    rng: np.random.Generator,
    *,
    photons: float = 2000.0,
    read_noise: float = 4.0,
    black_level: int = 2048,
    white_level: int = 15000,
    dark_current: float = 5.0,
    hot_pixels: np.ndarray | None = None,
) -> np.ndarray:
    """Jedna expozice: Poissonův šum + temný proud + čtecí šum + black level, 14bit."""
    electrons = rng.poisson(np.clip(signal * photons + dark_current, 0, None)).astype(np.float64)
    if hot_pixels is not None:
        electrons += hot_pixels
    adu = electrons + rng.normal(0, read_noise, signal.shape) + black_level
    return np.clip(np.round(adu), 0, white_level).astype(np.uint16)


def to_preview_rgb(signal: np.ndarray, rng: np.random.Generator | None = None) -> np.ndarray:
    """Náhled podobný live view: oranžová fluorescence na tmavém pozadí, uint8 RGB."""
    s = signal / max(float(signal.max()), 1e-9)
    if rng is not None:
        s = np.clip(s + rng.normal(0, 0.02, s.shape), 0, 1)
    r = np.clip(s * 255, 0, 255)
    g = np.clip(s * 140, 0, 255)
    b = np.clip(s * 20, 0, 255)
    return np.stack([r, g, b], axis=-1).astype(np.uint8)
