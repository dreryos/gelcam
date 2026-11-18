"""Exposure measurement on a RAW channel and a simple exposure-time proposal."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .channel import saturation_mask, select_channel
from .focus import raw_sharpness
from .raw_io import RawFrame


@dataclass(frozen=True)
class ExposureMeasurement:
    brightest_adu: float  # above black level
    fraction: float  # brightest_adu / (white_level - black)
    saturated_fraction: float
    sharpness: float | None = None  # `raw_sharpness` of the channel; compare only between frames of one scene
    median_adu: float | None = None  # median above black: the background of a gel (UV level cross-check)


def measure(frame: RawFrame, channel: str, percentile: float = 99.9) -> ExposureMeasurement:
    black = frame.black_level(channel)
    plane = select_channel(frame, channel) - black
    brightest = float(np.percentile(plane, percentile))
    span = frame.white_level - black
    return ExposureMeasurement(
        brightest_adu=brightest,
        fraction=brightest / span,
        saturated_fraction=float(saturation_mask(frame, channel).mean()),
        sharpness=raw_sharpness(plane),
        median_adu=float(np.median(plane)),
    )


def propose_seconds(current_s: float, fraction: float, target: float = 0.75, max_s: float = 30.0) -> float:
    """Linear scaling of the exposure time towards `target`, clamped to `max_s`."""
    if fraction <= 0:
        return max_s
    return min(current_s * target / fraction, max_s)
