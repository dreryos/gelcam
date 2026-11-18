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
from ..camera.base import check_allowed
from ..camera import values
from ..camera.values import av_fnumber
from ..acquisition.flat import analyze_flat
from ..processing.exposure import measure
from ..processing.export import frame_tiff_name, write_frame_tiff
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
    flat_analyzed = Signal(object, object)  # Path, FlatStats
    tiff_exported = Signal(object, object)  # RAW Path, TIFF Path
    live_boost_changed = Signal(object)  # {Prop: (live view value, operator's value)} while they differ, else None
    live_iso_flag_changed = Signal(bool)  # the "bright live view" switch, so every button can follow it
    status_ready = Signal(object)  # dict: Prop -> int | str (image quality, battery) and "lens" -> LensInfo

    MAGNIFIER_SETTLE = 0.6  # seconds the live view needs after the magnifier is switched
    LIVE_VIEW_F_NUMBER = 5.6  # aperture of the live view; if the lens does not offer it, its widest one
    LIVE_VIEW_BOOST_ISO = 6400  # ISO of the "bright live view" (the highest offered up to it)

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
        self.live_aperture = True  # open the aperture for the live view (a brighter picture); captures keep theirs
        self.live_iso = False  # "bright live view": a high ISO for the live view only; off until the operator asks
        self._operator: dict[Prop, int] = {}  # the operator's values while the live view runs with other ones
        self._live: dict[Prop, int] = {}  # what the live view runs with
        self.zoom = 1  # live view magnifier the operator asked for (the camera may drop out of it on its own)
        self.camera_model = ""  # of the connected camera, for the metadata of calibration sets
        self.zooms: tuple[int, ...] = (1, 5, 10)  # magnifier steps of the connected camera (refresh_options)
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
                self.camera_model = info.model
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

    def export_tiff(self, path: Path, channel: str, inverted: bool) -> None:
        """Black-and-white TIFF of one channel of a captured frame next to it, off the camera thread."""

        if self._closed:
            return

        def job() -> None:
            try:
                dest = path.with_name(frame_tiff_name(path, inverted))
                write_frame_tiff(dest, read_frame(path), channel, inverted, source=path.name)
                self.tiff_exported.emit(path, dest)
            except Exception as exc:  # noqa: BLE001 - shown to the operator
                self.error.emit(self.tr("Could not save the TIFF of {0}: {1}").format(path.name, exc))

        self._measure_pool.submit(job)

    def analyze_flat_file(self, path: Path, channel: str) -> None:
        """Centre level, corner falloff and saturation of a captured flat frame, off the camera thread."""

        if self._closed:
            return

        def job() -> None:
            try:
                self.flat_analyzed.emit(path, analyze_flat(read_frame(path), channel))
            except Exception as exc:  # noqa: BLE001 - shown to the operator
                self.error.emit(str(exc))

        self._measure_pool.submit(job)

    def disconnect_camera(self) -> None:
        def do() -> None:
            if self._camera is not None:
                self._restore_boost(self._camera)
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
            status["zooms"] = self.zooms = tuple(getattr(cam, "live_view_zooms", (1, 5, 10)))
            self.status_ready.emit(status)
            return {p: (cam.allowed_values(p), self._operator_value(cam, p)) for p in (Prop.ISO, Prop.TV, Prop.AV)}

        self._submit(do, self.options_ready.emit)

    def set_value(self, prop: Prop, code: int) -> None:
        def do() -> None:
            cam = self._cam()
            if prop in self._operator:  # the live view runs with other values: the choice is for the captures
                check_allowed(cam, prop, code)
                self._operator[prop] = code
                self._emit_boost()
                return
            cam.set(prop, code)

        self._submit(do, lambda _: self.message.emit(self.tr("Set {0}.").format(prop.value)))

    def set_live_view(self, on: bool) -> None:
        def do() -> None:
            if on == self.live:  # redundant request: true no-op
                return
            cam = self._cam()
            if on:
                cam.start_live_view()
                self._open_boost(cam)
            else:
                self._restore_boost(cam)
                cam.stop_live_view()
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
        self.zoom = factor
        self._submit(lambda: self._cam().set_live_view_zoom(factor))

    def autofocus(self) -> None:
        """Run AF and report what really happened, measured on live view frames before and after.

        The camera accepts the command without an error even when the lens does not move
        (e.g. the AF/MF switch is on MF) or there is nothing to focus on, so success is never assumed.

        Autofocus always runs in the normal (1x) view. Measured on the 100D: in the magnified view the camera
        drops back to 1x when autofocus runs, while the window still believed it was magnified (unstable
        picture, controls out of step). So the magnifier is switched off first, autofocus runs, and the
        magnifier the operator had is switched on again afterwards.
        """
        def do() -> tuple[float | None, float | None]:
            cam = self._cam()
            zoom = self.zoom
            if zoom != 1:
                cam.set_live_view_zoom(1)
                time.sleep(self.MAGNIFIER_SETTLE)  # the next frames are still magnified for a moment
            try:
                before = self._sharpness_now(cam)
                cam.autofocus()
                after = self._sharpness_now(cam)
            finally:
                if zoom != 1:
                    cam.set_live_view_zoom(zoom)
            return before, after

        def done(result: tuple[float | None, float | None]) -> None:
            self.message.emit(self._af_message(*result))

        self._submit(do, done)

    # --- the live view with other values than the captures (wide aperture, higher ISO)
    def _widest_av(self, cam: Camera) -> int | None:
        """f/5.6 if the camera offers it, otherwise the widest aperture it offers (the lowest f-number)."""
        allowed = cam.allowed_values(Prop.AV)
        if not allowed:
            return None
        wanted = [c for c in allowed if abs(av_fnumber(c) - self.LIVE_VIEW_F_NUMBER) < 0.05]
        return wanted[0] if wanted else min(allowed, key=av_fnumber)

    def _boost_iso(self, cam: Camera) -> int | None:
        """The highest ISO the camera offers up to `LIVE_VIEW_BOOST_ISO` (else its lowest numeric one)."""
        numeric = [(v, c) for c in cam.allowed_values(Prop.ISO) if (v := values.iso_value(c)) is not None]
        if not numeric:
            return None
        fit = [t for t in numeric if t[0] <= self.LIVE_VIEW_BOOST_ISO]
        return (max(fit) if fit else min(numeric))[1]

    def _targets(self, cam: Camera) -> dict[Prop, int]:
        targets: dict[Prop, int] = {}
        if self.live_aperture and (av := self._widest_av(cam)) is not None:
            targets[Prop.AV] = av
        if self.live_iso and (iso := self._boost_iso(cam)) is not None:
            targets[Prop.ISO] = iso
        return targets

    def _open_boost(self, cam: Camera) -> None:
        """Gives the live view its brighter values and remembers the operator's (camera thread)."""
        try:
            for prop, target in self._targets(cam).items():
                current = int(cam.get(prop))
                if prop not in self._operator:
                    if current == target:
                        continue  # already there and nothing to give back
                    self._operator[prop] = current
                if current != target:
                    cam.set(prop, target)  # a value from the camera's own list (rule 4)
                self._live[prop] = target
        except CameraError as exc:
            self.message.emit(self.tr("Could not brighten the live view: {0}").format(exc))
        self._emit_boost()

    def _restore_boost(self, cam: Camera, props: list[Prop] | None = None) -> None:
        """Gives the camera the operator's values back (camera thread); all of them, or only `props`."""
        for prop in [p for p in (props if props is not None else list(self._operator)) if p in self._operator]:
            code = self._operator.pop(prop)
            self._live.pop(prop, None)
            try:
                cam.set(prop, code)
            except CameraError as exc:
                self.message.emit(self.tr("Could not restore {0}: {1}").format(prop.value, exc))
        self._emit_boost()

    def _emit_boost(self) -> None:
        self.live_boost_changed.emit({p: (self._live.get(p, c), c) for p, c in self._operator.items()} or None)

    def _operator_value(self, cam: Camera, prop: Prop) -> int:
        """The value the operator has chosen, not the one the live view runs with."""
        if prop in self._operator:
            return self._operator[prop]
        return int(cam.get(prop))

    def set_live_aperture(self, on: bool) -> None:
        """Wide aperture for the live view on or off, at once if the live view is running."""
        self._set_boost_flag("live_aperture", Prop.AV, on)

    def set_live_iso(self, on: bool) -> None:
        """"Bright live view": a high ISO for the live view only (the captures keep the operator's ISO)."""
        self._set_boost_flag("live_iso", Prop.ISO, on)
        self.live_iso_flag_changed.emit(on)

    def _set_boost_flag(self, attr: str, prop: Prop, on: bool) -> None:
        setattr(self, attr, on)

        def do() -> None:
            if self._camera is None or not self.live:
                return  # takes effect when the live view starts
            cam = self._cam()
            if on:
                self._open_boost(cam)
            else:
                self._restore_boost(cam, [prop])

        self._submit(do, busy=False)

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
                "Autofocus finished, sharpness unchanged ({0}). If the image is already sharp, nothing is needed. "
                "If it is blurry: run autofocus again (it can fail when the lens is far out of focus; a few focus "
                "steps first can help), check that the lens switch is on AF and that a high-contrast target is in "
                "the centre of the image.").format(numbers)
        return self.tr(
            "Autofocus finished but sharpness dropped ({0}). Put a high-contrast target (marker lane, well "
            "edge, printed text) in the centre of the image and run autofocus again.").format(numbers)

    def focus_step(self, step: FocusStep) -> None:
        self._submit(lambda: self._cam().drive_focus(step))

    def capture(self, dest_dir: Path) -> None:
        self.message.emit(self.tr("Capturing…"))

        def do() -> Path:
            cam = self._cam()
            opened = bool(self._operator)
            if opened:  # the exposure is taken with the operator's values, never with the live view's
                self._restore_boost(cam)
            try:
                return cam.capture(dest_dir)
            finally:
                if opened and self.live:
                    self._open_boost(cam)

        self._submit(do, self.captured.emit)

    def shutdown(self) -> None:
        self._closed = True
        if self._camera is not None:
            try:
                self._restore_boost(self._camera)
                self._camera.disconnect()
            except Exception:  # noqa: BLE001
                pass
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._measure_pool.shutdown(wait=False, cancel_futures=True)
