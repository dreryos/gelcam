"""Look at the flat-field library or add flats that were taken earlier.

    uv run python tools/flat_library.py list [--library DIR]
    uv run python tools/flat_library.py import --flats DIR --darks DIR --light white --seconds 8 --aperture 8 \\
        --target "white paper" [--channel R] [--iso 100] [--lens NAME] [--library DIR]

The library is `Documents/GelCam/calibration/flats` unless `--library` is given. `import` copies the frames
(the originals are not touched); flats taken with the wizard window are added automatically.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gelcam.acquisition.flat import register_existing  # noqa: E402
from gelcam.storage import flat_library as lib  # noqa: E402

FRAME_PATTERNS = ("*.CR2", "*.cr2", "*.npy")


def frames(folder: Path) -> list[Path]:
    return sorted({p for pattern in FRAME_PATTERNS for p in folder.glob(pattern)})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["list", "import"])
    ap.add_argument("--library", type=Path, default=None)
    ap.add_argument("--flats", type=Path)
    ap.add_argument("--darks", type=Path)
    ap.add_argument("--light", choices=lib.LIGHTS)
    ap.add_argument("--seconds", type=float)
    ap.add_argument("--aperture", type=float)
    ap.add_argument("--target", default="")
    ap.add_argument("--channel", default="R", choices=["R", "G", "B"])
    ap.add_argument("--iso", type=int, default=100)
    ap.add_argument("--lens", default=None)
    ap.add_argument("--zoom-marked", action="store_true", help="the zoom was at the marked position")
    args = ap.parse_args()
    root = args.library or lib.default_library_dir()

    if args.command == "list":
        found = lib.list_flats(root)
        print(f"{root}: {len(found)} flat set(s)")
        for f in found:
            a = lib.assess(f, lib.Arrangement(f.light, f.aperture, f.lens))
            print(f"  {f.id}  {f.light:5s} {f.seconds:g} s f/{f.aperture:g}  {len(f.flats)}+{len(f.darks)} frames  "
                  f"centre {f.centre_adu:.0f} ADU  corner {f.corner_ratio:.2f}  {a.age_days} d  {f.target!r}")
        return 0

    missing = [n for n in ("flats", "darks", "light", "seconds", "aperture") if getattr(args, n) is None]
    if missing:
        ap.error("import needs --" + ", --".join(missing))
    flat_files, dark_files = frames(args.flats), frames(args.darks)
    if not flat_files or not dark_files:
        ap.error("no frames (*.CR2, *.npy) found in --flats / --darks")
    made = register_existing(root, flat_files, dark_files, light=args.light, channel=args.channel, iso=args.iso,
                             seconds=args.seconds, aperture=args.aperture, target=args.target,
                             zoom_marked=args.zoom_marked, lens=args.lens)
    print(f"added {made.id}: {len(made.flats)} flats + {len(made.darks)} darks, centre {made.centre_adu:.0f} ADU, "
          f"darkest corner {made.corner_ratio:.2f} of the centre")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
