"""Porovná konstanty v gelcam.camera.edsdk.constants s hlavičkami Canon EDSDK.

Použití:
    uv run python tools/check_edsdk_constants.py [cesta/k/Header]

Výchozí cesta je vendor/edsdk/Header. Skript nic nemění, jen vypíše rozdíly
a vrátí nenulový kód, pokud nějaký najde.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gelcam.camera.edsdk import constants  # noqa: E402
from gelcam.camera.edsdk.binding import diritem_size_is_64bit  # noqa: E402

_DEFINE = re.compile(r"^\s*#define\s+(\w+)\s+\(?\s*(0x[0-9A-Fa-f]+|\d+)[uUlL]*\s*\)?", re.M)
_ENUM = re.compile(r"^\s*(\w+)\s*=\s*\(?\s*(0x[0-9A-Fa-f]+|\d+)[uUlL]*\s*\)?\s*,?", re.M)


def parse_headers(header_dir: Path) -> dict[str, int]:
    found: dict[str, int] = {}
    for h in sorted(header_dir.glob("*.h")):
        text = h.read_text(encoding="latin-1")
        for rx in (_DEFINE, _ENUM):
            for name, val in rx.findall(text):
                found.setdefault(name, int(val, 0))
    return found


def compare(ours: dict[str, int], theirs: dict[str, int]) -> tuple[list[str], list[str]]:
    mismatched, missing = [], []
    for name, val in sorted(ours.items()):
        if name not in theirs:
            missing.append(name)
        elif theirs[name] != val:
            mismatched.append(f"{name}: GelCam 0x{val:X}, hlavička 0x{theirs[name]:X}")
    return mismatched, missing


def main(argv: list[str]) -> int:
    header_dir = Path(argv[1]) if len(argv) > 1 else ROOT / "vendor" / "edsdk" / "Header"
    if not header_dir.exists():
        print(f"Složka s hlavičkami neexistuje: {header_dir}")
        return 2
    theirs = parse_headers(header_dir)
    mismatched, missing = compare(constants.CHECKED, theirs)
    print(f"Zkontrolováno {len(constants.CHECKED)} konstant proti {header_dir}")
    print(f"EdsDirectoryItemInfo.size: {'64' if diritem_size_is_64bit(header_dir) else '32'} bit")
    for line in mismatched:
        print("NESEDÍ  ", line)
    for name in missing:
        print("CHYBÍ   ", name, "(v hlavičkách nenalezeno – ověřit ručně)")
    if not mismatched and not missing:
        print("Vše sedí.")
    return 1 if mismatched else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
