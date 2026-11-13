"""Main window: connection, live view with zoom, focus, exposure and single-frame capture.

Everything shown here from the live view stream is an estimate (8-bit EVF JPEG); only the
numbers measured on a captured RAW are authoritative. Display adjustments affect the preview only.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
from platformdirs import user_documents_dir
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..camera import CameraInfo, FocusStep, Prop, values
from ..processing.focus import sharpness_rgb
from . import theme
from .controller import CameraController
from .preview import apply_display, auto_levels, clipped_mask, histogram, overlay_clipping
from .widgets import Card, HistogramView, Note, PreviewView, StatValue

_LABELS = {Prop.ISO: values.iso_label, Prop.TV: values.tv_label, Prop.AV: values.av_label}
_LIGHTS = (("white", "White light"), ("uv70", "UV 70 %"), ("uv100", "UV 100 %"))
_CHANNELS = "RGB"
_STATS_EVERY = 3  # histogram and sharpness only on every 3rd frame (GELCAM_PLAN.md, ch. 8)
_CHIP = (f"background: {theme.PANEL}; border: 1px solid {theme.LINE}; border-radius: 12px;"
         " padding: 3px 10px;")


class LogDialog(QDialog):
    """Read-only list of "time  level  message" lines with a level filter."""

    def __init__(self, entries: list[tuple[str, str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Log"))
        self.resize(640, 400)
        self._entries = entries
        self._filter = ""
        self.list = QListWidget()
        row = QHBoxLayout()
        group = QButtonGroup(self)
        for label, level in ((self.tr("All"), ""), (self.tr("Warnings"), "WARNING"), (self.tr("Errors"), "ERROR")):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(level == "")
            b.clicked.connect(lambda _=False, lv=level: self._set_filter(lv))
            group.addButton(b)
            row.addWidget(b)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(self.list, 1)
        self.refresh()

    def _set_filter(self, level: str) -> None:
        self._filter = level
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        for t, level, text in self._entries:
            if not self._filter or level == self._filter:
                self.list.addItem(f"{t}  {level:<7}  {text}")
        self.list.scrollToBottom()


class MainWindow(QMainWindow):
    def __init__(self, controller: CameraController) -> None:
        super().__init__()
        self.setWindowTitle("GelCam")
        self.resize(1280, 800)
        self.ctrl = controller
        self.out_dir = Path(user_documents_dir()) / "GelCam" / "images"
        self.light = "white"
        self._options_updating = False
        self._frame: np.ndarray | None = None
        self._frame_n = 0
        self._frame_times: deque[float] = deque(maxlen=20)
        self._last_frame_t = 0.0
        self._connected = False
        self._auto_retry = True
        self._connecting = False
        self._attempts = 0
        self._awaiting_capture = False
        self._last_capture: Path | None = None
        self._log_entries: list[tuple[str, str, str]] = []
        self._log_dialog: LogDialog | None = None

        top = self._build_top_bar()
        left = self._build_left()
        right = self._build_right()
        body = QHBoxLayout()
        body.addLayout(left, 1)
        body.addWidget(right)
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(top)
        root.addLayout(body, 1)
        self.setCentralWidget(central)
        self._build_status_bar()
        self._set_tab_order()

        c = self.ctrl
        c.connected.connect(self._on_connected)
        c.disconnected.connect(self._on_disconnected)
        c.connect_failed.connect(self._on_connect_failed)
        c.options_ready.connect(self._on_options)
        c.status_ready.connect(self._on_status)
        c.frame_ready.connect(self._on_frame)
        c.captured.connect(self._on_captured)
        c.measured.connect(self._on_measured)
        c.message.connect(self._on_message)
        c.error.connect(lambda m: self._log("ERROR", m))
        c.connection_lost.connect(self._on_lost)
        c.reconnected.connect(self._on_reconnected)

        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.ctrl.request_frame)
        self.frame_timer.start(100)
        self.retry_timer = QTimer(self)  # LV3: auto-retry every 5 s
        self.retry_timer.timeout.connect(self._retry)
        self.lost_timer = QTimer(self)  # LV4: tick every second, reconnect every 2nd tick
        self.lost_timer.timeout.connect(self._lost_tick)

        self._set_enabled(False)
        self._show_nocam(self.tr("Looking for the camera…"))
        QTimer.singleShot(0, self._connect)

    # --- construction ---
    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet(f"QFrame#topbar {{ background: {theme.PANEL}; border-bottom: 1px solid {theme.LINE}; }}")
        bar.setObjectName("topbar")
        row = QHBoxLayout(bar)
        title = QLabel("GelCam")
        f = QFont(title.font())
        f.setPixelSize(20)
        title.setFont(f)
        self.chip_camera = QLabel(self.tr("No camera"))
        self.chip_quality = QLabel("–")
        for chip in (self.chip_camera, self.chip_quality):
            chip.setStyleSheet(_CHIP)
            chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.light_combo = QComboBox()
        self.light_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        for key, label in _LIGHTS:
            self.light_combo.addItem(self.tr("Light: {0}").format(self.tr(label)), key)
        self.light_combo.currentIndexChanged.connect(self._on_light)
        self.btn_new = QPushButton(self.tr("New gel image…"))
        self.btn_new.setProperty("primary", True)
        self.btn_new.clicked.connect(self._open_wizard)
        row.addWidget(title)
        row.addWidget(self.chip_camera)
        row.addWidget(self.chip_quality)
        row.addWidget(self.light_combo)
        row.addStretch(1)
        row.addWidget(self.btn_new)
        return bar

    def _build_left(self) -> QVBoxLayout:
        # toolbar
        tools = QHBoxLayout()
        tools.addWidget(QLabel(self.tr("View")))
        self.btn_grid = QPushButton(self.tr("Grid"))
        self.btn_clip = QPushButton(self.tr("Clipping"))
        for b in (self.btn_grid, self.btn_clip):
            b.setCheckable(True)
            tools.addWidget(b)
        self.btn_grid.toggled.connect(lambda on: self.view.set_grid(on))
        self.btn_clip.toggled.connect(lambda _: self._render())
        tools.addWidget(QLabel(self.tr("Zoom")))
        self.zoom_group = QButtonGroup(self)
        self.zoom_btns: dict[int, QPushButton] = {}
        for z in (1, 5, 10):
            b = theme.icon_button(QPushButton(f"{z}×"), self.tr("Zoom {0}×").format(z))
            b.setCheckable(True)
            b.setChecked(z == 1)
            self.zoom_group.addButton(b, z)
            self.zoom_btns[z] = b
            tools.addWidget(b)
        self.zoom_group.idClicked.connect(self._on_zoom)
        tools.addStretch(1)

        # preview area: live view (with the "connection lost" card on top) or the "no camera" state
        self.view = PreviewView()
        self.view.set_message(self.tr("Camera is not connected"))
        self.lost_card = self._build_lost_card()
        live_page = QWidget()
        grid = QGridLayout(live_page)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(self.view, 0, 0)
        grid.addWidget(self.lost_card, 0, 0, Qt.AlignmentFlag.AlignCenter)
        self.nocam_page = self._build_nocam_page()
        self.stack = QStackedWidget()
        self.stack.addWidget(live_page)
        self.stack.addWidget(self.nocam_page)

        left = QVBoxLayout()
        left.addLayout(tools)
        left.addWidget(self.stack, 1)
        left.addWidget(self._build_display_card())
        return left

    def _build_lost_card(self) -> QFrame:
        card = Card()
        card.setFixedWidth(420)
        title = QLabel(self.tr("● Connection lost — reconnecting"))
        title.setStyleSheet(f"font-weight: bold; color: {theme.WARN};")
        self.lost_last = QLabel()
        self.lost_attempt = QLabel()
        for lab in (self.lost_last, self.lost_attempt):
            lab.setProperty("role", "dim")
        restore = QLabel(self.tr("ISO, shutter and aperture will be restored automatically."))
        restore.setWordWrap(True)
        self.btn_reconnect = QPushButton(self.tr("Reconnect now"))
        self.btn_reconnect.setProperty("primary", True)
        self.btn_cancel = QPushButton(self.tr("Cancel"))
        self.btn_reconnect.clicked.connect(self._reconnect_now)
        self.btn_cancel.clicked.connect(self._cancel_reconnect)
        row = QHBoxLayout()
        row.addWidget(self.btn_reconnect)
        row.addWidget(self.btn_cancel)
        row.addStretch(1)
        for w in (title, self.lost_last, self.lost_attempt, restore):
            card.body.addWidget(w)
        card.body.addLayout(row)
        card.hide()
        return card

    def _build_nocam_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        card = Card()
        card.setFixedWidth(480)
        title = QLabel(self.tr("No camera found"))
        f = QFont(title.font())
        f.setPixelSize(20)
        title.setFont(f)
        title.setStyleSheet(f"color: {theme.BAD};")
        self.nocam_msg = QLabel()
        self.nocam_msg.setWordWrap(True)
        card.body.addWidget(title)
        card.body.addWidget(self.nocam_msg)
        for text in (self.tr("EOS Utility or another tethering app is not running"),
                     self.tr("USB cable connected directly, not through a hub"),
                     self.tr("Camera switched on, mode M, AC adapter plugged in")):
            lab = QLabel("• " + text)
            lab.setWordWrap(True)
            card.body.addWidget(lab)
        self.btn_retry = QPushButton(self.tr("Try again"))
        self.btn_retry.setProperty("primary", True)
        self.btn_retry.clicked.connect(self._connect)
        self.btn_open_log = QPushButton(self.tr("Open log"))
        self.btn_open_log.clicked.connect(self._open_log)
        row = QHBoxLayout()
        row.addWidget(self.btn_retry)
        row.addWidget(self.btn_open_log)
        row.addStretch(1)
        card.body.addLayout(row)
        outer.addStretch(1)
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)
        return page

    def _build_display_card(self) -> Card:
        card = Card(self.tr("Display — preview only, result.tif and the RAW stay linear"))
        self.hist = HistogramView()
        self.sl_black = self._slider(0, 255, 0)
        self.sl_white = self._slider(0, 255, 255)
        self.sl_gamma = self._slider(3, 30, 10)
        self.lbl_black, self.lbl_white, self.lbl_gamma = QLabel("0"), QLabel("255"), QLabel("1.00")
        self.btn_auto = QPushButton(self.tr("Auto stretch"))
        self.btn_reset = QPushButton(self.tr("Reset"))
        self.btn_invert = QPushButton(self.tr("Invert"))
        self.btn_invert.setCheckable(True)
        self.btn_auto.clicked.connect(self._auto_stretch)
        self.btn_reset.clicked.connect(self._reset_display)
        self.btn_invert.toggled.connect(lambda _: self._render(stats=True))
        self.chan_group = QButtonGroup(self)
        self.chan_btns: list[QPushButton] = []
        chan_row = QHBoxLayout()
        chan_row.addWidget(QLabel(self.tr("Channel")))
        for i, letter in enumerate(_CHANNELS):
            b = QPushButton(letter)
            b.setCheckable(True)
            b.setChecked(i == 0)
            self.chan_group.addButton(b, i)
            self.chan_btns.append(b)
            chan_row.addWidget(b)
        chan_row.addStretch(1)
        self.chan_group.idClicked.connect(lambda _: self._render(stats=True))
        for sl in (self.sl_black, self.sl_white, self.sl_gamma):
            sl.valueChanged.connect(self._on_sliders)

        top = QHBoxLayout()
        top.addStretch(1)
        for b in (self.btn_auto, self.btn_reset, self.btn_invert):
            top.addWidget(b)
        sliders = QGridLayout()
        for r, (name, sl, lab) in enumerate(((self.tr("Black"), self.sl_black, self.lbl_black),
                                             (self.tr("White"), self.sl_white, self.lbl_white),
                                             (self.tr("Gamma"), self.sl_gamma, self.lbl_gamma))):
            sliders.addWidget(QLabel(name), r, 0)
            sliders.addWidget(sl, r, 1)
            sliders.addWidget(lab, r, 2)
        sliders.setColumnStretch(1, 1)
        right = QVBoxLayout()
        right.addLayout(sliders)
        right.addLayout(chan_row)
        main = QHBoxLayout()
        main.addWidget(self.hist, 1)
        main.addLayout(right, 1)
        card.body.addLayout(top)
        card.body.addLayout(main)
        return card

    @staticmethod
    def _slider(lo: int, hi: int, value: int) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(value)
        return s

    def _build_right(self) -> QWidget:
        # Camera card (zoom 1x) / Focus card (zoom 5x, 10x)
        self.cam_card = Card(self.tr("Camera"))
        form = QFormLayout()
        self.lbl_model = QLabel("–")
        self.lbl_quality = QLabel("–")
        form.addRow(self.tr("Model"), self.lbl_model)
        form.addRow(self.tr("Quality"), self.lbl_quality)
        self.lbl_lens = QLabel("–")
        self.lbl_focal = QLabel("–")
        form.addRow(self.tr("Lens"), self.lbl_lens)
        form.addRow(self.tr("Focal length"), self.lbl_focal)
        for lab in (self.lbl_model, self.lbl_quality, self.lbl_lens, self.lbl_focal):
            lab.setWordWrap(True)  # long names wrap inside the fixed-width card
        self.lbl_battery = QLabel("–")
        form.addRow(self.tr("Battery"), self.lbl_battery)
        self.row_battery = (form.labelForField(self.lbl_battery), self.lbl_battery)
        for w in self.row_battery:
            w.hide()
        self.cam_card.body.addLayout(form)

        self.focus_card = Card(self.tr("Focus"))
        self.lbl_sharp = QLabel("–")
        f = QFont(self.lbl_sharp.font())
        f.setPixelSize(32)
        self.lbl_sharp.setFont(f)
        sharp_hint = QLabel(self.tr("sharpness · variance of Laplacian"))
        sharp_hint.setProperty("role", "dim")
        self.btn_af = QPushButton(self.tr("Run autofocus"))
        self.btn_af.setProperty("primary", True)
        self.btn_af.clicked.connect(self.ctrl.autofocus)
        steps = QHBoxLayout()
        self.focus_btns = {s: theme.icon_button(QPushButton(glyph), name) for s, glyph, name in [
            (FocusStep.NEAR_3, "≪≪", self.tr("Focus nearer, large step")),
            (FocusStep.NEAR_2, "≪", self.tr("Focus nearer, medium step")),
            (FocusStep.NEAR_1, "‹", self.tr("Focus nearer, small step")),
            (FocusStep.FAR_1, "›", self.tr("Focus farther, small step")),
            (FocusStep.FAR_2, "≫", self.tr("Focus farther, medium step")),
            (FocusStep.FAR_3, "≫≫", self.tr("Focus farther, large step"))]}
        for step, b in self.focus_btns.items():
            b.clicked.connect(lambda _=False, s=step: self.ctrl.focus_step(s))
            steps.addWidget(b)
        for w in (self.lbl_sharp, sharp_hint, self.btn_af, QLabel(self.tr("Fine steps (near ← → far)"))):
            self.focus_card.body.addWidget(w)
        self.focus_card.body.addLayout(steps)
        self.focus_card.body.addWidget(Note(self.tr(
            "Focus under white light, then switch back to UV. The shutter never refocuses.")))
        self.focus_card.hide()

        exp = Card(self.tr("Exposure"))
        eform = QFormLayout()
        self.combos = {p: QComboBox() for p in (Prop.ISO, Prop.TV, Prop.AV)}
        eform.addRow(self.tr("ISO"), self.combos[Prop.ISO])
        eform.addRow(self.tr("Shutter"), self.combos[Prop.TV])
        eform.addRow(self.tr("Aperture"), self.combos[Prop.AV])
        for prop, combo in self.combos.items():
            combo.currentIndexChanged.connect(lambda _i, p=prop: self._combo_changed(p))
        hint = QLabel(self.tr("Values are read from the camera; only what it allows is offered."))
        hint.setWordWrap(True)
        hint.setProperty("role", "dim")
        exp.body.addLayout(eform)
        exp.body.addWidget(hint)

        single = Card(self.tr("Single frame"))
        self.btn_capture = QPushButton(self.tr("Capture frame"))
        self.btn_capture.setProperty("primary", True)
        self.btn_capture.clicked.connect(self._capture)
        self.lbl_file = QLabel("–")
        self.lbl_file.setProperty("role", "dim")
        self.stat_bright = StatValue(self.tr("Brightest"))
        self.stat_sat = StatValue(self.tr("Saturated"))
        stats = QHBoxLayout()
        stats.addWidget(self.stat_bright)
        stats.addWidget(self.stat_sat)
        measured = QLabel(self.tr("measured on RAW"))
        measured.setProperty("role", "dim")
        for w in (self.btn_capture, self.lbl_file):
            single.body.addWidget(w)
        single.body.addLayout(stats)
        single.body.addWidget(measured)

        col = QWidget()
        col.setFixedWidth(300)
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        for w in (self.cam_card, self.focus_card, exp, single):
            lay.addWidget(w)
        lay.addStretch(1)
        return col

    def _build_status_bar(self) -> None:
        sb = self.statusBar()
        self.status_conn = QLabel(self.tr("Disconnected"))
        self.status_fps = QLabel("")
        self.status_light = QLabel("")
        for lab in (self.status_conn, self.status_fps, self.status_light):
            sb.addWidget(lab)
        self.btn_log = QPushButton(self.tr("Log"))
        self.btn_log.setFlat(True)
        self.btn_log.clicked.connect(self._open_log)
        sb.addPermanentWidget(self.btn_log)
        self._update_status()

    def _set_tab_order(self) -> None:
        chain: list[QWidget] = [
            self.light_combo, self.btn_new, self.btn_grid, self.btn_clip, *self.zoom_btns.values(),
            self.btn_retry, self.btn_open_log, self.btn_reconnect, self.btn_cancel,
            self.btn_auto, self.btn_reset, self.btn_invert, self.sl_black, self.sl_white, self.sl_gamma,
            *self.chan_btns, self.btn_af, *self.focus_btns.values(), *self.combos.values(),
            self.btn_capture, self.btn_log]
        for a, b in zip(chain, chain[1:]):
            QWidget.setTabOrder(a, b)

    # --- connection ---
    def _connect(self) -> None:
        self._connecting = True
        self.ctrl.connect_camera()

    def _on_connected(self, info: CameraInfo) -> None:
        self._connecting = False
        self._connected = True
        self.retry_timer.stop()
        self.lost_timer.stop()
        self.lost_card.hide()
        self.stack.setCurrentIndex(0)
        self.chip_camera.setText(f"● {info.model}")
        self.lbl_model.setText(info.model)
        self._set_enabled(True)
        self._update_status()
        self._log("INFO", self.tr("Connected: {0}").format(info.model))
        self.zoom_btns[1].setChecked(True)
        self._on_zoom(1, send=False)
        self.view.set_message(self.tr("Starting live view…"))
        self.ctrl.set_live_view(True)

    def _on_connect_failed(self, msg: str) -> None:
        self._connecting = False
        self._log("WARNING", msg)
        self._show_nocam(msg)

    def _on_disconnected(self) -> None:
        self._connected = False
        self._show_nocam(self.tr("Camera disconnected."))
        self._log("INFO", self.tr("Disconnected."))

    def _show_nocam(self, msg: str) -> None:
        self._connected = False
        rest = msg.removeprefix("No camera found.").strip()
        self.nocam_msg.setText(rest)
        self.nocam_msg.setVisible(bool(rest))
        self.stack.setCurrentIndex(1)
        self.view.set_message(self.tr("Camera is not connected"))
        self.lost_card.hide()
        self.lost_timer.stop()
        self.chip_camera.setText(self.tr("No camera"))
        self.chip_quality.setText("–")
        self.lbl_model.setText("–")
        self._set_enabled(False)
        self._update_status()
        if self._auto_retry:
            self.retry_timer.start(5000)

    def _retry(self) -> None:
        if not self._connecting and not self._connected:
            self._connect()

    # --- connection lost ---
    def _on_lost(self) -> None:
        self._log("WARNING", self.tr("Connection lost."))
        self._connected = False
        self._attempts = 0
        self.chip_camera.setText(self.tr("Connection lost"))
        self.lost_card.show()
        self._update_status()
        self._lost_tick(first=True)
        self.lost_timer.start(1000)

    def _lost_tick(self, first: bool = False) -> None:
        age = int(time.monotonic() - self._last_frame_t) if self._last_frame_t else 0
        self.lost_last.setText(self.tr("Last frame {0} s ago").format(age))
        if first or self._tick_odd():
            self._reconnect_now()

    def _tick_odd(self) -> bool:
        self._ticks = getattr(self, "_ticks", 0) + 1
        return self._ticks % 2 == 0

    def _reconnect_now(self) -> None:
        self._attempts += 1
        self.lost_attempt.setText(self.tr("Attempt {0}").format(self._attempts))
        self._update_status()
        self.ctrl.reconnect()

    def _cancel_reconnect(self) -> None:
        self._auto_retry = False
        self.lost_timer.stop()
        self.lost_card.hide()
        self.ctrl.disconnect_camera()

    def _on_reconnected(self, info: CameraInfo) -> None:
        self.lost_timer.stop()
        self.lost_card.hide()
        self._connected = True
        self.chip_camera.setText(f"● {info.model}")
        self._update_status()
        self._log("INFO", self.tr("Reconnected: {0}").format(info.model))

    # --- exposure ---
    def _on_options(self, opts: dict) -> None:
        self._options_updating = True
        try:
            for prop, (allowed, current) in opts.items():
                combo = self.combos[prop]
                combo.clear()
                for code in allowed:
                    combo.addItem(_LABELS[prop](code), code)
                idx = combo.findData(current)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
        finally:
            self._options_updating = False

    def _combo_changed(self, prop: Prop) -> None:
        if self._options_updating:
            return
        code = self.combos[prop].currentData()
        if code is not None:
            self.ctrl.set_value(prop, int(code))

    def _on_message(self, text: str) -> None:
        self._log("INFO", text)

    @staticmethod
    def _dim_text(label: QLabel, text: str | None, missing: str) -> None:
        label.setText(text or missing)
        label.setProperty("role", None if text else "dim")
        label.style().unpolish(label)
        label.style().polish(label)

    def _on_status(self, status: dict) -> None:
        code = status.get(Prop.IMAGE_QUALITY)
        if code is not None:
            raw = values.is_raw_only(int(code))
            self.lbl_quality.setText(values.quality_label(int(code)))
            self.chip_quality.setText(values.quality_label(int(code)) if raw
                                      else self.tr("Not RAW — will be set on capture"))
        lens = status.get("lens")
        if lens is not None:
            self._dim_text(self.lbl_lens, lens.name, self.tr("not reported"))
            self._dim_text(self.lbl_focal, f"{lens.focal_mm:g} mm" if lens.focal_mm else None,
                           self.tr("not reported by the camera"))
        zooms = status.get("zooms")
        if zooms is not None:
            self._apply_zooms(tuple(zooms))
        battery = status.get(Prop.BATTERY)
        for w in self.row_battery:
            w.setVisible(battery is not None)
        if battery is not None:
            self.lbl_battery.setText(f"{battery} %" if isinstance(battery, int) else str(battery))

    # --- single frame ---
    def _channel(self) -> int:
        return max(self.chan_group.checkedId(), 0)

    def _capture(self) -> None:
        self._awaiting_capture = True
        self.ctrl.capture(self.out_dir)

    def _on_captured(self, path: Path) -> None:
        self._log("INFO", self.tr("Saved: {0}").format(path))
        if not self._awaiting_capture:
            return
        self._awaiting_capture = False
        self._last_capture = path
        self.lbl_file.setText(path.name)
        self.stat_bright.set_value(self.tr("measuring…"))
        self.stat_sat.set_value("…")
        self.ctrl.measure_file(path, _CHANNELS[self._channel()])

    def _on_measured(self, path: Path, m) -> None:
        if path != self._last_capture:
            return
        self.stat_bright.set_value(f"{m.brightest_adu:.0f} ADU")
        if m.saturated_fraction > 0:
            self.stat_sat.set_value(self.tr("{0:.2f} % — saturated").format(m.saturated_fraction * 100), theme.BAD)
        else:
            self.stat_sat.set_value(f"{m.saturated_fraction * 100:.2f} %", theme.OK)

    # --- zoom, light ---
    def _apply_zooms(self, zooms: tuple[int, ...]) -> None:
        """Show only the magnifier steps the connected camera really has."""
        for z, b in self.zoom_btns.items():
            b.setVisible(z in zooms)
        if self.zoom_group.checkedId() not in zooms:
            self.zoom_btns[1].setChecked(True)
            self._on_zoom(1)
    def _on_zoom(self, factor: int, send: bool = True) -> None:
        self.cam_card.setVisible(factor == 1)
        self.focus_card.setVisible(factor > 1)
        if send:
            self.ctrl.set_zoom(factor)

    def _on_light(self) -> None:
        self.light = str(self.light_combo.currentData())
        self._update_status()

    def _open_wizard(self) -> None:
        from .wizard import GelWizard

        self._wizard = GelWizard(self.ctrl, self.out_dir, self.light, self)
        self._wizard.open()  # window-modal: no settings/capture interleaving with a series

    # --- live frames and display (preview only; the frame from the controller is never modified) ---
    def _on_frame(self, frame: np.ndarray) -> None:
        now = time.monotonic()
        self._last_frame_t = now
        self._frame_times.append(now)
        self._frame = frame
        self._frame_n += 1
        stats = self._frame_n % _STATS_EVERY == 1
        if stats:
            self.lbl_sharp.setText(f"{sharpness_rgb(frame):.1f}")
            self._update_status()
        self._render(stats=stats)

    def _fps(self) -> float:
        t = self._frame_times
        return (len(t) - 1) / (t[-1] - t[0]) if len(t) > 1 and t[-1] > t[0] else 0.0

    def _render(self, stats: bool = False) -> None:
        frame = self._frame
        if frame is None:
            return
        ch = self._channel()
        black, white = self.sl_black.value(), self.sl_white.value()
        out = apply_display(frame, black, white, self.sl_gamma.value() / 10, self.btn_invert.isChecked())
        if self.btn_clip.isChecked():
            out = overlay_clipping(out, clipped_mask(frame, ch))
        self.view.set_frame(out)
        h, w, _ = frame.shape
        zoom = self.zoom_group.checkedId()
        prefix = self.tr("camera magnifier {0}× · ").format(zoom) if zoom > 1 else ""
        self.view.set_caption(prefix + self.tr("live view · {0} × {1} · {2:.0f} fps").format(w, h, self._fps()))
        if stats:
            self.hist.set_data(histogram(frame, ch), black, white)

    def _on_sliders(self) -> None:
        self.lbl_black.setText(str(self.sl_black.value()))
        self.lbl_white.setText(str(self.sl_white.value()))
        self.lbl_gamma.setText(f"{self.sl_gamma.value() / 10:.2f}")
        self._render(stats=True)

    def _auto_stretch(self) -> None:
        if self._frame is not None:
            black, white = auto_levels(self._frame, self._channel())
            self.sl_black.setValue(black)
            self.sl_white.setValue(white)

    def _reset_display(self) -> None:
        self.sl_black.setValue(0)
        self.sl_white.setValue(255)
        self.sl_gamma.setValue(10)
        self.btn_invert.setChecked(False)

    # --- status bar, log ---
    def _update_status(self) -> None:
        if self.lost_card.isVisibleTo(self):
            self.status_conn.setText(self.tr("Reconnecting · attempt {0}").format(self._attempts))
        elif self._connected:
            self.status_conn.setText(self.tr("Connected"))
        else:
            self.status_conn.setText(self.tr("Disconnected · retrying every 5 s") if self._auto_retry
                                     else self.tr("Disconnected"))
        self.status_fps.setText(self.tr("· live view {0:.1f} fps").format(self._fps()) if self._connected else "")
        label = dict(_LIGHTS)[self.light]
        self.status_light.setText("· " + self.tr(label))

    def _set_enabled(self, on: bool) -> None:
        for w in [self.btn_new, self.btn_capture, self.btn_af, *self.focus_btns.values(),
                  *self.combos.values(), *self.zoom_btns.values()]:
            w.setEnabled(on)

    def _log(self, level: str, text: str) -> None:
        self._log_entries.append((datetime.now().strftime("%H:%M:%S"), level, text))
        if self._log_dialog is not None and self._log_dialog.isVisible():
            self._log_dialog.refresh()

    def _open_log(self) -> None:
        self._log_dialog = LogDialog(self._log_entries, self)
        self._log_dialog.show()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        for t in (self.frame_timer, self.retry_timer, self.lost_timer):
            t.stop()
        self.ctrl.shutdown()
        super().closeEvent(event)
