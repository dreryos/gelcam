"""End-to-end processing: R = mean_σ((L_i − D) / F̂), exported as linear 16-bit TIFF plus a preview.

Memory: frames live in float32 memmaps under `work_dir` (never all in RAM); source files are only read.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .align import estimate_shift, needs_alignment, shift_image
from .binning import bin2x2
from .calib import calibrate, master_dark, master_flat
from .export import write_preview_png, write_result_tiff
from .framestack import FrameStack, build_stack
from .stack import sigma_clip_mean

TILE_ROWS = 64
BLOCK = 64


@dataclass
class PipelineResult:
    result: Path
    preview: Path
    steps: list[dict[str, Any]]
    stats: dict[str, Any]


def _close(mm: np.ndarray | None) -> None:
    m = getattr(mm, "_mmap", None)
    if m is not None and not m.closed:
        m.close()


def _background_patch(img: np.ndarray) -> tuple[int, int]:
    """Top-left corner of the lowest-variance BLOCK×BLOCK block (non-overlapping grid)."""
    best, pos = np.inf, (0, 0)
    for y in range(0, img.shape[0] - BLOCK + 1, BLOCK):
        for x in range(0, img.shape[1] - BLOCK + 1, BLOCK):
            v = float(img[y:y + BLOCK, x:x + BLOCK].var(dtype=np.float64))
            if v < best:
                best, pos = v, (y, x)
    return pos


def _noise(patch: np.ndarray) -> float:
    """Std of the patch after removing a fitted plane (slow gradients are not noise)."""
    h, w = patch.shape
    yy, xx = np.mgrid[0:h, 0:w]
    A = np.column_stack([np.ones(h * w), yy.ravel(), xx.ravel()])
    y = patch.ravel().astype(np.float64)
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    return float((y - A @ coef).std())


def process(
    lights: Sequence[Path],
    darks: Sequence[Path],
    channel: str,
    out_dir: Path,
    *,
    flats: Sequence[Path] = (),
    flat_darks: Sequence[Path] = (),
    binning: bool = False,
    work_dir: Path | None = None,
    progress: Callable[[str, float], None] | None = None,
) -> PipelineResult:
    if not lights:
        raise ValueError("No light frames given")
    if not darks:
        raise ValueError("No dark frames given")
    if flats and not flat_darks:
        raise ValueError("Flat frames need flat darks (the flat must be dark-subtracted)")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path, preview_path = out_dir / "result.tif", out_dir / "preview.png"
    for p in (result_path, preview_path):
        if p.exists():
            raise FileExistsError(f"{p} already exists; refusing to overwrite")
    work = Path(work_dir) if work_dir is not None else out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)

    steps: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    stacks: list[FrameStack] = []
    work_files: list[Path] = []
    n = len(lights)
    cal: np.memmap | None = None

    def report(msg: str, frac: float) -> None:
        if progress is not None:
            progress(msg, frac)

    def stack_of(paths: Sequence[Path], name: str) -> FrameStack:
        st = build_stack(paths, channel, work / f"{name}.f32", crop=True)
        stacks.append(st)
        return st

    try:
        report("Reading light frames", 0.0)
        lt = stack_of(lights, "lights")
        shape = lt.array.shape[1:]
        steps.append({"step": "read_lights", "frames": [Path(p).name for p in lights], "channel": channel,
                      "shape": list(shape), "crop_to_image_area": True})

        report("Reading dark frames", 0.15)
        dk = stack_of(darks, "darks")
        if dk.array.shape[1:] != shape:
            raise ValueError(f"Dark shape {dk.array.shape[1:]} differs from light shape {shape}")
        dark = master_dark(dk.array, TILE_ROWS)
        steps.append({"step": "master_dark", "frames": [Path(p).name for p in darks], "method": "sigma-clipped mean",
                      "median_adu": float(np.median(dark))})
        dk.discard()

        flat: np.ndarray | None = None
        if flats:
            report("Building master flat", 0.25)
            fl, fd = stack_of(flats, "flats"), stack_of(flat_darks, "flat_darks")
            if fl.array.shape[1:] != shape or fd.array.shape[1:] != shape:
                raise ValueError("Flat / flat-dark shape differs from light shape")
            flat, clipped = master_flat(fl.array, master_dark(fd.array, TILE_ROWS), tile_rows=TILE_ROWS)
            steps.append({"step": "master_flat", "flats": [Path(p).name for p in flats],
                          "flat_darks": [Path(p).name for p in flat_darks], "clipped_pixels": clipped})
            fl.discard()
            fd.discard()
        else:
            steps.append({"step": "master_flat", "skipped": True})

        report("Calibrating", 0.35)
        cal_file = work / "calibrated.f32"
        work_files.append(cal_file)
        cal = np.memmap(cal_file, dtype=np.float32, mode="w+", shape=lt.array.shape)
        for i in range(n):
            for r in range(0, shape[0], TILE_ROWS):
                rows = slice(r, r + TILE_ROWS)
                cal[i, rows] = calibrate(np.asarray(lt.array[i, rows]), dark[rows],
                                         None if flat is None else flat[rows])
        saturated = lt.saturated
        sat_frac = lt.saturated_per_frame
        lt.discard()
        del dark, flat
        steps.append({"step": "calibrate", "formula": "(L - D) / F_hat" if flats else "L - D", "frames": n})

        report("Aligning", 0.5)
        shifts: list[list[float]] = [[0.0, 0.0]]
        applied = 0
        for i in range(1, n):
            dy, dx = estimate_shift(cal[0], cal[i])
            shifts.append([round(dy, 3), round(dx, 3)])
            if needs_alignment(dy, dx):
                cal[i] = shift_image(cal[i], dy, dx)
                applied += 1
        steps.append({"step": "align", "reference": 0, "shifts_dy_dx": shifts, "frames_shifted": applied,
                      "threshold_px": 0.5})
        stats["shift_max_px"] = max(max(abs(a), abs(b)) for a, b in shifts)

        report("Stacking", 0.65)
        result, rejected = sigma_clip_mean(cal, sigma=3.0, iterations=3, tile_rows=TILE_ROWS)
        steps.append({"step": "stack", "method": "sigma-clipped mean", "sigma": 3.0, "iterations": 3,
                      "frames": n, "rejected_samples": rejected,
                      "rejected_fraction": rejected / float(cal.size)})
        stats["rejected_samples"] = rejected

        y, x = _background_patch(result)
        single = _noise(np.asarray(cal[0, y:y + BLOCK, x:x + BLOCK]))
        stacked = _noise(result[y:y + BLOCK, x:x + BLOCK])
        stats.update(background_noise_single=single, background_noise_result=stacked,
                     background_noise_ratio=stacked / single if single > 0 else float("nan"),
                     background_patch_yx=[y, x])
        _close(cal)
        cal = None

        n_sat = int(saturated.sum())
        stats.update(saturated_pixels=n_sat, saturated_fraction=n_sat / float(saturated.size),
                     saturated_per_frame=sat_frac, frames_used=n)
        if n_sat:
            steps.append({"step": "warning", "message": "saturated pixels in the light frames; "
                          "bands there cannot be quantified", "saturated_pixels": n_sat,
                          "saturated_fraction": stats["saturated_fraction"]})

        if binning:
            result = bin2x2(result)
            steps.append({"step": "binning", "factor": 2, "mode": "mean", "shape": list(result.shape)})

        report("Writing result", 0.9)
        steps.append({"step": "export_result", **write_result_tiff(result_path, result)})
        steps.append({"step": "export_preview", **write_preview_png(preview_path, result)})
        stats["result_shape"] = list(result.shape)
        report("Done", 1.0)
        return PipelineResult(result_path, preview_path, steps, stats)
    finally:
        _close(cal)
        for st in stacks:
            st.discard()
        for f in work_files:
            f.unlink(missing_ok=True)
        try:
            work.rmdir()  # only if empty: never delete something we did not create
        except OSError:
            pass


def _paths(folder: Path, items: Sequence[str]) -> list[Path]:
    return [p if p.is_absolute() else folder / p for p in map(Path, items)]


def process_gel_folder(
    folder: Path, progress: Callable[[str, float], None] | None = None, *, binning: bool = False
) -> PipelineResult:
    """Processes a wizard-made gel folder in place and records the steps in metadata.json."""
    from ..storage.gel_folder import write_metadata

    folder = Path(folder)
    if (folder / "result.tif").exists():
        raise FileExistsError(f"{folder / 'result.tif'} already exists; refusing to overwrite")
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    res = process(
        _paths(folder, meta["light_frames"]), _paths(folder, meta["dark_frames"]), meta["profile"]["channel"],
        folder, flats=_paths(folder, meta.get("flat_frames", [])),
        flat_darks=_paths(folder, meta.get("flat_dark_frames", [])), binning=binning, progress=progress)
    write_metadata(folder, {**meta, "processing": res.steps, "stats": res.stats, "result": "result.tif",
                            "preview": "preview.png", "status": "processed"})
    return res
