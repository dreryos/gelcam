"""Per-gel output folder and its metadata.json."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .. import __version__


def create_gel_folder(root: Path, name: str, when: date) -> Path:
    """Creates `root/YYYY-MM-DD_name` with raw/ and calib/; never reuses an existing folder."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", name) or "gel"
    base = f"{when:%Y-%m-%d}_{safe}"
    folder, n = root / base, 1
    while folder.exists():
        n += 1
        folder = root / f"{base}_{n}"
    (folder / "raw").mkdir(parents=True)
    (folder / "calib").mkdir()
    return folder


def write_metadata(folder: Path, data: dict) -> Path:
    def default(o: Any) -> str:
        if isinstance(o, Path):
            return o.relative_to(folder).as_posix() if o.is_relative_to(folder) else str(o)
        raise TypeError(f"Not JSON serialisable: {type(o).__name__}")

    doc = {**data, "app_version": __version__, "written": datetime.now().astimezone().isoformat()}
    path = folder / "metadata.json"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=default), encoding="utf-8")
    return path
