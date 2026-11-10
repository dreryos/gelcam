"""Measure whether this machine is fast enough for GelCam.

Run on the target PC:    uv run python tools/bench.py [--raw-dir DIR]

Reports the three things that decide it: the live-view loop (must keep up with
the camera's ~16.5 fps), the processing pipeline (how long a series takes) and
the memory footprint (the binding constraint on a 2 GB machine).
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np


def rss_mb() -> float:
    """Resident set size in MB, on Windows and on POSIX."""
    try:
        import psutil

        return psutil.Process().memory_info().rss / 1e6
    except ImportError:
        pass
    if sys.platform == "win32":
        import ctypes
        import ctypes.wintypes as wt

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        c = Counters()
        c.cb = ctypes.sizeof(c)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb)
        return c.PeakWorkingSetSize / 1e6
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1e6 if sys.platform == "darwin" else peak / 1e3


def bench_imports() -> None:
    print("Memory footprint")
    print(f"  bare Python              {rss_mb():6.0f} MB")
    import numpy  # noqa: F401

    print(f"  + numpy                  {rss_mb():6.0f} MB")
    import rawpy  # noqa: F401

    print(f"  + rawpy                  {rss_mb():6.0f} MB")
    try:
        import PySide6.QtWidgets  # noqa: F401

        print(f"  + PySide6                {rss_mb():6.0f} MB")
    except ImportError:
        print("  + PySide6                not installed")
    import cv2  # noqa: F401

    print(f"  + opencv                 {rss_mb():6.0f} MB")


def bench_live_view(frames: int = 40) -> None:
    import cv2
    from PIL import Image

    rng = np.random.default_rng(0)
    scene = np.clip(rng.normal(40, 8, (640, 960)), 0, 255).astype(np.uint8)
    scene[200:240] = 180
    buf = io.BytesIO()
    Image.fromarray(scene).save(buf, "JPEG", quality=85)
    jpg = buf.getvalue()
    lut = np.clip(((np.arange(256) - 15) / 117.0).clip(0) ** 0.55 * 255, 0, 255).astype(np.uint8)

    def timed(fn):
        t0 = time.perf_counter()
        for _ in range(frames):
            fn()
        return (time.perf_counter() - t0) / frames * 1000

    decoded = np.asarray(Image.open(io.BytesIO(jpg)).convert("L"))
    t_dec = timed(lambda: np.asarray(Image.open(io.BytesIO(jpg)).convert("L")))
    t_lut = timed(lambda: lut[decoded])
    t_hist = timed(lambda: np.bincount(decoded.ravel(), minlength=256))
    t_lap = timed(lambda: cv2.Laplacian(decoded, cv2.CV_32F).var())
    t_lap2 = timed(lambda: cv2.Laplacian(decoded[::2, ::2], cv2.CV_32F).var())
    total = t_dec + t_lut + t_hist + t_lap

    print("\nLive view loop (960 x 640)")
    print(f"  JPEG decode              {t_dec:6.1f} ms")
    print(f"  display LUT              {t_lut:6.1f} ms")
    print(f"  histogram                {t_hist:6.1f} ms")
    print(f"  sharpness (full)         {t_lap:6.1f} ms")
    print(f"  sharpness (half res)     {t_lap2:6.1f} ms")
    print(f"  per frame                {total:6.1f} ms -> {1000 / total:.0f} fps "
          f"(camera delivers ~16.5)")
    if total > 60:
        print("  WARNING: below the camera's frame rate; compute histogram and")
        print("           sharpness on every other frame and on half resolution.")


def bench_pipeline(raw_dir: Path, count: int = 8) -> None:
    import rawpy

    files = sorted(raw_dir.glob("*.CR2"))[:count]
    if not files:
        print(f"\nPipeline: no CR2 files in {raw_dir}, skipped")
        return

    tmp = Path(tempfile.mkdtemp()) / "cube.dat"
    t0 = time.perf_counter()
    cube = None
    for k, f in enumerate(files):
        with rawpy.imread(str(f)) as r:
            channel = r.raw_image_visible[0::2, 0::2]
            if cube is None:
                cube = np.memmap(tmp, np.float32, "w+", shape=(len(files),) + channel.shape)
            cube[k] = channel
    cube.flush()
    t_read = time.perf_counter() - t0

    n, h, w = cube.shape
    tiles = 8
    t0 = time.perf_counter()
    out = np.empty((h, w), np.float32)
    for i in range(tiles):
        a, b = i * h // tiles, (i + 1) * h // tiles
        buf = np.array(cube[:, a:b, :])
        mu, sd = buf.mean(0), buf.std(0)
        np.copyto(buf, np.nan, where=np.abs(buf - mu) > 3 * sd)
        out[a:b] = np.nanmean(buf, 0)
        del buf
    t_stack = time.perf_counter() - t0

    print(f"\nPipeline ({n} frames, channel {w} x {h} = {w * h / 1e6:.1f} Mpx)")
    print(f"  read CR2 + channel       {t_read:6.2f} s ({t_read / n * 1000:.0f} ms/frame)")
    print(f"  3-sigma clip + mean      {t_stack:6.2f} s (in {tiles} tiles)")
    print(f"  total                    {t_read + t_stack:6.2f} s")
    print(f"  temporary file           {tmp.stat().st_size / 1e6:6.0f} MB")
    print(f"  peak memory              {rss_mb():6.0f} MB")
    del cube
    tmp.unlink()
    if rss_mb() > 700:
        print("  WARNING: close to what a 2 GB machine can give; raise the tile count.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bench")
    ap.add_argument("--raw-dir", type=Path, default=Path("testdata/calib"),
                    help="directory with CR2 frames (its first subdirectory is used)")
    ap.add_argument("--frames", type=int, default=8)
    args = ap.parse_args(argv)

    raw_dir = args.raw_dir
    if raw_dir.is_dir() and not list(raw_dir.glob("*.CR2")):
        subdirs = [d for d in sorted(raw_dir.iterdir()) if d.is_dir() and list(d.glob("*.CR2"))]
        if subdirs:
            raw_dir = subdirs[0]

    print(f"GelCam benchmark · Python {sys.version.split()[0]} · {sys.platform}")
    bench_imports()
    bench_live_view()
    bench_pipeline(raw_dir, args.frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
