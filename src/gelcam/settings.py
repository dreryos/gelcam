"""User settings, stored in `%APPDATA%\\GelCam\\settings.json` (never in the program folder).

So far one setting: the root folder under which the application keeps everything it writes for the user:
`<root>/images/` (gel folders and single frames) and `<root>/calibration/flats/` (the flat-field library).
Unset, the root is `Documents/GelCam`. Existing folders are not moved when the root changes; the new root
applies to what is taken from then on.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_documents_dir

from . import runtime

SETTINGS_NAME = "settings.json"


def default_root() -> Path:
    return Path(user_documents_dir()) / "GelCam"


@dataclass(frozen=True)
class Settings:
    root: Path | None = None  # None = the default root
    live_view_aperture: bool = True  # open the aperture for the live view (f/5.6 or the widest); captures keep theirs

    @property
    def effective_root(self) -> Path:
        return self.root or default_root()

    @property
    def images_dir(self) -> Path:
        return self.effective_root / "images"

    @property
    def flats_dir(self) -> Path:
        return self.effective_root / "calibration" / "flats"


def settings_path() -> Path:
    return runtime.data_dir() / SETTINGS_NAME


def load() -> Settings:
    """The saved settings; a missing, unreadable or broken file means the defaults."""
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        root = data.get("root")
        return Settings(root=Path(root) if isinstance(root, str) and root.strip() else None,
                        live_view_aperture=data.get("live_view_aperture", True) is not False)
    except (OSError, ValueError, AttributeError):
        return Settings()


def save(settings: Settings) -> Path:
    """Writes the settings atomically."""
    target = settings_path()
    data = {"root": str(settings.root) if settings.root else None,
            "live_view_aperture": settings.live_view_aperture}
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target


def check_writable(folder: Path) -> str | None:
    """None when frames can be written under `folder` (it is created if needed), otherwise the reason."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".gelcam-write-test-")
        os.close(fd)
        Path(tmp).unlink(missing_ok=True)
    except OSError as exc:
        return str(exc)
    return None


def free_gb(folder: Path) -> float | None:
    """Free space of the disk holding `folder` (or its nearest existing parent), in GB."""
    path = folder
    while not path.exists() and path.parent != path:
        path = path.parent
    try:
        return shutil.disk_usage(path).free / 1e9
    except OSError:
        return None


def is_synchronised(folder: Path) -> bool:
    """True when the folder is under OneDrive, Dropbox or similar (the raw frames are 20 MB each)."""
    text = str(folder).lower()
    return any(name in text for name in ("onedrive", "dropbox", "google drive", "icloud"))
