"""Build the Windows package:  uv run python packaging/build.py [--no-edsdk] [--no-zip]

1. PyInstaller (packaging/gelcam.spec) -> dist/GelCam/
2. copy the 64-bit Canon EDSDK DLLs from vendor/edsdk/Dll to dist/GelCam/edsdk/Dll (see the licence note)
3. dist/GelCam-<version>-win64.zip

Canon licence: vendor/edsdk/ itself is never committed. Whether the DLLs may be handed to other PCs is
governed by the terms accepted in the Canon Developer Programme; check them before giving the zip away
(`--no-edsdk` builds a package without the DLLs; copy them into edsdk/Dll/ on each PC instead).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gelcam import __version__  # noqa: E402


#: Files GelCam never uses (checked by the self-test after trimming): video codecs of OpenCV, the
#: software OpenGL fallback of Qt (only QtQuick / OpenGL widgets need it) and AVIF support of Pillow.
UNUSED = ("opencv_videoio_ffmpeg*.dll", "opengl32sw.dll", "_avif*.pyd")


def trim(out: Path) -> float:
    """Delete UNUSED files from the package; returns the freed megabytes."""
    freed = 0.0
    for pattern in UNUSED:
        for f in out.rglob(pattern):
            freed += f.stat().st_size / 1e6
            f.unlink()
    return freed


def folder_size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-edsdk", action="store_true", help="do not copy the Canon EDSDK DLLs into the package")
    ap.add_argument("--no-zip", action="store_true")
    args = ap.parse_args()

    import PyInstaller.__main__ as pyi

    dist, work = ROOT / "dist", ROOT / "build" / "pyinstaller"
    out = dist / "GelCam"
    if out.exists():
        shutil.rmtree(out)
    pyi.run([str(ROOT / "packaging" / "gelcam.spec"), "--noconfirm", "--distpath", str(dist), "--workpath", str(work)])
    if not (out / "GelCam.exe").exists():
        print("PyInstaller did not produce GelCam.exe", file=sys.stderr)
        return 1

    print(f"trimmed unused files: {trim(out):.0f} MB")
    dll_src = ROOT / "vendor" / "edsdk" / "Dll"
    if args.no_edsdk:
        print("EDSDK DLLs: not included (--no-edsdk)")
    elif not dll_src.exists():
        print(f"WARNING: {dll_src} not found; the package works only with the simulation (--mock).")
    else:
        target = out / "edsdk" / "Dll"
        target.mkdir(parents=True, exist_ok=True)
        for dll in dll_src.glob("*.dll"):
            shutil.copy2(dll, target / dll.name)
        print("EDSDK DLLs:", ", ".join(sorted(p.name for p in target.glob("*.dll"))))

    print(f"package: {out}  ({folder_size_mb(out):.0f} MB)")
    if not args.no_zip:
        archive = dist / f"GelCam-{__version__}-win64.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(out.rglob("*")):
                if f.is_file():
                    zf.write(f, Path("GelCam") / f.relative_to(out))
        print(f"zip: {archive}  ({archive.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
