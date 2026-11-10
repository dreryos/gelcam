"""Bridge between the GUI and the camera.

All camera calls go through a single helper thread, so the GUI never
waits for the camera. Results are returned via Qt signals (thread-safe).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QObject, Signal

from ..camera import Camera, CameraInfo, FocusStep, Prop


class CameraController(QObject):
    connected = Signal(object)  # CameraInfo
    disconnected = Signal()
    options_ready = Signal(object)  # dict[Prop, tuple[list[int], int]]
    frame_ready = Signal(object)  # np.ndarray
    captured = Signal(object)  # Path
    message = Signal(str)
    error = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, camera_factory: Callable[[], Camera]) -> None:
        super().__init__()
        self._factory = camera_factory
        self._camera: Camera | None = None
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="camera-ui")
        self._frame_pending = False
        self.live = False

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
                self.error.emit(str(exc))
            finally:
                if busy:
                    self.busy_changed.emit(False)

        self._pool.submit(job)

    def _cam(self) -> Camera:
        if self._camera is None:
            raise RuntimeError("Camera is not connected.")
        return self._camera

    # --- commands from the GUI ---
    def connect_camera(self) -> None:
        def do() -> CameraInfo:
            cam = self._factory()
            info = cam.connect()
            self._camera = cam
            for w in getattr(cam, "warnings", []):
                self.message.emit(w)
            return info

        def ok(info: CameraInfo) -> None:
            self.connected.emit(info)
            self.refresh_options()

        self._submit(do, ok)

    def disconnect_camera(self) -> None:
        def do() -> None:
            if self._camera is not None:
                self._camera.disconnect()
            self._camera = None
            self.live = False

        self._submit(do, lambda _: self.disconnected.emit())

    def refresh_options(self) -> None:
        def do() -> dict:
            cam = self._cam()
            return {p: (cam.allowed_values(p), int(cam.get(p))) for p in (Prop.ISO, Prop.TV, Prop.AV)}

        self._submit(do, self.options_ready.emit)

    def set_value(self, prop: Prop, code: int) -> None:
        self._submit(lambda: self._cam().set(prop, code), lambda _: self.message.emit(f"Set {prop.value}."))

    def set_live_view(self, on: bool) -> None:
        def do() -> None:
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
        self._submit(lambda: self._cam().autofocus(), lambda _: self.message.emit("Focused."))

    def focus_step(self, step: FocusStep) -> None:
        self._submit(lambda: self._cam().drive_focus(step))

    def capture(self, dest_dir: Path) -> None:
        self.message.emit("Capturing…")
        self._submit(lambda: self._cam().capture(dest_dir), self.captured.emit)

    def shutdown(self) -> None:
        if self._camera is not None:
            try:
                self._camera.disconnect()
            except Exception:  # noqa: BLE001
                pass
        self._pool.shutdown(wait=False, cancel_futures=True)
