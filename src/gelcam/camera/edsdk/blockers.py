"""Detekce aplikací, které mohou držet foťák (EDSDK pak foťák nevidí)."""

from __future__ import annotations

import subprocess
import sys

#: Názvy procesů (malými písmeny, bez .exe), které typicky obsazují USB spojení s foťákem.
KNOWN_BLOCKERS: dict[str, str] = {
    "eos utility": "EOS Utility",
    "eos utility 3": "EOS Utility 3",
    "eosutility": "EOS Utility",
    "digicamcontrol": "digiCamControl",
    "cameracontrol": "digiCamControl",
    "qdslrdashboard": "qDslrDashboard",
    "capture one": "Capture One",
    "lightroom": "Lightroom",
    "nina": "N.I.N.A.",
    "canon camera window": "Canon CameraWindow",
    "cameraWindow".lower(): "Canon CameraWindow",
}


def parse_tasklist(output: str) -> list[str]:
    """Z výstupu `tasklist /fo csv /nh` vybere názvy známých blokujících aplikací."""
    found: list[str] = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith('"'):
            continue
        image = line.split('","')[0].strip('"').lower()
        if image.endswith(".exe"):
            image = image[:-4]
        label = KNOWN_BLOCKERS.get(image)
        if label and label not in found:
            found.append(label)
    return found


def find_blockers() -> list[str]:
    """Názvy běžících aplikací, které mohou držet foťák. Mimo Windows prázdný seznam."""
    if sys.platform != "win32":
        return []
    try:
        out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
                             timeout=10, creationflags=0x08000000).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_tasklist(out)
