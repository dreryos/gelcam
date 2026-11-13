"""Seven-step capture wizard: profile, scene, focus, test exposure, calibration, series, review.

The wizard captures frames into a gel folder and writes metadata.json. Step 7 can also run the
processing pipeline on a background thread (result.tif + preview.png); without it the metadata
states "processing pending".
The camera is reached only through CameraController; controller signals are broadcast to every
listener, so each one is filtered by the folder the wizard asked for.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from PySide6.QtCore import QEventLoop, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from ..acquisition.profiles import DEFAULT_PROFILES, DyeProfile
from ..camera import FocusStep, Prop
from ..camera.values import av_fnumber, av_label, iso_label, iso_value, tv_code_at_most, tv_label, tv_seconds
from ..processing.exposure import ExposureMeasurement, propose_seconds
from ..processing.focus import sharpness_rgb
from ..processing.pipeline import ProcessingCancelled, process_gel_folder
from ..storage.gel_folder import create_gel_folder, write_metadata
from . import theme
from .controller import CameraController
from .widgets import Card, Note, PreviewView, StatValue

STEP_COUNT = 7
SATURATION_LIMIT = 0.001  # fraction of saturated pixels that triggers the warning
AF_MIN_GAIN = 1.10  # sharpness after AF must beat the value before by 10 %
STATUS = "captured; processing pending"


def _secs(code: int) -> str:
    s = tv_seconds(code)
    return "Bulb" if s is None else f"{s:g} s"


def pick_iso(allowed: list[int], target: int) -> int | None:
    """Highest allowed ISO not above `target` (else the lowest numeric one)."""
    vals = [(v, c) for c in allowed if (v := iso_value(c)) is not None]
    if not vals:
        return None
    fit = [t for t in vals if t[0] <= target]
    return max(fit)[1] if fit else min(vals)[1]


class GelWizard(QDialog):
    _proc_progress = Signal(str)  # emitted from the worker thread, delivered on the GUI thread
    _proc_done = Signal(object)  # PipelineResult or an Exception

    def __init__(self, controller: CameraController, out_root: Path, light: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctrl = controller
        self.out_root = out_root
        self.setWindowTitle(self.tr("New gel image"))
        self.resize(960, 640)

        self.idx = 0
        self.folder: Path | None = None
        self.opts: dict[Prop, tuple[list[int], int]] = {}
        self.codes: dict[Prop, int] = {}  # exposure the wizard set (allowed codes only)
        self.applied = False
        self.proposal_code: int | None = None
        self.test_frames: list[Path] = []
        self.light_frames: list[Path] = []
        self.dark_frames: list[Path] = []
        self.discarded: list[Path] = []
        self.series_done = False
        self.darks_done = False
        self.sharp_now: float | None = None
        self.sharp_before: float | None = None
        self.sharp_after: float | None = None
        self.af_state = "idle"  # idle -> running -> settling -> idle
        self._busy = 0
        self._frame_n = 0
        self._batch: dict[str, Any] | None = None
        self._box: QMessageBox | None = None
        self._box_btns: tuple[QAbstractButton, QAbstractButton] | None = None
        self._test_dir: Path | None = None
        self._live_at_open = controller.live
        self._closed = False
        self._processing = False
        self._proc_out: object = None  # worker result, readable even if the dialog closes first
        self._future: Future[None] | None = None
        self._cancel = threading.Event()
        self._metadata_written = False
        self._frozen: tuple[DyeProfile, int] | None = None  # (profile, UV level) at the first frame
        self.processed = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gelcam-process")
        self._proc_progress.connect(self._on_proc_progress)
        self._proc_done.connect(self._on_proc_done)

        self._timer = QTimer(self)  # drives live view while a preview is on screen
        self._timer.setInterval(60)
        self._timer.timeout.connect(self.ctrl.request_frame)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(1500)
        self._reconnect_timer.timeout.connect(self.ctrl.reconnect)

        self._lights = (("white", self.tr("White light")), ("uv70", self.tr("UV 70 %")),
                        ("uv100", self.tr("UV 100 %")))
        self._light = light
        self._build(light)

        self._wiring = [
            (self.ctrl.options_ready, self._on_options), (self.ctrl.frame_ready, self._on_frame),
            (self.ctrl.captured, self._on_captured), (self.ctrl.measured, self._on_measured),
            (self.ctrl.error, self._on_error), (self.ctrl.connection_lost, self._on_lost),
            (self.ctrl.reconnected, self._on_reconnected), (self.ctrl.busy_changed, self._on_busy),
        ]
        for sig, slot in self._wiring:
            sig.connect(slot)
        self.ctrl.refresh_options()
        self._goto(0)

    # ------------------------------------------------------------------ layout
    def _btn(self, text: str, primary: bool = False, slot: Any = None, checkable: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setCheckable(checkable)
        if primary:
            b.setProperty("primary", True)
        if slot is not None:
            b.clicked.connect(slot)
        return b

    def _build(self, light: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(20, 12, 20, 12)
        title = QLabel(self.tr("New gel image"))
        f = QFont(title.font())
        f.setPixelSize(20)
        title.setFont(f)
        self.step_label = QLabel()
        self.step_label.setProperty("role", "dim")
        head.addWidget(title)
        head.addStretch()
        head.addWidget(self.step_label)
        root.addLayout(head)

        mid = QHBoxLayout()
        mid.setSpacing(0)
        side = QFrame()
        side.setFixedWidth(230)
        sl = QVBoxLayout(side)
        self._names = [self.tr("Profile and description"), self.tr("Scene check"), self.tr("Focus"),
                       self.tr("Test exposure"), self.tr("Calibration"), self.tr("Image series"),
                       self.tr("Review and export")]
        self.step_items = [QLabel() for _ in self._names]
        for lab in self.step_items:
            sl.addWidget(lab)
        sl.addStretch()
        mid.addWidget(side)

        right = QVBoxLayout()
        right.setContentsMargins(16, 12, 16, 8)
        self.stack = QStackedWidget()
        for page in (self._p1(light), self._p2(light), self._p3(), self._p4(), self._p5(), self._p6(), self._p7()):
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setWidget(page)
            self.stack.addWidget(area)
        right.addWidget(self.stack, 1)
        self.status = Note("", "error")
        self.status.hide()
        right.addWidget(self.status)
        mid.addLayout(right, 1)
        root.addLayout(mid, 1)

        foot = QHBoxLayout()
        foot.setContentsMargins(20, 10, 20, 10)
        self.btn_cancel = self._btn(self.tr("Cancel"), slot=self.reject)
        self.btn_back = self._btn(self.tr("Back"), slot=lambda: self._goto(self.idx - 1))
        self.btn_next = self._btn(self.tr("Continue"), primary=True, slot=self._next)
        self.btn_next.setDefault(True)
        for b in (self.btn_cancel, self.btn_back):
            b.setAutoDefault(False)
        foot.addWidget(self.btn_cancel)
        foot.addStretch()
        foot.addWidget(self.btn_back)
        foot.addWidget(self.btn_next)
        root.addLayout(foot)

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        lay = QVBoxLayout(w)
        return w, lay

    # --- 1 profile
    def _p1(self, light: str) -> QWidget:
        w, lay = self._page()
        card = Card(self.tr("Profile and description"))
        grid = QGridLayout()
        self.dye = QComboBox()
        for p in DEFAULT_PROFILES:
            self.dye.addItem(p.name, p)
        self.profile_hint = QLabel()
        self.profile_hint.setProperty("role", "dim")
        self.uv70 = QRadioButton(self.tr("70 %"))
        self.uv100 = QRadioButton(self.tr("100 %"))
        (self.uv100 if light == "uv100" else self.uv70).setChecked(True)
        uv = QHBoxLayout()
        uv.addWidget(self.uv70)
        uv.addWidget(self.uv100)
        uv.addStretch()
        self.gel_name = QLineEdit("gel")
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText(self.tr("optional description of samples and ladder"))
        self.note.setFixedHeight(70)
        grid.addWidget(QLabel(self.tr("Dye")), 0, 0)
        grid.addWidget(self.dye, 0, 1)
        grid.addWidget(self.profile_hint, 1, 1)
        grid.addWidget(QLabel(self.tr("UV level")), 2, 0)
        grid.addLayout(uv, 2, 1)
        grid.addWidget(QLabel(self.tr("Gel name")), 3, 0)
        grid.addWidget(self.gel_name, 3, 1)
        grid.addWidget(QLabel(self.tr("Note")), 4, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.note, 4, 1)
        grid.setColumnStretch(1, 1)
        card.body.addLayout(grid)
        self.freeze_note = QLabel(self.tr("Dye and UV level are fixed after the first frame."))
        self.freeze_note.setProperty("role", "dim")
        self.freeze_note.hide()
        card.body.addWidget(self.freeze_note)
        lay.addWidget(card)
        lay.addWidget(Note(self.tr("The profile sets the colour channel and the default exposure.") + "\n"
                           + self.tr("Changing the zoom or the UV level means a new calibration — a flat "
                                     "field is valid for one arrangement only.")))
        lay.addStretch()
        self.dye.currentIndexChanged.connect(self._profile_changed)
        self._profile_changed()
        return w

    @property
    def profile(self) -> DyeProfile:
        return self._frozen[0] if self._frozen else self.dye.currentData()

    @property
    def uv_level(self) -> int:
        return self._frozen[1] if self._frozen else (100 if self.uv100.isChecked() else 70)

    def _freeze(self) -> None:
        """Profile and UV level belong to the frames: from the first one on they cannot change."""
        if self._frozen is None:
            self._frozen = (self.profile, self.uv_level)
            for w in (self.dye, self.uv70, self.uv100):
                w.setEnabled(False)
            self.freeze_note.show()

    def _profile_changed(self) -> None:
        p = self.profile
        self.profile_hint.setText(self.tr("Channel {0}  ·  {1} filter  ·  default {2:g} s, ISO {3}, f/{4:g}").format(
            p.channel, p.emission_filter, p.seconds, p.iso, p.aperture))
        self.applied = False  # exposure is derived from the profile
        if hasattr(self, "frames") and not self.light_frames:
            self.frames.setCurrentIndex(max(self.frames.findData(p.frames), 0))

    # --- 2 scene
    def _p2(self, light: str) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        self.pv_scene = PreviewView()
        self.pv_scene.set_grid(True)
        lay.addWidget(self.pv_scene, 3)
        col = QVBoxLayout()
        card = Card(self.tr("Which light is on?"))
        row = QHBoxLayout()
        self.light_group = QButtonGroup(self)
        self.light_btns: dict[str, QPushButton] = {}
        for key, label in self._lights:
            b = self._btn(label, checkable=True, slot=self._light_changed)
            b.setChecked(key == light)
            self.light_group.addButton(b)
            self.light_btns[key] = b
            row.addWidget(b)
        card.body.addLayout(row)
        hint = QLabel(self.tr("switch it by hand on the cabinet, then tell the app — the UV level decides "
                              "which flat field applies"))
        hint.setWordWrap(True)
        hint.setProperty("role", "dim")
        card.body.addWidget(hint)
        col.addWidget(card)
        card = Card(self.tr("Before you continue"))
        self.checks: dict[str, QCheckBox] = {}
        for key, text, h in (
            ("cabinet", self.tr("Cabinet is closed"), ""),
            ("eyepiece", self.tr("Viewfinder eyepiece is covered"),
             self.tr("otherwise room light leaks in during long exposures")),
            ("gel", self.tr("Gel is centred and fully in frame"), ""),
            ("zoom", self.tr("Zoom is at the marked position"),
             self.tr("a flat field is valid for one position only")),
        ):
            cb = QCheckBox(text)
            cb.toggled.connect(self._zoom_warning)
            self.checks[key] = cb
            card.body.addWidget(cb)
            if h:
                lab = QLabel("    " + h)
                lab.setProperty("role", "dim")
                card.body.addWidget(lab)
        col.addWidget(card)
        focal = self.ctrl.lens.focal_mm
        if focal:
            self.focal_label = QLabel(self.tr("current focal length: {0:g} mm").format(focal))
            self.focal_label.setProperty("role", "dim")
            col.addWidget(self.focal_label)
        self.zoom_note = Note(self.tr("Zoom is not at the marked position — you can continue, but the flat "
                                      "field must be taken again."), "error")
        col.addWidget(self.zoom_note)
        col.addStretch()
        lay.addLayout(col, 2)
        self._light_changed()
        self._zoom_warning()
        return w

    @property
    def light_declared(self) -> str:
        return next((k for k, b in self.light_btns.items() if b.isChecked()), "")

    def _light_changed(self) -> None:
        names = dict(self._lights)
        self.pv_scene.set_caption(self.tr("{0} · grid").format(names.get(self.light_declared, "")))

    def _zoom_warning(self) -> None:
        self.zoom_note.setVisible(not self.checks["zoom"].isChecked())

    # --- 3 focus
    def _p3(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        self.pv_focus = PreviewView()
        lay.addWidget(self.pv_focus, 3)
        col = QVBoxLayout()
        card = Card(self.tr("Sharpness"))
        self.sharp_val = StatValue()
        self.sharp_hint = QLabel(self.tr("variance of Laplacian in the magnifier"))
        self.sharp_hint.setProperty("role", "dim")
        self.sharp_hint.setWordWrap(True)
        card.body.addWidget(self.sharp_val)
        card.body.addWidget(self.sharp_hint)
        col.addWidget(card)
        card = Card(self.tr("Focus"))
        self.btn_af = self._btn(self.tr("Run autofocus"), primary=True, slot=self._run_af)
        card.body.addWidget(self.btn_af)
        card.body.addWidget(QLabel(self.tr("Fine steps")))
        row = QHBoxLayout()
        for glyph, name, step in (
            ("‹‹‹", self.tr("Focus nearer, large step"), FocusStep.NEAR_3),
            ("‹‹", self.tr("Focus nearer, medium step"), FocusStep.NEAR_2),
            ("‹", self.tr("Focus nearer, small step"), FocusStep.NEAR_1),
            ("›", self.tr("Focus farther, small step"), FocusStep.FAR_1),
            ("››", self.tr("Focus farther, medium step"), FocusStep.FAR_2),
            ("›››", self.tr("Focus farther, large step"), FocusStep.FAR_3),
        ):
            b = self._btn(glyph, slot=lambda _=False, s=step: self.ctrl.focus_step(s))
            theme.icon_button(b, name)
            row.addWidget(b)
        card.body.addLayout(row)
        card.body.addWidget(QLabel(self.tr("Magnifier")))
        row = QHBoxLayout()
        self.mag_group = QButtonGroup(self)
        self.mag_btns: dict[int, QPushButton] = {}
        for z in (1, 5, 10):
            b = self._btn(f"{z}×", checkable=True, slot=lambda _=False, z=z: self._set_mag(z))
            self.mag_group.addButton(b)
            self.mag_btns[z] = b
            row.addWidget(b)
        card.body.addLayout(row)
        col.addWidget(card)
        self.af_note = Note("", "error")
        self.af_note.hide()
        col.addWidget(self.af_note)
        col.addWidget(Note(self.tr("Focus under white light, then switch to UV. The shutter never "
                                   "refocuses.") + "\n" + self.tr("Refocus after every zoom change and at "
                                                                 "the start of each session.")))
        col.addStretch()
        lay.addLayout(col, 2)
        self._set_mag(10, send=False)
        return w

    def _set_mag(self, z: int, send: bool = True) -> None:
        self.mag_btns[z].setChecked(True)
        self.pv_focus.set_caption(self.tr("camera magnifier {0}×").format(z))
        if send:
            self.ctrl.set_zoom(z)

    def _run_af(self) -> None:
        self.sharp_before = self.sharp_now
        self.sharp_after = None
        self.af_note.hide()
        self.af_state = "running"
        self.btn_af.setEnabled(False)
        self.ctrl.autofocus()

    def _af_measured(self, value: float) -> None:
        self.sharp_after = value
        self.af_state = "idle"
        self.btn_af.setEnabled(True)
        before = self.sharp_before or 0.0
        self.af_note.hide()
        if value < before * AF_MIN_GAIN:
            self.af_note.setText(self.tr(
                "Autofocus did not lock — sharpness stayed at {0:.1f}. It can fail when the lens is far out of "
                "focus or the scene is dim, so the sensor finds no contrast.").format(before) + "\n" + self.tr(
                "Run autofocus again (a few focus steps first can help), check that the lens switch is on AF and "
                "that a high-contrast target is in the centre. In a dim scene switch the cabinet to white light, "
                "focus, then switch back to UV. The focus will hold."))
            self.af_note.show()
        self.sharp_hint.setText(self.tr("variance of Laplacian in the magnifier · {0:.1f} before AF").format(before))

    # --- 4 test exposure
    def _p4(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        self.exp_hint = QLabel()
        self.exp_hint.setProperty("role", "dim")
        card = Card(self.tr("Test exposure"))
        card.body.addWidget(self.exp_hint)
        grid = QHBoxLayout()
        self.st_bright = StatValue(self.tr("Brightest region"))
        self.st_range = StatValue(self.tr("Of range"))
        self.st_sat = StatValue(self.tr("Saturated"))
        for s in (self.st_bright, self.st_range, self.st_sat):
            grid.addWidget(s)
        card.body.addLayout(grid)
        self.btn_test = self._btn(self.tr("Take test frame"), slot=self._take_test)
        row.addWidget(self.btn_test)
        row.addStretch()
        card.body.addLayout(row)
        lay.addWidget(card)
        card = Card(self.tr("Exposure proposal"))
        self.proposal = QLabel("–")
        f = QFont(self.proposal.font())
        f.setPixelSize(18)
        self.proposal.setFont(f)
        card.body.addWidget(self.proposal)
        self.btn_apply = self._btn(self.tr("Apply proposal"), primary=True, slot=self._apply_proposal)
        self.btn_apply.setEnabled(False)
        row = QHBoxLayout()
        row.addWidget(self.btn_apply)
        row.addStretch()
        card.body.addLayout(row)
        lay.addWidget(card)
        self.sat_note = Note("", "error")
        self.sat_note.hide()
        lay.addWidget(self.sat_note)
        lay.addWidget(Note(self.tr("Exposure is not extended beyond 30 s — take more frames instead.")))
        lay.addStretch()
        return w

    def _apply_profile_exposure(self) -> bool:
        """Sets ISO, shutter and aperture closest to the profile, from the allowed lists only."""
        if any(p not in self.opts for p in (Prop.ISO, Prop.TV, Prop.AV)):
            return False
        p = self.profile
        iso = pick_iso(self.opts[Prop.ISO][0], p.iso)
        tv = tv_code_at_most(self.opts[Prop.TV][0], p.seconds)
        av = min(self.opts[Prop.AV][0], key=lambda c: abs(av_fnumber(c) - p.aperture), default=None)
        if iso is None or tv is None or av is None:
            return False
        for prop, code in ((Prop.ISO, iso), (Prop.TV, tv), (Prop.AV, av)):
            self.codes[prop] = code
            self.ctrl.set_value(prop, code)
        self.applied = True
        return True

    def _exposure_text(self) -> str:
        if not self.codes:
            return "–"
        return f"{_secs(self.codes[Prop.TV])} · {iso_label(self.codes[Prop.ISO])} · {av_label(self.codes[Prop.AV])}"

    def _refresh_exposure(self) -> None:
        self.exp_hint.setText(self.tr("{0} · target 70–80 % of range without saturation").format(self._exposure_text()))
        self.btn_test.setEnabled(self.applied and self.folder is not None)

    def _take_test(self) -> None:
        assert self.folder is not None
        self._test_dir = self.folder / "raw" / "test"
        self._freeze()
        self.btn_test.setEnabled(False)
        self.ctrl.capture(self._test_dir)

    def _show_measurement(self, m: ExposureMeasurement) -> None:
        self.st_bright.set_value(f"{m.brightest_adu:,.0f} ADU")
        self.st_range.set_value(f"{m.fraction * 100:.0f} %")
        saturated = m.saturated_fraction > SATURATION_LIMIT
        self.st_sat.set_value(f"{m.saturated_fraction * 100:.2f} %", theme.BAD if saturated else theme.OK)
        cur = tv_seconds(self.codes[Prop.TV]) or self.profile.seconds
        want = propose_seconds(cur, m.fraction)
        self.proposal_code = tv_code_at_most(self.opts[Prop.TV][0], want)
        new = tv_seconds(self.proposal_code) if self.proposal_code is not None else None
        self.proposal.setText(f"{cur:g} s  →  {new:g} s" if new else "–")
        self.btn_apply.setEnabled(self.proposal_code is not None)
        if saturated:
            self.sat_note.setText(self.tr(
                "The brightest region is saturated — {0:.2f} % of pixels at {1:,.0f} ADU above black, the "
                "white level at this ISO. It cannot be quantified.").format(
                    m.saturated_fraction * 100, m.brightest_adu) + "\n" + self.tr(
                "Shorten the exposure to {0:g} s, or continue if only the faint bands matter.").format(new or cur))
        self.sat_note.setVisible(saturated)
        self.btn_test.setEnabled(True)

    def _apply_proposal(self) -> None:
        if self.proposal_code is None:
            return
        self.codes[Prop.TV] = self.proposal_code
        self.ctrl.set_value(Prop.TV, self.proposal_code)
        self.btn_apply.setEnabled(False)
        self._refresh_exposure()

    # --- 5 calibration
    def _p5(self) -> QWidget:
        w, lay = self._page()
        card = Card(self.tr("Dark frames"))
        self.darks_val = QLabel()
        f = QFont(self.darks_val.font())
        f.setPixelSize(16)
        self.darks_val.setFont(f)
        card.body.addWidget(self.darks_val)
        hint = QLabel(self.tr("Taken automatically right after the series, with the lights off.") + "\n"
                      + self.tr("Same exposure time and ISO as the light frames — otherwise warm pixels remain."))
        hint.setProperty("role", "dim")
        hint.setWordWrap(True)
        card.body.addWidget(hint)
        row = QHBoxLayout()
        auto = QRadioButton(self.tr("Automatic"))
        auto.setChecked(True)
        stored = QRadioButton(self.tr("Use stored"))
        stored.setEnabled(False)
        stored.setToolTip(self.tr("No dark library yet in the prototype"))
        row.addWidget(auto)
        row.addWidget(stored)
        row.addStretch()
        card.body.addLayout(row)
        lay.addWidget(card)
        card = Card(self.tr("Flat field"))
        card.body.addWidget(QLabel(self.tr("No flat-field library exists yet in the prototype.")))
        hint = QLabel(self.tr("The flat correction will be skipped and recorded as skipped in metadata.json."))
        hint.setProperty("role", "dim")
        hint.setWordWrap(True)
        card.body.addWidget(hint)
        lay.addWidget(card)
        lay.addWidget(Note(self.tr("Darks are taken right after the series, not from a library: hot pixels "
                                   "depend on sensor temperature, and after a series the sensor is warmer.")))
        lay.addStretch()
        return w

    # --- 6 series
    def _p6(self) -> QWidget:
        w, lay = self._page()
        card = Card(self.tr("Series"))
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Frame count")))
        self.frames = QComboBox()
        for n in (4, 8, 16, 32):
            self.frames.addItem(str(n), n)
        self.frames.setCurrentIndex(max(self.frames.findData(self.profile.frames), 0))
        self.frames.currentIndexChanged.connect(lambda _: self._rebuild_thumbs(self.frames.currentData()))
        row.addWidget(self.frames)
        self.btn_series = self._btn(self.tr("Start series"), primary=True, slot=self._start_series)
        row.addWidget(self.btn_series)
        row.addStretch()
        card.body.addLayout(row)
        hint = QLabel(self.tr("Background noise falls with √N — 8 frames means roughly 2.8× better "
                              "signal-to-noise."))
        hint.setProperty("role", "dim")
        card.body.addWidget(hint)
        lay.addWidget(card)

        card = Card(self.tr("Progress"))
        self.series_count = QLabel("0 / 0")
        f = QFont(self.series_count.font())
        f.setPixelSize(18)
        self.series_count.setFont(f)
        self.series_bar = QProgressBar()
        self.series_bar.setTextVisible(False)
        self.series_bar.setFixedHeight(8)
        self.st_last_sat = StatValue(self.tr("Saturated (last frame)"))
        card.body.addWidget(self.series_count)
        card.body.addWidget(self.series_bar)
        card.body.addWidget(self.st_last_sat)
        lay.addWidget(card)
        self.thumb_row = QHBoxLayout()
        self.thumb_row.addStretch()
        self.thumbs: list[QLabel] = []
        lay.addLayout(self.thumb_row)
        self._rebuild_thumbs(self.frames.currentData())

        self.dark_card = Card(self.tr("Turn off all light"))
        self.dark_checks = [QCheckBox(t) for t in (self.tr("UV lamp and white light off"),
                                                   self.tr("Cabinet door closed"), self.tr("Eyepiece covered"))]
        for cb in self.dark_checks:
            cb.toggled.connect(self._update_nav)
            self.dark_card.body.addWidget(cb)
        self.btn_darks = self._btn(self.tr("Take dark frames"), primary=True, slot=self._start_darks)
        self.dark_count = QLabel("0 / 0")
        self.dark_bar = QProgressBar()
        self.dark_bar.setTextVisible(False)
        self.dark_bar.setFixedHeight(8)
        row = QHBoxLayout()
        row.addWidget(self.btn_darks)
        row.addWidget(self.dark_count)
        row.addStretch()
        self.dark_card.body.addLayout(row)
        self.dark_card.body.addWidget(self.dark_bar)
        self.dark_card.hide()
        lay.addWidget(self.dark_card)
        lay.addWidget(Note(self.tr("Live view stays off during the series so the sensor does not warm up.")
                           + "\n" + self.tr("Darks are taken right after the last exposure, with the camera in "
                                            "the same state.")))
        lay.addStretch()
        return w

    def _rebuild_thumbs(self, n: int, filled: int = 0) -> None:
        for t in self.thumbs:
            self.thumb_row.removeWidget(t)
            t.deleteLater()
            t.hide()
        self.thumbs = []
        for i in range(n):
            t = QLabel(str(i + 1))
            t.setFixedSize(38, 26)
            t.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.thumb_row.insertWidget(i, t)
            self.thumbs.append(t)
        self._paint_thumbs(filled)

    def _paint_thumbs(self, filled: int) -> None:
        for i, t in enumerate(self.thumbs):
            if i < filled:
                t.setStyleSheet(f"background: {theme.DARK}; color: #FFFFFF; border: 1px solid {theme.OK};")
            else:
                t.setStyleSheet(f"background: {theme.PANEL}; border: 1px solid {theme.LINE};")

    def _start_series(self) -> None:
        assert self.folder is not None
        self.light_frames = []
        self.series_bar.setMaximum(self.frames.currentData())
        self._start_batch("light", self.folder / "raw", self.frames.currentData())

    def _start_darks(self) -> None:
        assert self.folder is not None
        self.dark_frames = []
        self.dark_bar.setMaximum(len(self.light_frames))
        self._start_batch("dark", self.folder / "calib", len(self.light_frames))

    # --- 7 review
    def _p7(self) -> QWidget:
        w, lay = self._page()
        card = Card(self.tr("Review and export"))
        self.summary = QLabel()
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.body.addWidget(self.summary)
        row = QHBoxLayout()
        self.btn_process = self._btn(self.tr("Process"), primary=True, slot=self._process)
        row.addWidget(self.btn_process)
        row.addWidget(self._btn(self.tr("Open folder"), slot=self._open_folder))
        row.addStretch()
        card.body.addLayout(row)
        self.proc_label = QLabel()
        self.proc_label.setWordWrap(True)
        card.body.addWidget(self.proc_label)
        lay.addWidget(card)
        self.pv_result = PreviewView()
        self.pv_result.setMinimumHeight(260)
        self.pv_result.hide()
        lay.addWidget(self.pv_result, 1)
        self.proc_stats = QLabel()
        self.proc_stats.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.proc_stats)
        lay.addWidget(Note(self.tr("Process subtracts the dark frames, stacks the light frames and saves "
                                   "result.tif (linear, 16-bit) and preview.png in the gel folder. The RAW "
                                   "frames are never modified; the flat field is skipped. Without Process, "
                                   "Finish only saves the frames and metadata for later processing.")))
        lay.addStretch()
        return w

    def _refresh_summary(self) -> None:
        p = self.profile
        self.summary.setText("\n".join([
            f"{self.folder}",
            self.tr("raw/: {0} light frames ({1} test)").format(len(self.light_frames), len(self.test_frames)),
            self.tr("calib/: {0} dark frames").format(len(self.dark_frames)),
            self.tr("Profile: {0} · channel {1}").format(p.name, p.channel),
            self.tr("Exposure: {0}").format(self._exposure_text()),
            self.tr("Flat field: skipped (no library in prototype)"),
        ]))

    def _process(self) -> None:
        assert self.folder is not None
        try:
            write_metadata(self.folder, self._metadata())
        except OSError as exc:
            return self._show_error(str(exc))
        self._metadata_written = True
        self.status.hide()
        self._processing = True
        self.btn_process.setEnabled(False)
        self.proc_label.setText(self.tr("Processing…"))
        self._update_nav()
        folder = self.folder
        self._cancel = cancel = threading.Event()

        def work() -> None:
            try:
                out: object = process_gel_folder(
                    folder, lambda msg, f: self._emit(self._proc_progress, msg), cancel=cancel)
            except Exception as exc:  # noqa: BLE001 - reported in the dialog
                out = exc
            self._proc_out = out
            self._emit(self._proc_done, out)

        self._future = self._executor.submit(work)

    @staticmethod
    def _emit(sig: Any, value: object) -> None:
        try:
            sig.emit(value)
        except RuntimeError:  # dialog already destroyed
            pass

    def _on_proc_progress(self, msg: str) -> None:
        if not self._closed:
            self.proc_label.setText(self.tr("Processing: {0}…").format(msg))

    def _on_proc_done(self, out: Any) -> None:
        if self._closed:
            return
        self._processing = False
        if isinstance(out, ProcessingCancelled):
            self.proc_label.setText(self.tr("Cancelled"))
            self.btn_process.setEnabled(True)
        elif isinstance(out, BaseException):
            self.proc_label.setText("")
            self.btn_process.setEnabled(not isinstance(out, FileExistsError))
            self._show_error(self.tr("Processing failed: {0}").format(out))
        else:
            from PIL import Image  # lazy

            self.processed = True
            text = self.tr("Processed: {0}, {1}").format(out.result.name, out.preview.name)
            if self._cancel.is_set():  # cancelled too late: the run had reached publishing and completed
                text = self.tr("Processing had already finished; the results were kept.") + " " + text
            self.proc_label.setText(text)
            self.pv_result.set_frame(np.asarray(Image.open(out.preview).convert("RGB")))
            self.pv_result.show()
            s = out.stats
            self.proc_stats.setText("\n".join([
                self.tr("Background noise: {0:.2f} → {1:.2f} ADU (ratio {2:.2f})").format(
                    s["background_noise_single"], s["background_noise_result"], s["background_noise_ratio"]),
                self.tr("Saturated pixels: {0:.3f} %").format(100 * s["saturated_fraction"]),
                self.tr("Frames used: {0} · max shift {1:.2f} px").format(s["frames_used"], s["shift_max_px"]),
            ]))
        self._update_nav()

    def _open_folder(self) -> None:
        if self.folder is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder)))

    # ------------------------------------------------------------------ navigation
    def _next(self) -> None:
        if self.idx == 0 and self.folder is None:
            try:
                self.folder = create_gel_folder(self.out_root, self.gel_name.text().strip(), date.today())
            except OSError as exc:
                return self._show_error(str(exc))
        if self.idx == STEP_COUNT - 1:
            return self._finish()
        self._goto(self.idx + 1)

    def _goto(self, i: int) -> None:
        old, self.idx = self.idx, max(0, min(i, STEP_COUNT - 1))
        i = self.idx
        self.status.hide()
        if old == 2 and i != 2:
            self.ctrl.set_zoom(1)
        live = i in (1, 2)
        if live and not self.ctrl.live:
            self.ctrl.set_live_view(True)
        elif i >= 3 and self.ctrl.live:
            self.ctrl.set_live_view(False)
        if i == 2 and old != 2:
            self._set_mag(10)
        self._timer.start() if live else self._timer.stop()
        self.stack.setCurrentIndex(i)
        if i == 0:
            fixed = self.folder is not None
            self.gel_name.setEnabled(not fixed)
        elif i == 3:
            if not self.applied and not self._apply_profile_exposure():
                self._show_error(self.tr("Camera options are not available yet."))
            self._refresh_exposure()
        elif i == 4:
            n = self.frames.currentData()
            self.darks_val.setText(self.tr("{0} × {1} · {2}").format(
                n, _secs(self.codes[Prop.TV]) if self.codes else "–",
                iso_label(self.codes[Prop.ISO]) if self.codes else "–"))
        elif i == 6:
            self._refresh_summary()
        self._refresh_chrome()

    def _refresh_chrome(self) -> None:
        self.step_label.setText(self.tr("Step {0} of {1}").format(self.idx + 1, STEP_COUNT))
        for n, lab in enumerate(self.step_items):
            if n == self.idx:
                lab.setText(f"{n + 1}   {self._names[n]}")
                lab.setStyleSheet(f"background: {theme.SELECTED}; color: {theme.ACC}; font-weight: bold; "
                                  "padding: 6px; border-radius: 4px;")
            else:
                done = n < self.idx
                lab.setText(f"✓   {self._names[n]}" if done else f"{n + 1}   {self._names[n]}")
                lab.setStyleSheet(f"color: {theme.OK if done else theme.DIM}; padding: 6px;")
        self.btn_next.setText(self.tr("Finish") if self.idx == STEP_COUNT - 1 else self.tr("Continue"))
        self._update_nav()

    def _update_nav(self) -> None:
        busy = self._batch is not None or self._processing
        self.btn_back.setEnabled(self.idx > 0 and not busy)
        ok = not busy and not (self.idx == 5 and not (self.series_done and self.darks_done))
        self.btn_next.setEnabled(ok)
        if self.idx == 5:
            self.btn_series.setEnabled(not busy and not self.series_done and self.folder is not None)
            self.frames.setEnabled(not busy and not self.series_done)
            self.dark_card.setVisible(self.series_done)
            self.btn_darks.setEnabled(not busy and not self.darks_done and all(c.isChecked() for c in self.dark_checks))
            for c in self.dark_checks:
                c.setEnabled(not busy and not self.darks_done)

    def _show_error(self, text: str) -> None:
        self.status.setText(text)
        self.status.show()

    # ------------------------------------------------------------------ camera signals
    def _on_options(self, opts: dict) -> None:
        self.opts = opts
        if self.idx == 3 and not self.applied and self._apply_profile_exposure():
            self._refresh_exposure()

    def _on_busy(self, on: bool) -> None:
        self._busy = max(0, self._busy + (1 if on else -1))
        if self.af_state == "running" and self._busy == 0:
            self.af_state = "settling"  # next frame is the first one after AF

    def _on_frame(self, frame: Any) -> None:
        if self.idx == 1:
            self.pv_scene.set_frame(frame)
        elif self.idx == 2:
            self.pv_focus.set_frame(frame)
            self._frame_n += 1
            if self.af_state == "settling" or self._frame_n % 3 == 0:
                self.sharp_now = sharpness_rgb(frame)
                self.sharp_val.set_value(f"{self.sharp_now:.1f}")
                if self.af_state == "settling":
                    self._af_measured(self.sharp_now)

    def _on_captured(self, path: Any) -> None:
        path = Path(path)
        if self._test_dir is not None and path.parent == self._test_dir:
            self.test_frames.append(path)
            self.ctrl.measure_file(path, self.profile.channel)
            return
        b = self._batch
        if b is None or path.parent != b["dest"]:
            return
        b["got"].append(path)  # also while paused: the file is on disk
        if b["kind"] == "light":
            self.ctrl.measure_file(path, self.profile.channel)
        self._progress()
        if b["paused"]:
            k = len(b["got"])  # in-flight capture finished after the interruption
            if self._box_btns is not None:
                resume, use = self._box_btns
                resume.setText(self.tr("Resume from frame {0}").format(k + 1))
                use.setText(self.tr("Use the {0} frames").format(k))
                use.setVisible(True)
            return
        if len(b["got"]) >= b["total"]:
            self._batch_done()
        else:
            self.ctrl.capture(b["dest"])

    def _on_measured(self, path: Any, m: ExposureMeasurement) -> None:
        path = Path(path)
        if path in self.test_frames:
            self._show_measurement(m)
        elif path in self.light_frames or (self._batch and path in self._batch["got"]):
            sat = m.saturated_fraction
            self.st_last_sat.set_value(f"{sat * 100:.2f} %", theme.BAD if sat > SATURATION_LIMIT else theme.OK)

    def _on_error(self, msg: str) -> None:
        if self._batch is not None and not self._batch["paused"]:
            self._interrupt(lost=False)
        else:
            self._show_error(msg)
            if self.idx == 3:
                self.btn_test.setEnabled(self.applied)

    def _on_lost(self) -> None:
        if self._batch is not None:
            self._interrupt(lost=True)
        else:
            self._show_error(self.tr("Connection to the camera lost."))

    def _on_reconnected(self, _info: Any) -> None:
        b = self._batch
        if b is not None and b["resume"]:
            b["resume"] = False
            self._reconnect_timer.stop()
            self._continue_batch()

    # ------------------------------------------------------------------ frame batches
    def _start_batch(self, kind: str, dest: Path, total: int) -> None:
        self._batch = {"kind": kind, "dest": dest, "total": total, "got": [], "paused": False, "resume": False}
        self._freeze()
        self.status.hide()
        self._progress()
        self._update_nav()
        self.ctrl.capture(dest)

    def _progress(self) -> None:
        b = self._batch
        if b is None:
            return
        k, n = len(b["got"]), b["total"]
        if b["kind"] == "light":
            self.series_count.setText(f"{k} / {n}")
            self.series_bar.setMaximum(n)
            self.series_bar.setValue(k)
            if len(self.thumbs) != n:
                self._rebuild_thumbs(n, k)
            self._paint_thumbs(k)
        else:
            self.dark_count.setText(f"{k} / {n}")
            self.dark_bar.setMaximum(n)
            self.dark_bar.setValue(k)

    def _batch_done(self) -> None:
        b, self._batch = self._batch, None
        assert b is not None
        if b["kind"] == "light":
            self.light_frames, self.series_done = b["got"], True
            self._progress_final(b)
        else:
            self.dark_frames, self.darks_done = b["got"], True
            self.dark_count.setText(f"{len(b['got'])} / {len(b['got'])}")
            self.dark_bar.setMaximum(len(b["got"]) or 1)
            self.dark_bar.setValue(len(b["got"]))
        self._update_nav()

    def _progress_final(self, b: dict[str, Any]) -> None:
        k = len(b["got"])
        self.series_count.setText(f"{k} / {k}")
        self.series_bar.setMaximum(max(k, 1))
        self.series_bar.setValue(k)
        if len(self.thumbs) != k:
            self._rebuild_thumbs(k, k)

    def _interrupt(self, lost: bool) -> None:
        b = self._batch
        assert b is not None
        b["paused"] = True
        k, n = len(b["got"]), b["total"]
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        light = b["kind"] == "light"
        title = (self.tr("Series interrupted after {0} of {1} frames") if light
                 else self.tr("Dark frames interrupted after {0} of {1} frames")).format(k, n)
        box.setWindowTitle(title)
        box.setText(title)
        box.setInformativeText(
            (self.tr("The camera disconnected.") if lost else self.tr("The camera reported an error."))
            + " " + self.tr("{0} frames are downloaded and kept; exposure and focus are unchanged.").format(k))
        resume = box.addButton(self.tr("Resume from frame {0}").format(k + 1), QMessageBox.ButtonRole.AcceptRole)
        again = box.addButton(self.tr("Start over"), QMessageBox.ButtonRole.DestructiveRole)
        use = box.addButton(self.tr("Use the {0} frames").format(k), QMessageBox.ButtonRole.ActionRole)
        use.setVisible(bool(k))
        self._box_btns = (resume, use)
        box.setDefaultButton(resume)
        box.buttonClicked.connect(lambda btn: self._interrupt_choice(btn, resume, again, use, lost))
        self._box = box
        box.open()

    def _interrupt_choice(self, btn: QAbstractButton, resume: QAbstractButton, again: QAbstractButton,
                          use: QAbstractButton | None, lost: bool) -> None:
        b = self._batch
        if b is None:
            return
        self._box_btns = None
        if btn is use:
            b["total"] = len(b["got"])
            return self._batch_done()
        if btn is again and b["got"]:
            n = 1
            while (d := b["dest"] / f"discarded_{n}").exists():
                n += 1
            d.mkdir()
            for p in b["got"]:  # moved aside, never deleted or modified
                self.discarded.append(p.rename(d / p.name))
            b["got"] = []
            self._progress()
        b["paused"] = False
        if lost and self.ctrl.lost:
            b["resume"] = True
            self.ctrl.reconnect()
            self._reconnect_timer.start()
        else:
            self._continue_batch()

    def _continue_batch(self) -> None:
        b = self._batch
        if b is None:
            return
        if len(b["got"]) >= b["total"]:  # the in-flight capture completed the batch
            return self._batch_done()
        for prop, code in self.codes.items():  # restore exposure after a reconnect
            self.ctrl.set_value(prop, code)
        self.ctrl.capture(b["dest"])

    # ------------------------------------------------------------------ finish / close
    def _metadata(self) -> dict[str, Any]:
        c = self.codes
        exposure = {
            "iso": {"code": c[Prop.ISO], "value": iso_value(c[Prop.ISO]), "label": iso_label(c[Prop.ISO])},
            "shutter": {"code": c[Prop.TV], "seconds": tv_seconds(c[Prop.TV]), "label": tv_label(c[Prop.TV])},
            "aperture": {"code": c[Prop.AV], "f_number": av_fnumber(c[Prop.AV]), "label": av_label(c[Prop.AV])},
        } if c else {}
        return {
            "profile": asdict(self.profile),
            "uv_level": self.uv_level,
            "light_declared": self.light_declared,
            "lens": {"name": self.ctrl.lens.name, "focal_length_mm": self.ctrl.lens.focal_mm},  # from status_ready
            "gel_name": self.gel_name.text().strip() or "gel",
            "note": self.note.toPlainText(),
            "exposure": exposure,
            "light_frames": self.light_frames,
            "dark_frames": self.dark_frames,
            "test_frames": self.test_frames,
            "discarded_frames": self.discarded,
            "flat": "skipped (no library in prototype)",
            "checklist": {
                **{k: cb.isChecked() for k, cb in self.checks.items()},
                "lights_off_and_cabinet_closed_and_eyepiece_covered_for_darks": all(
                    cb.isChecked() for cb in self.dark_checks),
            },
            "focus": {"sharpness_before_af": self.sharp_before, "sharpness_after_af": self.sharp_after},
            "processing": [],
            "status": STATUS,
        }

    def _finish(self) -> None:
        assert self.folder is not None
        if not self.processed:
            try:
                write_metadata(self.folder, self._metadata())
            except OSError as exc:
                return self._show_error(str(exc))
        self.accept()

    def _frames_taken(self) -> bool:
        return bool(self.test_frames or self.light_frames or self.dark_frames or self._batch)

    def reject(self) -> None:
        if self._frames_taken() and not self._closed and not self.processed:
            if self._metadata_written:
                msg = self.tr("Frames and metadata.json stay in the gel folder (status: captured; processing "
                              "pending). Running processing will be stopped. Cancel anyway?")
            else:
                msg = self.tr("Frames already taken stay in the gel folder, without metadata. Cancel anyway?")
            ask = QMessageBox.question(self, self.tr("Cancel"), msg)
            if ask != QMessageBox.StandardButton.Yes:
                return
        super().reject()

    def _cancel_processing(self) -> None:
        """Stops a running pipeline and waits until it has finished, so nothing is written after the dialog closed."""
        fut = self._future
        if fut is None:
            return
        handled_before = self.processed  # _on_proc_done may run inside the wait loop below
        if not fut.done():
            self._cancel.set()
            self.proc_label.setText(self.tr("Cancelling…"))
            for b in (self.btn_next, self.btn_back, self.btn_cancel, self.btn_process):
                b.setEnabled(False)
            while True:
                try:
                    fut.result(timeout=0.05)
                    break
                except FutureTimeout:
                    QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
                except BaseException:  # noqa: BLE001 - the worker reports its own errors
                    return
        out = self._proc_out
        if not handled_before and out is not None and not isinstance(out, BaseException):  # passed the publishing boundary: completed
            self.processed = True
            QMessageBox.information(self, self.tr("Cancel"),
                                    self.tr("Processing had already finished; the results were kept."))

    def done(self, result: int) -> None:
        if not self._closed:
            self._cancel_processing()
            self._closed = True
            self._timer.stop()
            self._reconnect_timer.stop()
            self._executor.shutdown(wait=False, cancel_futures=True)
            for sig, slot in self._wiring:
                try:
                    sig.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
            if self.idx == 2:
                self.ctrl.set_zoom(1)
            if self._live_at_open:  # FIFO on the camera thread: runs after any queued stop
                self.ctrl.set_live_view(True)
        super().done(result)
