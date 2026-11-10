"""Writing the result image (linear 16-bit TIFF) and the display-only preview (8-bit PNG)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

PREVIEW_PERCENTILES = (0.5, 99.8)


def write_result_tiff(path: Path, img: np.ndarray) -> dict[str, Any]:
    """Linear 16-bit single-channel TIFF; `img` holds ADU above the master dark.

    Negative noise is clipped to 0 and values are rounded to integers; nothing else is applied. NaN (saturated in
    every frame, so no valid sample) is written as 65535 and counted as `saturated_in_all_frames`, not as clipped.
    Raises FileExistsError instead of overwriting.
    """
    import tifffile  # lazy

    path = Path(path)
    a = np.asarray(img)
    if a.ndim != 2:
        raise ValueError(f"Expected a single-channel 2-D image, got shape {a.shape}")
    nan = np.isnan(a)
    low, high = int((a < 0).sum()), int((a > 65535).sum())
    out = np.rint(np.clip(np.where(nan, np.float32(0), a), 0, 65535)).astype(np.uint16)
    out[nan] = 65535
    with open(path, "xb") as fh:  # "x": fails if the file exists
        tifffile.imwrite(fh, out, photometric="minisblack")
    return {"file": path.name, "dtype": "uint16", "units": "ADU above master dark",
            "shape": [int(out.shape[0]), int(out.shape[1])], "clipped_low": low, "clipped_high": high,
            "saturated_in_all_frames": int(nan.sum())}


def write_preview_png(path: Path, img: np.ndarray, invert: bool = False) -> dict[str, Any]:
    """8-bit preview with a percentile stretch (and optional inversion). Display only, never data."""
    from PIL import Image  # lazy

    path = Path(path)
    a = np.asarray(img, dtype=np.float32)
    nan = np.isnan(a)  # saturated in every frame: shown white
    ok = a[~nan] if nan.any() else a
    lo, hi = (float(v) for v in np.percentile(ok, PREVIEW_PERCENTILES)) if ok.size else (0.0, 1.0)
    if hi <= lo:
        hi = lo + 1.0
    if nan.any():
        a = np.where(nan, np.float32(hi), a)
    u8 = np.clip((a - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
    if invert:
        u8 = 255 - u8
    with open(path, "xb") as fh:
        Image.fromarray(u8).save(fh, format="PNG")
    return {"file": path.name, "dtype": "uint8", "stretch_percentiles": list(PREVIEW_PERCENTILES),
            "black": lo, "white": hi, "inverted": bool(invert), "note": "preview only, not for quantification"}
