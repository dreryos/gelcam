"""`python -m gelcam.processing <gel_folder> [--binning]` – process a gel folder from the command line."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import process_gel_folder


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gelcam.processing", description=__doc__)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--binning", action="store_true", help="2×2 software binning of the result")
    args = ap.parse_args(argv)
    try:
        res = process_gel_folder(args.folder, lambda msg, f: print(f"[{f:4.0%}] {msg}", flush=True),
                                 binning=args.binning)
    except Exception as exc:  # noqa: BLE001 - report any failure as one clear line
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"result:  {res.result}\npreview: {res.preview}")
    print(json.dumps(res.stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
