"""Dye profiles: channel and starting exposure for each stain."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DyeProfile:
    name: str
    channel: str  # "R", "G" or "B"
    emission_filter: str
    iso: int
    seconds: float
    aperture: float
    frames: int = 8


DEFAULT_PROFILES: tuple[DyeProfile, ...] = (
    DyeProfile("EtBr", "R", "orange", 100, 4.0, 8.0),
    DyeProfile("GelRed", "R", "orange", 100, 4.0, 8.0),
    DyeProfile("SYBR Safe", "G", "amber", 100, 8.0, 8.0),
)


def profile_by_name(name: str) -> DyeProfile:
    for p in DEFAULT_PROFILES:
        if p.name == name:
            return p
    raise KeyError(name)
