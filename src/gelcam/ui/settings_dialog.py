"""Settings window: where the application keeps images and the flat-field library."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .. import settings as cfg
from .widgets import Card, Note


class SettingsDialog(QDialog):
    def __init__(self, current: cfg.Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Settings"))
        self.resize(560, 460)
        self._current = current
        self._root: Path | None = current.root  # None = default
        lay = QVBoxLayout(self)

        card = Card(self.tr("Folder for images and calibration"))
        self.root_label = QLabel()
        self.root_label.setWordWrap(True)
        self.root_label.setTextInteractionFlags(self.root_label.textInteractionFlags().TextSelectableByMouse)
        card.body.addWidget(self.root_label)
        row = QHBoxLayout()
        self.btn_choose = QPushButton(self.tr("Change…"))
        self.btn_choose.clicked.connect(self._choose)
        self.btn_default = QPushButton(self.tr("Use the default"))
        self.btn_default.clicked.connect(lambda: self.set_root(None))
        row.addWidget(self.btn_choose)
        row.addWidget(self.btn_default)
        row.addStretch()
        card.body.addLayout(row)
        self.detail = QLabel()
        self.detail.setProperty("role", "dim")
        self.detail.setWordWrap(True)
        card.body.addWidget(self.detail)
        lay.addWidget(card)

        self.warning = Note("", "error")
        self.warning.hide()
        lay.addWidget(self.warning)
        lay.addWidget(Note(self.tr(
            "The new folder applies to what you take from now on. Folders that already exist are not moved; "
            "copy them over if you need them in the new place.")))
        live = Card(self.tr("Live view"))
        self.live_aperture = QCheckBox(self.tr("Open the aperture for the live view (f/5.6 or the widest)"))
        self.live_aperture.setChecked(current.live_view_aperture)
        live.body.addWidget(self.live_aperture)
        hint = QLabel(self.tr("A wide aperture makes the live view brighter. Every capture, series and flat still "
                              "uses the aperture you set for them."))
        hint.setProperty("role", "dim")
        hint.setWordWrap(True)
        live.body.addWidget(hint)
        lay.addWidget(live)
        lay.addStretch()

        row = QHBoxLayout()
        self.btn_cancel = QPushButton(self.tr("Cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton(self.tr("Save"))
        self.btn_ok.setProperty("primary", True)
        self.btn_ok.clicked.connect(self.accept)
        row.addStretch()
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_ok)
        lay.addLayout(row)
        self.set_root(self._root)

    @property
    def result_settings(self) -> cfg.Settings:
        return replace(self._current, root=self._root, live_view_aperture=self.live_aperture.isChecked())

    def _choose(self) -> None:
        start = str(self._root or cfg.default_root())
        folder = QFileDialog.getExistingDirectory(self, self.tr("Choose the folder for images and calibration"), start)
        if folder:
            self.set_root(Path(folder))

    def set_root(self, root: Path | None) -> None:
        """Shows the consequences of a root folder and blocks Save when nothing can be written there."""
        self._root = root
        s = cfg.Settings(root=root)
        self.root_label.setText(str(s.effective_root) + ("  " + self.tr("(default)") if root is None else ""))
        free = cfg.free_gb(s.effective_root)
        self.detail.setText(self.tr("Images: {0}\nFlat fields: {1}\nFree space on that disk: {2}").format(
            s.images_dir, s.flats_dir, f"{free:,.0f} GB" if free is not None else "?"))
        problem = cfg.check_writable(s.effective_root)
        lines = []
        if problem:
            lines.append(self.tr("Nothing can be written to this folder: {0}").format(problem))
        elif cfg.is_synchronised(s.effective_root):
            lines.append(self.tr("This folder is synchronised to the cloud. Every raw frame is about 20 MB and a flat "
                                 "field set about 600 MB, so the synchronisation will be busy and may fill the "
                                 "cloud storage."))
        self.warning.setText("\n".join(lines))
        self.warning.setVisible(bool(lines))
        self.btn_ok.setEnabled(problem is None)
