"""Measuring and registering flat fields (no GUI, no camera): used by the flat capture window and the tools.

A flat is divided out, so its absolute level does not matter; it must only be well exposed (centre at
50-80 % of the range, nothing saturated) and show the illumination pattern of the arrangement.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

import numpy as np

from ..processing.channel import saturation_mask, select_channel
from ..processing.exposure import propose_seconds
from ..processing.raw_io import RawFrame, read_frame
from ..storage import flat_library as lib

TARGET_FRACTION = 0.65  # centre brightness aimed at, as a fraction of the usable range
RANGE_OK = (0.50, 0.80)
SATURATION_LIMIT = lib.SATURATION_WARN
MAX_SECONDS = 30.0


@dataclass(frozen=True)
class FlatStats:
    centre_adu: float  # mean of the central 20 % x 20 %, above black
    fraction: float  # centre_adu / (white level - black)
    corner_ratio: float  # darkest corner / centre
    saturated_fraction: float


def analyze_flat(frame: RawFrame, channel: str) -> FlatStats:
    """Centre level, corner falloff and saturation of one flat frame in the given channel."""
    plane = select_channel(frame, channel) - np.float32(frame.black_level(channel))
    h, w = plane.shape
    centre = float(plane[int(0.4 * h):int(0.6 * h), int(0.4 * w):int(0.6 * w)].mean())
    ph, pw = max(int(0.06 * h), 4), max(int(0.06 * w), 4)
    ih, iw = int(0.04 * h), int(0.04 * w)
    corners = [plane[y:y + ph, x:x + pw].mean() for y in (ih, h - ih - ph) for x in (iw, w - iw - pw)]
    span = frame.white_level - frame.black_level(channel)
    return FlatStats(
        centre_adu=centre,
        fraction=centre / span if span > 0 else 0.0,
        corner_ratio=float(min(corners) / centre) if centre > 0 else 0.0,
        saturated_fraction=float(saturation_mask(frame, channel).mean()),
    )


def advice(stats: FlatStats) -> str | None:
    """None when the flat is well exposed, otherwise "dark", "bright" or "saturated" (what to change)."""
    if stats.saturated_fraction > SATURATION_LIMIT:
        return "saturated"
    if stats.fraction < RANGE_OK[0]:
        return "dark"
    if stats.fraction > RANGE_OK[1]:
        return "bright"
    return None


def propose_flat_seconds(current_s: float, fraction: float) -> float:
    """Exposure time that puts the centre at `TARGET_FRACTION` (linear scaling, at most 30 s)."""
    return propose_seconds(current_s, fraction, target=TARGET_FRACTION, max_s=MAX_SECONDS)


def build_flat_set(
    folder: Path, *, light: str, channel: str, iso: int, seconds: float, aperture: float, target: str,
    zoom_marked: bool, lens: str | None = None, focal_mm: float | None = None, camera: str = "",
    created: datetime | None = None, sample: int = 4,
) -> lib.FlatSet:
    """Measures the frames already in `folder/flat` and `folder/dark`, writes `flat.json` and returns the set.

    The statistics come from `sample` frames spread over the series (reading every CR2 would only cost time).
    """
    flats = sorted(p.name for p in (folder / "flat").iterdir() if p.is_file())
    darks = sorted(p.name for p in (folder / "dark").iterdir() if p.is_file())
    if not flats or not darks:
        raise ValueError("A flat set needs flat frames and dark frames")
    picks = sorted({flats[round(i * (len(flats) - 1) / max(sample - 1, 1))] for i in range(min(sample, len(flats)))})
    stats = [analyze_flat(read_frame(folder / "flat" / n), channel) for n in picks]
    flat_set = lib.FlatSet(
        path=folder, created=created or datetime.now(), light=light, channel=channel, iso=iso, seconds=seconds,
        aperture=aperture, lens=lens, focal_mm=focal_mm, target=target, zoom_marked=zoom_marked,
        flats=tuple(flats), darks=tuple(darks),
        centre_adu=float(np.mean([s.centre_adu for s in stats])),
        corner_ratio=float(np.mean([s.corner_ratio for s in stats])),
        saturated_fraction=float(max(s.saturated_fraction for s in stats)), camera=camera,
    )
    lib.save(flat_set)
    return flat_set


def register_existing(
    root: Path, flat_files: Sequence[Path], dark_files: Sequence[Path], *, light: str, channel: str, iso: int,
    seconds: float, aperture: float, target: str, zoom_marked: bool = False, lens: str | None = None,
    camera: str = "", created: datetime | None = None,
) -> lib.FlatSet:
    """Copies frames that were taken earlier into a new library entry (the originals stay untouched)."""
    folder = lib.new_flat_dir(root, light, created or datetime.now())
    try:
        for i, src in enumerate(flat_files, 1):
            shutil.copy2(src, folder / "flat" / f"flat_{i:02d}{Path(src).suffix.upper()}")
        for i, src in enumerate(dark_files, 1):
            shutil.copy2(src, folder / "dark" / f"dark_{i:02d}{Path(src).suffix.upper()}")
        return build_flat_set(folder, light=light, channel=channel, iso=iso, seconds=seconds, aperture=aperture,
                              target=target, zoom_marked=zoom_marked, lens=lens, camera=camera, created=created)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)  # a half-made set must not stay in the library
        raise
