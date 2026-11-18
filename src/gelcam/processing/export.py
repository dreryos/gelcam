"""Writing the result image (linear 16-bit TIFF), the display-only preview (8-bit PNG) and the black-and-white
TIFF of a single frame."""

from __future__ import annotations

import json
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


def frame_tiff_name(source: Path, inverted: bool) -> str:
    """`IMG_0001.CR2` -> `IMG_0001.tif`, or `IMG_0001_inverted.tif` for the inverted picture."""
    return f"{Path(source).stem}{'_inverted' if inverted else ''}.tif"


def write_frame_tiff(path: Path, frame: Any, channel: str, inverted: bool = False, source: str = "") -> dict[str, Any]:
    """Black-and-white 16-bit TIFF of ONE colour channel of a single RAW frame, e.g. for a quick look or a report.

    The channel is taken from the CFA mosaic as it is (no demosaicing, no interpolation: half the resolution of the
    sensor). Counts above the black level are scaled linearly so that the sensor's saturation level is 65535
    (`scale` below), so brightness ratios are kept. With `inverted` every value becomes 65535 - value (dark bands
    on a white background, as on a gel documentation system): that is a picture to look at; **quantify on the
    non-inverted file or on the RAW**. The RAW frame is never touched. Everything needed to undo the scaling and
    the inversion is stored in the TIFF description (JSON). Raises FileExistsError instead of overwriting.
    """
    import tifffile  # lazy

    from .channel import select_channel

    path = Path(path)
    black = float(frame.black_level(channel))
    span = float(frame.white_level) - black
    if span <= 0:
        raise ValueError("The white level is not above the black level")
    scale = 65535.0 / span
    plane = (select_channel(frame, channel) - np.float32(black)) * np.float32(scale)
    out = np.rint(np.clip(plane, 0, 65535)).astype(np.uint16)
    if inverted:
        out = np.uint16(65535) - out
    info = {
        "file": path.name, "source": source or getattr(frame, "source", ""), "channel": channel, "dtype": "uint16",
        "shape": [int(out.shape[0]), int(out.shape[1])], "black_level": black, "white_level": float(frame.white_level),
        "scale": scale, "units": "(raw - black_level) * scale", "inverted": bool(inverted),
        "note": ("inverted for viewing: value = 65535 - scaled value; quantify on the non-inverted file or the RAW"
                 if inverted else "linear in the raw counts"),
    }
    from .. import __version__

    with open(path, "xb") as fh:  # "x": fails if the file exists
        tifffile.imwrite(fh, out, photometric="minisblack", description=json.dumps(info),
                         software=f"GelCam {__version__}")
    return info


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
