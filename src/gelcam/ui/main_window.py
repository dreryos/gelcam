"""Hlavní okno: připojení, live view s lupou, ostření, expozice a jednotlivý snímek."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from platformdirs import user_documents_dir
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..camera import CameraInfo, FocusStep, Prop, values
from .controller import CameraController

_LABELS = {Prop.ISO: values.iso_label, Prop.TV: values.tv_label, Prop.AV: values.av_label}


def frame_stats(frame: np.ndarray, channel: int = 0) -> tuple[np.ndarray, float]:
    """Histogram (64 košů) a podíl saturovaných pixelů vybraného kanálu náhledu."""
    ch = frame[..., channel]
    hist, _ = np.histogram(ch, bins=64, range=(0, 256))
    return hist, float((ch >= 250).mean())


class MainWindow(QMainWindow):
    def __init__(self, controller: CameraController) -> None:
        super().__init__()
        self.setWindowTitle("GelCam")
        self.resize(1200, 760)
        self.ctrl = controller
        self.out_dir = Path(user_documents_dir()) / "GelCam" / "snimky"
        self._options_updating = False

        # --- live view ---
        self.view = QLabel("Foťák není připojený")
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.view.setMinimumSize(640, 427)
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.view.setStyleSheet("background:#111; color:#aaa;")
        self.hist = QLabel()
        self.hist.setFixedHeight(60)
        self.sat = QLabel("Saturace: –")

        # --- ovládání ---
        self.btn_connect = QPushButton("Připojit foťák")
        self.btn_live = QPushButton("Live view")
        self.btn_live.setCheckable(True)
        self.zoom = QComboBox()
        self.zoom.addItems(["1×", "5×", "10×"])
        self.btn_af = QPushButton("Autofokus")
        self.focus_btns = {s: QPushButton(lbl) for s, lbl in [
            (FocusStep.NEAR_3, "≪≪"), (FocusStep.NEAR_2, "≪"), (FocusStep.NEAR_1, "‹"),
            (FocusStep.FAR_1, "›"), (FocusStep.FAR_2, "≫"), (FocusStep.FAR_3, "≫≫")]}
        self.combos = {p: QComboBox() for p in (Prop.ISO, Prop.TV, Prop.AV)}
        self.btn_capture = QPushButton("Vyfotit snímek")
        self.btn_dir = QPushButton("Složka…")
        self.dir_label = QLabel(str(self.out_dir))
        self.dir_label.setWordWrap(True)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)

        conn = QGroupBox("Foťák")
        cl = QVBoxLayout(conn)
        self.model_label = QLabel("–")
        cl.addWidget(self.btn_connect)
        cl.addWidget(self.model_label)

        lv = QGroupBox("Live view a ostření")
        ll = QVBoxLayout(lv)
        row = QHBoxLayout()
        row.addWidget(self.btn_live)
        row.addWidget(QLabel("Lupa"))
        row.addWidget(self.zoom)
        ll.addLayout(row)
        ll.addWidget(self.btn_af)
        frow = QHBoxLayout()
        for b in self.focus_btns.values():
            b.setFixedWidth(40)
            frow.addWidget(b)
        ll.addWidget(QLabel("Ostření: blíž ← → dál"))
        ll.addLayout(frow)

        exp = QGroupBox("Expozice")
        el = QFormLayout(exp)
        el.addRow("ISO", self.combos[Prop.ISO])
        el.addRow("Čas", self.combos[Prop.TV])
        el.addRow("Clona", self.combos[Prop.AV])

        cap = QGroupBox("Snímek")
        capl = QVBoxLayout(cap)
        capl.addWidget(self.btn_capture)
        drow = QHBoxLayout()
        drow.addWidget(self.dir_label, 1)
        drow.addWidget(self.btn_dir)
        capl.addLayout(drow)

        side = QVBoxLayout()
        for g in (conn, lv, exp, cap):
            side.addWidget(g)
        side.addWidget(QLabel("Záznam"))
        side.addWidget(self.log, 1)
        side_w = QWidget()
        side_w.setLayout(side)
        side_w.setFixedWidth(340)

        left = QVBoxLayout()
        left.addWidget(self.view, 1)
        left.addWidget(self.hist)
        left.addWidget(self.sat)
        main = QHBoxLayout()
        main.addLayout(left, 1)
        main.addWidget(side_w)
        central = QWidget()
        central.setLayout(main)
        self.setCentralWidget(central)

        # --- signály ---
        self.btn_connect.clicked.connect(self._toggle_connect)
        self.btn_live.toggled.connect(self.ctrl.set_live_view)
        self.zoom.currentIndexChanged.connect(lambda i: self.ctrl.set_zoom((1, 5, 10)[i]))
        self.btn_af.clicked.connect(self.ctrl.autofocus)
        for step, b in self.focus_btns.items():
            b.clicked.connect(lambda _=False, s=step: self.ctrl.focus_step(s))
        for prop, combo in self.combos.items():
            combo.currentIndexChanged.connect(lambda _i, p=prop: self._combo_changed(p))
        self.btn_capture.clicked.connect(lambda: self.ctrl.capture(self.out_dir))
        self.btn_dir.clicked.connect(self._choose_dir)

        self.ctrl.connected.connect(self._on_connected)
        self.ctrl.disconnected.connect(self._on_disconnected)
        self.ctrl.options_ready.connect(self._on_options)
        self.ctrl.frame_ready.connect(self._on_frame)
        self.ctrl.captured.connect(lambda p: self._log(f"Uloženo: {p}"))
        self.ctrl.message.connect(self._log)
        self.ctrl.error.connect(lambda m: self._log(f"CHYBA: {m}"))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.ctrl.request_frame)
        self.timer.start(100)
        self._connected = False
        self._set_enabled(False)

    # --- reakce ---
    def _toggle_connect(self) -> None:
        if self._connected:
            self.btn_live.setChecked(False)
            self.ctrl.disconnect_camera()
        else:
            self._log("Připojuji…")
            self.ctrl.connect_camera()

    def _on_connected(self, info: CameraInfo) -> None:
        self._connected = True
        self.model_label.setText(info.model)
        self.btn_connect.setText("Odpojit")
        self._set_enabled(True)
        self._log(f"Připojeno: {info.model}")

    def _on_disconnected(self) -> None:
        self._connected = False
        self.model_label.setText("–")
        self.btn_connect.setText("Připojit foťák")
        self.view.setText("Foťák není připojený")
        self._set_enabled(False)
        self._log("Odpojeno.")

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

    def _on_frame(self, frame: np.ndarray) -> None:
        h, w, _ = frame.shape
        img = QImage(frame.tobytes(), w, h, 3 * w, QImage.Format.Format_RGB888)
        self.view.setPixmap(QPixmap.fromImage(img).scaled(
            self.view.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        hist, sat = frame_stats(frame, channel=0)
        self._draw_hist(hist)
        self.sat.setText(f"Saturace (R, náhled): {sat * 100:.2f} %  – přesně se měří až na RAW")

    def _draw_hist(self, hist: np.ndarray) -> None:
        w, h = 64 * 4, 60
        canvas = np.full((h, w), 30, np.uint8)
        top = hist.max() or 1
        for i, v in enumerate(hist):
            bar = int(round(np.log1p(v) / np.log1p(top) * (h - 2)))
            canvas[h - bar:, i * 4:i * 4 + 3] = 210
        img = QImage(canvas.tobytes(), w, h, w, QImage.Format.Format_Grayscale8)
        self.hist.setPixmap(QPixmap.fromImage(img))

    def _choose_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Složka pro snímky", str(self.out_dir))
        if d:
            self.out_dir = Path(d)
            self.dir_label.setText(d)

    def _set_enabled(self, on: bool) -> None:
        for w in [self.btn_live, self.zoom, self.btn_af, self.btn_capture, *self.focus_btns.values(),
                  *self.combos.values()]:
            w.setEnabled(on)

    def _log(self, text: str) -> None:
        self.log.appendPlainText(text)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.timer.stop()
        self.ctrl.shutdown()
        super().closeEvent(event)
