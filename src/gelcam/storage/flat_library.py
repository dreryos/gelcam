"""Flat-field library: the calibration sets taken for one arrangement, and the rules for when one applies.

A flat set is a folder `<library>/<date>_<time>_<light>/` with `flat/` (the flat frames), `dark/` (darks of
the same exposure, needed because the flat must be dark-subtracted) and `flat.json` (what it is valid for).
The library lives outside the gel folders; a gel's `metadata.json` records the absolute paths of the frames
it was calibrated with, so nothing is copied and the raw frames are never modified.

A flat describes the illumination pattern of one arrangement. It is valid only for the same UV level (the
white-light flat is different: other spectrum and geometry, measured 4 Nov 2026), the same aperture and
lens and the zoom position it was taken at; it ages (lamp, dust), so it is flagged after 30 days. The
exposure time of the gel does not have to equal that of the flat: the flat is normalised.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

SCHEMA = 1
META_NAME = "flat.json"
LIGHTS = ("white", "uv70", "uv100")
MAX_AGE_DAYS = 30
MIN_FRAMES = 8
SATURATION_WARN = 0.001  # fraction of saturated pixels in the flat that is still tolerated
APERTURE_TOLERANCE = 0.05  # f-number


def default_library_dir() -> Path:
    """The library under the root folder chosen in the settings (default `Documents/GelCam`)."""
    from .. import settings

    return settings.load().flats_dir


@dataclass(frozen=True)
class FlatSet:
    path: Path
    created: datetime
    light: str  # "white", "uv70" or "uv100"
    channel: str  # the channel the statistics refer to
    iso: int
    seconds: float  # exposure time of the flats (and of their darks)
    aperture: float
    lens: str | None
    focal_mm: float | None
    target: str  # what was photographed, e.g. "blank gel with EtBr"
    zoom_marked: bool  # the operator confirmed the zoom was at the marked position
    flats: tuple[str, ...]  # file names inside flat/
    darks: tuple[str, ...]  # file names inside dark/
    centre_adu: float  # centre brightness above black, mean of the flats
    corner_ratio: float  # darkest corner / centre
    saturated_fraction: float
    camera: str = ""

    @property
    def id(self) -> str:
        return self.path.name

    @property
    def centre_rate(self) -> float:
        """Centre brightness per second of exposure (ADU/s); compares flats and frames of other exposures."""
        return self.centre_adu / self.seconds if self.seconds > 0 else 0.0

    @property
    def flat_paths(self) -> list[Path]:
        return [self.path / "flat" / n for n in self.flats]

    @property
    def dark_paths(self) -> list[Path]:
        return [self.path / "dark" / n for n in self.darks]

    def to_json(self) -> dict:
        return {
            "schema": SCHEMA, "created": self.created.isoformat(timespec="seconds"), "light": self.light,
            "channel": self.channel, "iso": self.iso, "seconds": self.seconds, "aperture": self.aperture,
            "lens": self.lens, "focal_mm": self.focal_mm, "target": self.target, "zoom_marked": self.zoom_marked,
            "flats": list(self.flats), "darks": list(self.darks), "centre_adu": self.centre_adu,
            "corner_ratio": self.corner_ratio, "saturated_fraction": self.saturated_fraction, "camera": self.camera,
        }

    @classmethod
    def from_json(cls, path: Path, data: dict) -> "FlatSet":
        return cls(
            path=path, created=datetime.fromisoformat(data["created"]), light=data["light"],
            channel=data["channel"], iso=int(data["iso"]), seconds=float(data["seconds"]),
            aperture=float(data["aperture"]), lens=data.get("lens"), focal_mm=data.get("focal_mm"),
            target=data.get("target", ""), zoom_marked=bool(data.get("zoom_marked", False)),
            flats=tuple(data["flats"]), darks=tuple(data["darks"]), centre_adu=float(data["centre_adu"]),
            corner_ratio=float(data["corner_ratio"]), saturated_fraction=float(data["saturated_fraction"]),
            camera=data.get("camera", ""),
        )


# ----------------------------------------------------------------------------------------- storage
def new_flat_dir(root: Path, light: str, when: datetime) -> Path:
    """Creates `root/YYYY-MM-DD_HHMM_<light>/{flat,dark}`; never reuses an existing folder."""
    if light not in LIGHTS:
        raise ValueError(f"Unknown light {light!r}")
    base = f"{when:%Y-%m-%d_%H%M}_{light}"
    folder, n = root / base, 1
    while folder.exists():
        n += 1
        folder = root / f"{base}_{n}"
    (folder / "flat").mkdir(parents=True)
    (folder / "dark").mkdir()
    return folder


def save(flat: FlatSet) -> Path:
    """Writes `flat.json` atomically (the set is complete only once this file exists)."""
    target = flat.path / META_NAME
    fd, tmp = tempfile.mkstemp(dir=flat.path, prefix=".flat-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(flat.to_json(), f, indent=2, ensure_ascii=False)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target


def load(path: Path) -> FlatSet:
    return FlatSet.from_json(path, json.loads((path / META_NAME).read_text(encoding="utf-8")))


def list_flats(root: Path) -> list[FlatSet]:
    """All complete sets in the library, newest first; folders without a valid `flat.json` are ignored."""
    found: list[FlatSet] = []
    if not root.is_dir():
        return found
    for d in root.iterdir():
        if d.is_dir() and (d / META_NAME).exists():
            try:
                found.append(load(d))
            except (OSError, ValueError, KeyError, TypeError):
                continue
    return sorted(found, key=lambda f: f.created, reverse=True)


# ----------------------------------------------------------------------------------------- rules
@dataclass(frozen=True)
class Arrangement:
    """What the gel will be photographed with (declared by the wizard)."""

    light: str
    aperture: float
    lens: str | None = None


@dataclass(frozen=True)
class FlatAssessment:
    status: str  # "ok", "warn" or "mismatch"
    reasons: tuple[str, ...]  # codes, see REASON_TEXT
    age_days: int

    @property
    def usable(self) -> bool:
        return self.status != "mismatch"


MISMATCH = ("light", "aperture", "lens", "incomplete", "files_missing")
WARN = ("old", "zoom_unconfirmed", "saturated")


def assess(flat: FlatSet, arr: Arrangement, now: datetime | None = None) -> FlatAssessment:
    """Does `flat` apply to `arr`? Mismatches must not be used; warnings are shown but allowed."""
    now = now or datetime.now()
    age = max((now - flat.created).days, 0)
    reasons: list[str] = []
    if flat.light != arr.light:
        reasons.append("light")
    if abs(flat.aperture - arr.aperture) > APERTURE_TOLERANCE:
        reasons.append("aperture")
    if flat.lens and arr.lens and flat.lens != arr.lens:
        reasons.append("lens")
    if len(flat.flats) < MIN_FRAMES or not flat.darks:
        reasons.append("incomplete")
    elif not all(p.exists() for p in (*flat.flat_paths, *flat.dark_paths)):
        reasons.append("files_missing")
    if age > MAX_AGE_DAYS:
        reasons.append("old")
    if not flat.zoom_marked:
        reasons.append("zoom_unconfirmed")
    if flat.saturated_fraction > SATURATION_WARN:
        reasons.append("saturated")
    if any(r in MISMATCH for r in reasons):
        status = "mismatch"
    else:
        status = "warn" if reasons else "ok"
    return FlatAssessment(status, tuple(reasons), age)


_ORDER = {"ok": 0, "warn": 1, "mismatch": 2}


def ranked(flats: Sequence[FlatSet], arr: Arrangement, now: datetime | None = None
           ) -> list[tuple[FlatSet, FlatAssessment]]:
    """Flats with their assessment, best first: matching before warnings before mismatches, newest first."""
    rated = [(f, assess(f, arr, now)) for f in flats]
    return sorted(rated, key=lambda fa: (_ORDER[fa[1].status], -fa[0].created.timestamp()))


# ----------------------------------------------------------------------------------------- UV check
#: A frame's background may differ from the flat's by this factor before the app speaks up. It is wide on
#: purpose: a gel is not the same object as the blank flat target, and UV 70 % vs 100 % (0.80-0.81) cannot
#: be told apart this way. The check only catches gross mistakes (wrong or switched-off lamp, wrong flat).
UV_BAND = (0.5, 2.0)


@dataclass(frozen=True)
class UvCheck:
    status: str  # "ok", "warn" or "unknown" (no flat of the declared level to compare with)
    ratio: float | None  # background rate / flat centre rate
    suggests: str | None  # another light whose flat fits much better


def check_uv_level(flats: Sequence[FlatSet], declared: str, background_rate: float) -> UvCheck:
    """Compares the brightness of a test frame (ADU per second) with the stored flats.

    Never changes anything: it is a warning that the declared light may not be the one that is on.
    """
    def newest(light: str) -> FlatSet | None:
        return next((f for f in sorted(flats, key=lambda f: f.created, reverse=True) if f.light == light), None)

    ref = newest(declared)
    if ref is None or ref.centre_rate <= 0 or background_rate <= 0:
        return UvCheck("unknown", None, None)
    ratio = background_rate / ref.centre_rate
    if UV_BAND[0] <= ratio <= UV_BAND[1]:
        return UvCheck("ok", ratio, None)
    for light in LIGHTS:
        other = newest(light)
        if light != declared and other is not None and other.centre_rate > 0:
            if UV_BAND[0] <= background_rate / other.centre_rate <= UV_BAND[1]:
                return UvCheck("warn", ratio, light)
    return UvCheck("warn", ratio, None)


_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def safe_name(text: str) -> str:
    return _SAFE.sub("-", text) or "flat"
