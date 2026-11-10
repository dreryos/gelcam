"""On-disk stack of one channel from N frames (never all frames in RAM).

Each RAW file is read exactly once; its channel goes into a float32 `numpy.memmap` of shape (N, H, W).
Saturated samples are stored as NaN so they can never enter a stacked result. The source RAW files are never modified.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .channel import saturation_mask, select_channel
from .raw_io import read_frame


@dataclass
class FrameStack:
    array: np.ndarray  # np.memmap (N, H, W) float32
    paths: list[Path]
    saturated: np.ndarray  # bool (H, W), union of per-frame saturation masks
    saturated_per_frame: list[float]  # saturated fraction per frame
    file: Path
    saturated_samples: int = 0  # saturated samples written as NaN (all frames together)

    def discard(self) -> None:
        """Closes the memmap and deletes its backing file (source RAW files are untouched)."""
        mm = getattr(self.array, "_mmap", None)
        if mm is not None:
            mm.close()
        self.array = np.empty((0, 0, 0), np.float32)
        self.file.unlink(missing_ok=True)


def plane_shape(path: Path, crop: bool = True) -> tuple[int, int]:
    """(H, W) of the channel plane `build_stack` would produce for this file."""
    frame = read_frame(path)
    if crop and frame.image_area is not None:
        return frame.image_area[2] // 2, frame.image_area[3] // 2
    return frame.mosaic.shape[0] // 2, frame.mosaic.shape[1] // 2


def _close(mm: np.ndarray | None) -> None:
    m = getattr(mm, "_mmap", None)
    if m is not None and not m.closed:
        m.close()


def build_stack(
    paths: Sequence[Path], channel: str, dest: Path, crop: bool = True, check: Callable[[], None] | None = None
) -> FrameStack:
    """Extracts `channel` from every file into a memmap at `dest`; one frame in RAM at a time.

    With `crop`, each plane is cut to the camera's official image area (when the frame knows it).
    `dest` must not exist (FileExistsError, also for a symlink); if anything fails the partial file is removed.
    `check` is called before each frame (cooperative cancellation: it may raise).
    """
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("No frames given")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    array: np.ndarray | None = None
    saturated: np.ndarray | None = None
    fractions: list[float] = []
    n_sat = 0
    created = False
    try:
        for i, path in enumerate(paths):
            if check is not None:
                check()
            frame = read_frame(path)
            plane = select_channel(frame, channel)
            sat = saturation_mask(frame, channel)
            if crop and frame.image_area is not None:
                top, left, h, w = frame.image_area
                if top % 2 or left % 2:
                    raise ValueError(f"Image area offsets must be even, got top={top}, left={left}")
                ys, xs = slice(top // 2, (top + h) // 2), slice(left // 2, (left + w) // 2)
                plane, sat = plane[ys, xs], sat[ys, xs]
            del frame
            if array is None:
                shape = (len(paths), *plane.shape)
                with open(dest, "xb") as fh:  # "x": never truncates an existing file or follows a symlink
                    created = True
                    fh.truncate(int(np.prod(shape, dtype=np.int64)) * 4)
                array = np.memmap(dest, dtype=np.float32, mode="r+", shape=shape)
                saturated = np.zeros(plane.shape, bool)
            elif plane.shape != array.shape[1:]:
                raise ValueError(f"Frame {path.name} has shape {plane.shape}, expected {array.shape[1:]}")
            array[i] = np.where(sat, np.float32(np.nan), plane)  # saturated samples must not enter any result
            saturated |= sat  # type: ignore[operator]
            fractions.append(float(sat.mean()))
            n_sat += int(sat.sum())
        assert array is not None and saturated is not None
        array.flush()
    except BaseException:
        _close(array)
        if created:
            dest.unlink(missing_ok=True)
        raise
    return FrameStack(array, paths, saturated, fractions, dest, n_sat)
