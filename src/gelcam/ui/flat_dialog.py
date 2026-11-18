"""Window C1: taking a new flat field into the library (a test frame to find the exposure, the flat frames,
then the matching dark frames).

The flat is divided out, so it only has to be well exposed (centre at 50-80 % of the range, nothing saturated)
and taken for the arrangement it will be valid for: UV level, aperture, lens and the marked zoom position. The
target is a uniformly fluorescing surface at the place of the gel (a blank gel with the same dye is the best
one). The camera is reached only through the CameraController; a capture that is interrupted keeps the frames
already taken and continues after a reconnect.
"""

from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from ..acquisition import flat as flat_acq
from ..camera import Prop
from ..camera.values import iso_label, tv_code_at_most, tv_label, tv_seconds, av_label
from ..storage import flat_library as lib
from .controller import CameraController
from .widgets import Card, Note, StatValue

FRAME_CHOICES = (8, 16, 32)


class FlatDialog(QDialog):
    _built = Signal(object)  # FlatSet, or the exception that stopped building it (worker thread -> GUI thread)

    def __init__(
        self, controller: CameraController, library: Path, *, channel: str, light: str, opts: dict,
        codes: dict[Prop, int], lens: str | None = None, camera: str = "", parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("New flat field"))
        self.resize(640, 700)  # fits a 1366 x 768 screen; the body scrolls
        self.ctrl, self.library, self.channel = controller, library, channel
        self.opts = opts
        self.codes = dict(codes)  # ISO, shutter and aperture of this flat (the caller restores its own afterwards)
        self.lens, self.camera = lens, camera
        self.folder: Path | None = None
        self.flat_set: lib.FlatSet | None = None
        self.stats: flat_acq.FlatStats | None = None
        self.proposal_code: int | None = None
        self.flats_done = self.darks_done = False
        self._batch: dict[str, Any] | None = None
        self._test_dir: Path | None = None
        self._busy = False
        self._saving = False
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gelcam-flat")
        self._built.connect(self._on_built)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(1500)
        self._reconnect_timer.timeout.connect(self.ctrl.reconnect)
        self._lights = {"white": self.tr("White light"), "uv70": self.tr("UV 70 %"), "uv100": self.tr("UV 100 %")}
        self._build(light)
        self._wiring = [(ctrl_sig, slot) for ctrl_sig, slot in (
            (self.ctrl.captured, self._on_captured), (self.ctrl.flat_analyzed, self._on_analyzed),
            (self.ctrl.error, self._on_error), (self.ctrl.connection_lost, self._on_lost),
            (self.ctrl.reconnected, self._on_reconnected), (self.ctrl.options_ready, self._on_options))]
        for sig, slot in self._wiring:
            sig.connect(slot)
        self._refresh()

    # ------------------------------------------------------------------ layout
    def _build(self, light: str) -> None:
        outer = QVBoxLayout(self)
        body = QWidget()
        lay = QVBoxLayout(body)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        card = Card(self.tr("Arrangement"))
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Light")))
        self.light = QComboBox()
        for key, label in self._lights.items():
            self.light.addItem(label, key)
        self.light.setCurrentIndex(max(self.light.findData(light), 0))
        row.addWidget(self.light)
        row.addStretch()
        card.body.addLayout(row)
        self.target = QLineEdit(self.tr("blank gel with dye"))
        card.body.addWidget(QLabel(self.tr("Target (what is under the camera)")))
        card.body.addWidget(self.target)
        self.zoom_ok = QCheckBox(self.tr("Zoom is at the marked position"))
        card.body.addWidget(self.zoom_ok)
        self.info = QLabel()
        self.info.setProperty("role", "dim")
        self.info.setWordWrap(True)
        card.body.addWidget(self.info)
        lay.addWidget(card)
        lay.addWidget(Note(self.tr(
            "The flat is valid only for this UV level, aperture, lens and zoom position. The target must light "
            "up evenly over the whole field, at the place of the gel.")))

        card = Card(self.tr("Exposure"))
        stats = QHBoxLayout()
        self.st_centre = StatValue(self.tr("Centre"))
        self.st_corner = StatValue(self.tr("Darkest corner"))
        self.st_sat = StatValue(self.tr("Saturated"))
        for s in (self.st_centre, self.st_corner, self.st_sat):
            stats.addWidget(s)
        card.body.addLayout(stats)
        self.exposure = QLabel()
        card.body.addWidget(self.exposure)
        row = QHBoxLayout()
        self.btn_test = QPushButton(self.tr("Take test frame"))
        self.btn_test.clicked.connect(self._take_test)
        self.btn_apply = QPushButton(self.tr("Apply proposal"))
        self.btn_apply.clicked.connect(self._apply_proposal)
        self.btn_apply.setEnabled(False)
        row.addWidget(self.btn_test)
        row.addWidget(self.btn_apply)
        row.addStretch()
        card.body.addLayout(row)
        self.advice = Note("", "error")
        self.advice.hide()
        card.body.addWidget(self.advice)
        lay.addWidget(card)

        card = Card(self.tr("Flat frames"))
        row = QHBoxLayout()
        self.count = QComboBox()
        for n in FRAME_CHOICES:
            self.count.addItem(str(n), n)
        self.count.setCurrentIndex(self.count.findData(16))
        self.btn_flats = QPushButton(self.tr("Take flat frames"))
        self.btn_flats.setProperty("primary", True)
        self.btn_flats.clicked.connect(self._start_flats)
        row.addWidget(QLabel(self.tr("Frame count")))
        row.addWidget(self.count)
        row.addWidget(self.btn_flats)
        row.addStretch()
        card.body.addLayout(row)
        self.flat_bar = QProgressBar()
        self.flat_label = QLabel("")
        card.body.addWidget(self.flat_bar)
        card.body.addWidget(self.flat_label)
        lay.addWidget(card)

        card = Card(self.tr("Dark frames"))
        card.body.addWidget(Note(self.tr(
            "Same exposure time and ISO as the flat frames, taken with all light off: the flat must be "
            "dark-subtracted.")))
        self.dark_checks = [QCheckBox(t) for t in (
            self.tr("UV lamp and white light off"), self.tr("Cabinet door closed"), self.tr("Eyepiece covered"))]
        for cb in self.dark_checks:
            cb.toggled.connect(self._refresh)
            card.body.addWidget(cb)
        self.btn_darks = QPushButton(self.tr("Take dark frames"))
        self.btn_darks.setProperty("primary", True)
        self.btn_darks.clicked.connect(self._start_darks)
        card.body.addWidget(self.btn_darks)
        self.dark_bar = QProgressBar()
        self.dark_label = QLabel("")
        card.body.addWidget(self.dark_bar)
        card.body.addWidget(self.dark_label)
        lay.addWidget(card)

        lay.addStretch()
        self.status = Note("", "error")  # outside the scrolled body: always visible
        self.status.hide()
        outer.addWidget(self.status)
        row = QHBoxLayout()
        self.btn_cancel = QPushButton(self.tr("Cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_retry = QPushButton(self.tr("Resume"))
        self.btn_retry.clicked.connect(self._resume)
        self.btn_retry.hide()
        self.btn_save = QPushButton(self.tr("Save flat"))
        self.btn_save.setProperty("primary", True)
        self.btn_save.clicked.connect(self._save)
        row.addWidget(self.btn_cancel)
        row.addStretch()
        row.addWidget(self.btn_retry)
        row.addWidget(self.btn_save)
        outer.addLayout(row)

    # ------------------------------------------------------------------ state
    @property
    def seconds(self) -> float:
        return tv_seconds(self.codes[Prop.TV]) or 0.0

    def _arrangement_info(self) -> str:
        parts = [iso_label(self.codes[Prop.ISO]), av_label(self.codes[Prop.AV])]
        parts.append(self.lens or self.tr("lens not reported"))
        return " · ".join(parts)

    def _refresh(self) -> None:
        taking = self._batch is not None and not self._batch["paused"]
        idle = not taking and not self._busy and self.flat_set is None
        self.info.setText(self._arrangement_info())
        self.exposure.setText(self.tr("Exposure: {0}").format(tv_label(self.codes[Prop.TV])))
        locked = self.folder is not None
        self.light.setEnabled(idle and not locked)
        self.target.setEnabled(idle and not self.flats_done)
        self.zoom_ok.setEnabled(idle)
        self.count.setEnabled(idle and not self.flats_done)
        self.btn_test.setEnabled(idle and not self.flats_done)
        self.btn_flats.setEnabled(idle and not self.flats_done)
        self.btn_apply.setEnabled(idle and not self.flats_done and self.proposal_code is not None
                                  and self.proposal_code != self.codes[Prop.TV])
        for cb in self.dark_checks:
            cb.setEnabled(idle and self.flats_done and not self.darks_done)
        self.btn_darks.setEnabled(idle and self.flats_done and not self.darks_done
                                  and all(cb.isChecked() for cb in self.dark_checks))
        self.btn_save.setEnabled(idle and self.flats_done and self.darks_done)
        self.btn_cancel.setEnabled(not self._busy)

    def _show_error(self, text: str) -> None:
        self.status.setText(text)
        self.status.show()

    def _ensure_folder(self) -> Path:
        if self.folder is None:
            self.library.mkdir(parents=True, exist_ok=True)
            self.folder = lib.new_flat_dir(self.library, str(self.light.currentData()), datetime.now())
        return self.folder

    # ------------------------------------------------------------------ test frame and exposure
    def _take_test(self) -> None:
        folder = self._ensure_folder()
        self._test_dir = folder / "test"
        self._test_dir.mkdir(exist_ok=True)
        self.status.hide()
        self._busy = True
        self._refresh()
        self.ctrl.capture(self._test_dir)

    def _on_analyzed(self, path: Path, stats: flat_acq.FlatStats) -> None:
        if self._closed or self._test_dir is None or Path(path).parent != self._test_dir:
            return
        self._busy = False
        self.stats = stats
        self.st_centre.set_value(f"{stats.fraction * 100:.0f} %")
        self.st_corner.set_value(f"{stats.corner_ratio * 100:.0f} %")
        self.st_sat.set_value(f"{stats.saturated_fraction * 100:.2f} %")
        verdict = flat_acq.advice(stats)
        want = flat_acq.propose_flat_seconds(self.seconds, stats.fraction)
        self.proposal_code = tv_code_at_most(self.opts[Prop.TV][0], want)
        text = {
            None: "",
            "saturated": self.tr("Part of the flat is saturated. Shorten the exposure, or make the target dimmer."),
            "dark": self.tr("The flat is too dark (centre below 50 % of the range). Lengthen the exposure."),
            "bright": self.tr("The flat is too bright (centre above 80 % of the range). Shorten the exposure."),
        }[verdict]
        if verdict is not None and self.proposal_code is not None and self.proposal_code != self.codes[Prop.TV]:
            text += " " + self.tr("Proposal: {0}.").format(tv_label(self.proposal_code))
        self.advice.setText(text)
        self.advice.setVisible(bool(text))
        self._refresh()

    def _apply_proposal(self) -> None:
        if self.proposal_code is None:
            return
        self.codes[Prop.TV] = self.proposal_code
        self.ctrl.set_value(Prop.TV, self.proposal_code)
        self.proposal_code = None
        self.advice.hide()
        self._refresh()

    # ------------------------------------------------------------------ frame batches
    def _start_flats(self) -> None:
        folder = self._ensure_folder()
        self._start_batch("flat", folder / "flat", int(self.count.currentData()))

    def _start_darks(self) -> None:
        assert self.folder is not None
        self._start_batch("dark", self.folder / "dark", len(self._batch_files("flat")))

    def _batch_files(self, kind: str) -> list[Path]:
        assert self.folder is not None
        return sorted(p for p in (self.folder / kind).iterdir() if p.is_file())

    def _start_batch(self, kind: str, dest: Path, total: int) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        self._batch = {"kind": kind, "dest": dest, "total": total, "got": [], "paused": False, "resume": False}
        self.status.hide()
        self._progress()
        self._refresh()
        self.ctrl.capture(dest)

    def _progress(self) -> None:
        b = self._batch
        if b is None:
            return
        k, n = len(b["got"]), b["total"]
        bar, label = (self.flat_bar, self.flat_label) if b["kind"] == "flat" else (self.dark_bar, self.dark_label)
        bar.setMaximum(n)
        bar.setValue(k)
        label.setText(f"{k} / {n}")

    def _on_captured(self, path: Any) -> None:
        if self._closed:
            return
        path = Path(path)
        if self._test_dir is not None and path.parent == self._test_dir:
            self.ctrl.analyze_flat_file(path, self.channel)
            return
        b = self._batch
        if b is None or path.parent != b["dest"]:
            return
        b["got"].append(path)  # also while paused: the file is on disk
        self._progress()
        if b["paused"]:
            return
        if len(b["got"]) >= b["total"]:
            self._batch_done()
        else:
            self.ctrl.capture(b["dest"])

    def _batch_done(self) -> None:
        b, self._batch = self._batch, None
        assert b is not None
        if b["kind"] == "flat":
            self.flats_done = True
        else:
            self.darks_done = True
        self._refresh()

    def _on_error(self, msg: str) -> None:
        if self._closed:
            return
        self._busy = False
        if self._batch is not None and not self._batch["paused"]:
            self._interrupt(self.tr("The camera reported an error."), msg, lost=False)
        else:
            self._show_error(msg)
            self._refresh()

    def _on_lost(self) -> None:
        if self._closed:
            return
        self._busy = False
        if self._batch is not None:
            self._interrupt(self.tr("The camera disconnected."), "", lost=True)
        else:
            self._show_error(self.tr("Connection to the camera lost."))
            self._refresh()

    def _interrupt(self, what: str, detail: str, *, lost: bool) -> None:
        b = self._batch
        assert b is not None
        b["paused"] = True
        k, n = len(b["got"]), b["total"]
        self._show_error(f"{what} " + self.tr("{0} of {1} frames are kept.").format(k, n)
                         + (f"\n{detail}" if detail else "")
                         + ("\n" + self.tr("Reconnecting…") if lost else ""))
        if lost:
            b["resume"] = True
            self.ctrl.reconnect()
            self._reconnect_timer.start()
        self.btn_retry.setVisible(not lost)
        self._refresh()

    def _on_reconnected(self, _info: Any) -> None:
        b = self._batch
        if self._closed or b is None or not b["resume"]:
            return
        b["resume"] = False
        self._reconnect_timer.stop()
        self._resume()

    def _resume(self) -> None:
        b = self._batch
        if b is None:
            return
        self.btn_retry.hide()
        self.status.hide()
        b["paused"] = False
        if len(b["got"]) >= b["total"]:  # the capture that was in flight completed the batch
            return self._batch_done()
        for prop, code in self.codes.items():  # a reconnect can bring the camera back with its old values
            self.ctrl.set_value(prop, code)
        self._refresh()
        self.ctrl.capture(b["dest"])

    def _on_options(self, opts: dict) -> None:
        self.opts = opts

    # ------------------------------------------------------------------ finishing
    def _save(self) -> None:
        assert self.folder is not None
        self._busy = self._saving = True
        self.status.hide()
        self._refresh()
        folder, light = self.folder, str(self.light.currentData())
        shutil.rmtree(folder / "test", ignore_errors=True)  # test frames are not part of the set
        kwargs = dict(
            light=light, channel=self.channel, iso=iso_value_of(self.codes), seconds=self.seconds,
            aperture=aperture_of(self.codes), target=self.target.text().strip(), zoom_marked=self.zoom_ok.isChecked(),
            lens=self.lens, camera=self.camera)

        def work() -> None:
            try:
                out: object = flat_acq.build_flat_set(folder, **kwargs)
            except Exception as exc:  # noqa: BLE001 - reported in the dialog
                out = exc
            try:
                self._built.emit(out)
            except RuntimeError:  # dialog already destroyed
                pass

        self._executor.submit(work)

    def _on_built(self, out: object) -> None:
        if self._closed:
            return
        self._busy = self._saving = False
        if isinstance(out, BaseException):
            self._show_error(self.tr("Could not save the flat: {0}").format(out))
            self._refresh()
            return
        self.flat_set = out  # type: ignore[assignment]
        self.accept()

    # ------------------------------------------------------------------ closing
    def reject(self) -> None:
        if self._saving:
            return  # saving: not interruptible
        if self.folder is not None and self.flat_set is None and any(
                (self.folder / d).is_dir() and any((self.folder / d).iterdir()) for d in ("flat", "dark")):
            ask = QMessageBox.question(self, self.tr("Cancel"), self.tr(
                "The frames already taken are deleted because the flat is not finished. Cancel anyway?"))
            if ask != QMessageBox.StandardButton.Yes:
                return
        super().reject()

    def done(self, result: int) -> None:
        if not self._closed:
            self._closed = True
            self._reconnect_timer.stop()
            self._executor.shutdown(wait=False, cancel_futures=True)
            for sig, slot in self._wiring:
                try:
                    sig.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
            if self.flat_set is None and self.folder is not None:  # an unfinished set must not stay in the library
                shutil.rmtree(self.folder, ignore_errors=True)
        super().done(result)


def iso_value_of(codes: dict[Prop, int]) -> int:
    from ..camera.values import iso_value

    return iso_value(codes[Prop.ISO]) or 0


def aperture_of(codes: dict[Prop, int]) -> float:
    from ..camera.values import av_fnumber

    return av_fnumber(codes[Prop.AV])
