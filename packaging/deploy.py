"""Copy the built package to a folder (e.g. a USB stick) for testing on another PC.

    uv run python packaging/deploy.py --to E:\\GelCam-lab [--sample testdata/bench_sample] [--no-build-check]

Creates `<to>/GelCam/` (the program, replaced if an earlier deployment is there), `<to>/sample/` (frames for
`--bench`, optional) and `<to>/LAB-TEST-CHECKLIST.txt`, then verifies every copied file by size. It refuses to
write into a folder that holds something else.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def tree_size(path: Path) -> tuple[int, int]:
    files = [p for p in path.rglob("*") if p.is_file()]
    return len(files), sum(p.stat().st_size for p in files)


def copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst)
    if tree_size(src) != tree_size(dst):
        raise RuntimeError(f"Copy of {src} differs from the original (files / bytes): {tree_size(src)} vs {tree_size(dst)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", type=Path, required=True)
    ap.add_argument("--sample", type=Path, default=None, help="folder with lights/ darks/ flats/ flat_darks/ of CR2 frames")
    args = ap.parse_args()

    package = ROOT / "dist" / "GelCam"
    if not (package / "GelCam.exe").exists():
        print("dist/GelCam is not built: run  uv run python packaging/build.py  first", file=sys.stderr)
        return 1
    target = args.to
    known = {"GelCam", "sample", "LAB-TEST-CHECKLIST.txt"}
    if target.exists() and any(p.name not in known for p in target.iterdir()):
        print(f"{target} holds other things; use an empty or new folder", file=sys.stderr)
        return 1
    target.mkdir(parents=True, exist_ok=True)

    app = target / "GelCam"
    if app.exists():
        if not (app / "GelCam.exe").exists():
            print(f"{app} exists but is not a GelCam deployment", file=sys.stderr)
            return 1
        shutil.rmtree(app)
    copy_tree(package, app)
    n, size = tree_size(app)
    print(f"GelCam: {n} files, {size / 1e6:.0f} MB -> {app}")

    shutil.copy2(ROOT / "packaging" / "LAB-TEST-CHECKLIST.txt", target / "LAB-TEST-CHECKLIST.txt")
    if args.sample is not None:
        sample = target / "sample"
        if sample.exists():
            shutil.rmtree(sample)
        copy_tree(args.sample, sample)
        n, size = tree_size(sample)
        print(f"sample: {n} files, {size / 1e6:.0f} MB -> {sample}")
    print("checklist:", target / "LAB-TEST-CHECKLIST.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
