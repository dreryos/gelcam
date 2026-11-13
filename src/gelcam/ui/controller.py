"""Bridge between the GUI and the camera.

All camera calls go through a single helper thread, so the GUI never
waits for the camera. Results are returned via Qt signals (thread-safe).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QObject, Signal

from ..camera import Camera, CameraError, CameraInfo, FocusStep, LensInfo, Prop
from ..processing.exposure import measure
from ..processing.focus import sharpness_rgb
from ..processing.raw_io import read_frame


class CameraController(QObject):
    connected = Signal(object)  # CameraInfo
    disconnected = Signal()
    options_ready = Signal(object)  # dict[Prop, tuple[list[int], int]]
    frame_ready = Signal(object)  # np.ndarray
    captured = Signal(object)  # Path
    message = Signal(str)
    error = Signal(str)
    busy_changed = Signal(bool)
    connect_failed = Signal(str)
    connection_lost = Signal()
    reconnected = Signal(object)  # CameraInfo
    measured = Signal(object, object)  # Path, ExposureMeasurement
    status_ready = Signal(object)  # dict: Prop -> int | str (image quality, battery) and "lens" -> LensInfo

    def __init__(self, camera_factory: Callable[[], Camera]) -> None:
        super().__init__()
        self._factory = camera_factory
        self._camera: Camera | None = None
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="camera-ui")
        self._measure_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="measure-ui")
        self._frame_pending = False
        self.live = False
        self.lost = False
        self._live_before_loss = False
        self.lens = LensInfo()  # latest from refresh_options
        self._closed = False

    # --- internal ---
    def _submit(self, fn: Callable[[], Any], on_ok: Callable[[Any], None] | None = None, busy: bool = True) -> None:
        if busy:
            self.busy_changed.emit(True)

        def job() -> None:
            try:
                result = fn()
                if on_ok is not None:
                    on_ok(result)
            except Exception as exc:  # noqa: BLE001 - shown to the operator
                cam = self._camera
                if cam is not None and not cam.is_connected:
                    if not self.lost:
                        self.lost = True
                        self._live_before_loss = self.live
                        self.live = False
                        self.connection_lost.emit()
                else:
                    self.error.emit(str(exc))
            finally:
                if busy:
                    self.busy_changed.emit(False)

        self._pool.submit(job)

    def _cam(self) -> Camera:
        if self._camera is None:
            raise RuntimeError(self.tr("Camera is not connected."))
        return self._camera

    # --- commands from the GUI ---
    def connect_camera(self) -> None:
        def do() -> CameraInfo | None:
            cam = self._factory()
            try:
                info = cam.connect()
            except CameraError as exc:
                self.connect_failed.emit(str(exc))
                return None
            self._camera = cam
            for w in getattr(cam, "warnings", []):
                self.message.emit(w)
            return info

        def ok(info: CameraInfo | None) -> None:
            if info is not None:
                self.connected.emit(info)
                self.refresh_options()

        self._submit(do, ok)

    def reconnect(self) -> None:
        """One reconnect attempt; failure is silent (the window counts attempts)."""

        def do() -> CameraInfo | None:
            if not self.lost or self._camera is None:  # cancelled or already reconnected
                return None
            try:
                return self._cam().reconnect(attempts=1, delay=0.0)  # type: ignore[attr-defined]
            except CameraError:
                return None

        def ok(info: CameraInfo | None) -> None:
            if info is None:
                return
            self.lost = False
            self.reconnected.emit(info)
            self.refresh_options()
            if self._live_before_loss:
                self.set_live_view(True)

        self._submit(do, ok, busy=False)

    def measure_file(self, path: Path, channel: str) -> None:
        """Exposure measurement of a captured file, off the camera thread."""

        if self._closed:
            return

        def job() -> None:
            try:
                self.measured.emit(path, measure(read_frame(path), channel))
            except Exception as exc:  # noqa: BLE001 - shown to the operator
                self.error.emit(str(exc))

        self._measure_pool.submit(job)

    def disconnect_camera(self) -> None:
        def do() -> None:
            if self._camera is not None:
                self._camera.disconnect()
            self._camera = None
            self.live = False
            self.lost = False
            self._live_before_loss = False

        self._submit(do, lambda _: self.disconnected.emit())

    def refresh_options(self) -> None:
        def do() -> dict:
            cam = self._cam()
            status = {}
            for p in (Prop.IMAGE_QUALITY, Prop.BATTERY):
                try:
                    status[p] = cam.get(p)
                except Exception:  # noqa: BLE001 - not every camera reports it
                    pass
            try:
                status["lens"] = cam.lens_info()
            except Exception:  # noqa: BLE001
                status["lens"] = LensInfo()
            self.lens = status["lens"]
            status["zooms"] = tuple(getattr(cam, "live_view_zooms", (1, 5, 10)))
            self.status_ready.emit(status)
            return {p: (cam.allowed_values(p), int(cam.get(p))) for p in (Prop.ISO, Prop.TV, Prop.AV)}

        self._submit(do, self.options_ready.emit)

    def set_value(self, prop: Prop, code: int) -> None:
        self._submit(lambda: self._cam().set(prop, code), lambda _: self.message.emit(self.tr("Set {0}.").format(prop.value)))

    def set_live_view(self, on: bool) -> None:
        def do() -> None:
            if on == self.live:  # redundant request: true no-op
                return
            cam = self._cam()
            cam.start_live_view() if on else cam.stop_live_view()
            self.live = on

        self._submit(do)

    def request_frame(self) -> None:
        """Called by the GUI timer; no new frame is requested until the previous one has arrived."""
        if not self.live or self._frame_pending or self._camera is None:
            return
        self._frame_pending = True

        def do() -> np.ndarray | None:
            try:
                return self._cam().live_view_frame()
            finally:
                self._frame_pending = False

        self._submit(do, lambda f: f is not None and self.frame_ready.emit(f), busy=False)

    def set_zoom(self, factor: int) -> None:
        self._submit(lambda: self._cam().set_live_view_zoom(factor))

    def autofocus(self) -> None:
        """Run AF and report what really happened, measured on live view frames before and after.

        The camera accepts the command without an error even when the lens does not move
        (e.g. the AF/MF switch is on MF) or there is nothing to focus on, so success is never assumed.
        """
        def do() -> tuple[float | None, float | None]:
            cam = self._cam()
            before = self._sharpness_now(cam)
            cam.autofocus()
            return before, self._sharpness_now(cam)

        def done(result: tuple[float | None, float | None]) -> None:
            self.message.emit(self._af_message(*result))

        self._submit(do, done)

    @staticmethod
    def _sharpness_now(cam: Camera, frames: int = 3) -> float | None:
        """Mean sharpness of a few fresh live view frames; None when none arrived."""
        values: list[float] = []
        for _ in range(frames * 4):
            frame = cam.live_view_frame()
            if frame is not None:
                values.append(sharpness_rgb(frame))
            if len(values) == frames:
                break
            time.sleep(0.1)
        return float(np.mean(values)) if values else None

    def _af_message(self, before: float | None, after: float | None) -> str:
        if before is None or after is None:
            return self.tr("Autofocus finished (sharpness could not be measured).")
        ratio = after / before if before > 0 else float("inf")
        numbers = f"{before:.1f} → {after:.1f}"
        if ratio >= 1.10:
            return self.tr("Focused: sharpness {0}.").format(numbers)
        if ratio >= 0.90:
            return self.tr(
                "Autofocus finished, sharpness unchanged ({0}). If the image is blurry, check that the lens "
                "switch is on AF and that a high-contrast target is in the centre of the image.").format(numbers)
        return self.tr(
            "Autofocus finished but sharpness dropped ({0}). Put a high-contrast target in the centre "
            "of the image and try again.").format(numbers)

    def focus_step(self, step: FocusStep) -> None:
        self._submit(lambda: self._cam().drive_focus(step))

    def capture(self, dest_dir: Path) -> None:
        self.message.emit(self.tr("Capturing…"))
        self._submit(lambda: self._cam().capture(dest_dir), self.captured.emit)

    def shutdown(self) -> None:
        self._closed = True
        if self._camera is not None:
            try:
                self._camera.disconnect()
            except Exception:  # noqa: BLE001
                pass
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._measure_pool.shutdown(wait=False, cancel_futures=True)
