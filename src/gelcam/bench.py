"""Measure whether this machine is fast enough for GelCam.

Run on the target PC:
    GelCam-console.exe --bench [--sample DIR]        (packaged build)
    uv run python tools/bench.py [--sample DIR]       (sources)

Reports what decides it: the live-view loop (must keep up with the camera's ~16.5 fps), a quick model of
the processing pipeline and, with `--sample`, the REAL pipeline on your frames (how long a series takes and
the peak memory, the binding constraint on a 2 GB machine). `--sample DIR` is a folder with the subfolders
`lights/` and `darks/` and, for the heaviest case, `flats/` and `flat_darks/`, each holding CR2 frames.
The report is also saved to %APPDATA%\\GelCam\\bench-<date>.txt.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np


class _Tee(io.StringIO):
    """Collects what is printed while it is also shown, so the report can be saved and sent."""

    def __init__(self) -> None:
        super().__init__()
        self._console = sys.stdout

    def write(self, text: str) -> int:
        self._console.write(text)
        self._console.flush()
        return super().write(text)

    def save(self) -> Path | None:
        try:
            from . import runtime

            path = runtime.data_dir() / f"bench-{time.strftime('%Y-%m-%d_%H%M')}.txt"
            path.write_text(self.getvalue(), encoding="utf-8")
            return path
        except OSError:
            return None


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

        # Without argument types ctypes passes the process handle as a 32-bit int and the call fails silently.
        kernel32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), wt.DWORD]
        psapi.GetProcessMemoryInfo.restype = wt.BOOL
        c = Counters()
        c.cb = ctypes.sizeof(c)
        if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return 0.0
        return c.PeakWorkingSetSize / 1e6  # the PEAK working set: what a 2 GB machine has to hold
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


def describe_machine() -> None:
    """OS, cores and memory of this PC: what a report needs to be understood later."""
    import platform

    print(f"  {platform.platform()} · {platform.machine()} · {os.cpu_count()} logical cores · {platform.processor()}")
    if sys.platform == "win32":
        import ctypes

        class Mem(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                        ("avail", ctypes.c_ulonglong), ("totalpage", ctypes.c_ulonglong),
                        ("availpage", ctypes.c_ulonglong), ("totalvirt", ctypes.c_ulonglong),
                        ("availvirt", ctypes.c_ulonglong), ("availext", ctypes.c_ulonglong)]

        m = Mem()
        m.length = ctypes.sizeof(m)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            print(f"  RAM {m.total / 1e9:.1f} GB, free now {m.avail / 1e9:.1f} GB")


def bench_real_pipeline(sample: Path) -> None:
    """The real pipeline (dark, flat, align, stack, export) on the operator's frames, with time per stage."""
    from .processing.pipeline import process

    def frames(name: str) -> list[Path]:
        return sorted({p for pattern in ("*.CR2", "*.cr2") for p in (sample / name).glob(pattern)})  # case-insensitive disks match twice

    lights, darks, flats, flat_darks = (frames(n) for n in ("lights", "darks", "flats", "flat_darks"))
    if not lights or not darks:
        print(f"\nReal pipeline: need CR2 frames in {sample / 'lights'} and {sample / 'darks'}, skipped")
        return
    use_flat = bool(flats and flat_darks)
    print(f"\nReal pipeline: {len(lights)} lights, {len(darks)} darks" +
          (f", {len(flats)} flats, {len(flat_darks)} flat darks" if use_flat else ", no flat field"))
    out = Path(tempfile.mkdtemp(prefix="gelcam-bench-"))
    t0 = time.perf_counter()
    last = [t0]

    def progress(msg: str, frac: float) -> None:
        now = time.perf_counter()
        print(f"  {now - t0:6.1f} s  {msg:<24s} (+{now - last[0]:.1f} s, peak {rss_mb():.0f} MB)")
        last[0] = now

    result = process(lights, darks, "R", out, flats=flats if use_flat else (), flat_darks=flat_darks if use_flat else (),
                     progress=progress)
    total = time.perf_counter() - t0
    print(f"  total {total:.1f} s, peak memory {rss_mb():.0f} MB, result {result.result.stat().st_size / 1e6:.0f} MB")
    if rss_mb() > 1000:
        print("  WARNING: the peak memory is high for a 2 GB machine.")
    import shutil

    shutil.rmtree(out, ignore_errors=True)


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
    ap.add_argument("--sample", type=Path, default=None,
                    help="folder with lights/ darks/ [flats/ flat_darks/] of CR2 frames: runs the real pipeline")
    args = ap.parse_args(argv)

    raw_dir = args.raw_dir
    if raw_dir.is_dir() and not list(raw_dir.glob("*.CR2")):
        subdirs = [d for d in sorted(raw_dir.iterdir()) if d.is_dir() and list(d.glob("*.CR2"))]
        if subdirs:
            raw_dir = subdirs[0]

    report = _Tee()
    with contextlib.redirect_stdout(report):
        print(f"GelCam benchmark · Python {sys.version.split()[0]} · {sys.platform} · {time.strftime('%Y-%m-%d %H:%M')}")
        describe_machine()
        bench_imports()
        bench_live_view()
        if args.sample is not None:
            bench_real_pipeline(args.sample)
        else:
            bench_pipeline(raw_dir, args.frames)
    saved = report.save()
    if saved:
        print(f"\nReport saved to {saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
