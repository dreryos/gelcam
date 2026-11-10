"""Colours and the application stylesheet, taken from the audited mockups.

The colour values are the ones in `design/design_wizard.py`, checked for WCAG 2.2 AA contrast
on 10 Nov 2026 (docs/GELCAM_PLAN.md, "Accessibility and readability audit"). Do not add new
greys or greens here without running `contrast()` against the backgrounds they sit on.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPalette, QPolygon
from PySide6.QtWidgets import QAbstractButton, QApplication

# Backgrounds
BG = "#F2F2F2"
PANEL = "#FFFFFF"
SELECTED = "#E7EEFB"
DARK = "#141414"  # live view / preview area
LINE = "#D8D8D8"
# Text and state colours (all >= 4.5:1 on BG, PANEL and SELECTED)
INK = "#1A1A1A"
DIM = "#6B6B6B"
ACC = "#2563D9"
OK = "#177A45"
WARN = "#9E5100"
BAD = "#C0392B"
PV_INK = "#9E9E9E"  # captions inside the dark preview (6.9:1 on DARK)
# Note boxes: (text, background, border)
NOTE_INFO = ("#6B5518", "#FFF8E6", "#E8D6A8")
NOTE_ERROR = ("#8C2A1E", "#FDECEA", "#F0C0BA")

GROOVE = "#8C8C8C"  # slider groove / handle border, >= 3:1 on PANEL and BG (WCAG 1.4.11)
MIN_TARGET = 24  # px, WCAG 2.5.8


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    r, g, b = (_lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str) -> float:
    """WCAG contrast ratio of two #RRGGBB colours (1.0 to 21.0)."""
    hi, lo = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _arrow_png() -> str:
    """Draw the combo-box arrow once into a temp PNG (QSS can only reference files)."""
    img = QImage(10, 6, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(INK))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPolygon(QPolygon([QPoint(0, 0), QPoint(10, 0), QPoint(5, 6)]))
    p.end()
    path = Path(tempfile.gettempdir()) / "gelcam_combo_arrow.png"
    img.save(str(path))
    return path.as_posix()


_ARROW = _arrow_png()

# The :focus rules matter: once a widget is styled with QSS, Qt no longer draws the native
# focus rectangle, so keyboard focus would become invisible without them.
STYLESHEET = f"""
QWidget {{ color: {INK}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QGroupBox {{
    background: {PANEL}; border: 1px solid {LINE}; border-radius: 6px;
    margin-top: 14px; padding: 10px 8px 8px 8px; font-weight: bold;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QPushButton {{
    background: {PANEL}; border: 1px solid #BFBFBF; border-radius: 4px;
    padding: 4px 12px; min-height: {MIN_TARGET - 8}px; font-weight: normal;
}}
QPushButton:checked {{ background: {SELECTED}; border-color: {ACC}; color: {ACC}; }}
QPushButton:disabled {{ color: #A8A8A8; border-color: #DCDCDC; }}
QPushButton[primary="true"] {{ background: {ACC}; border-color: {ACC}; color: #FFFFFF; }}
QPushButton[primary="true"]:disabled {{ background: #BFD3F5; border-color: #BFD3F5; }}
QPushButton:focus, QComboBox:focus, QLineEdit:focus, QPlainTextEdit:focus {{
    border: 2px solid {ACC};
}}
QComboBox, QLineEdit {{
    background: {PANEL}; border: 1px solid #BFBFBF; border-radius: 4px;
    padding: 3px 8px; min-height: {MIN_TARGET - 6}px; font-weight: normal;
}}
QPlainTextEdit {{ background: {PANEL}; border: 1px solid {LINE}; font-weight: normal; }}
QSlider::groove:horizontal {{ height: 4px; background: {GROOVE}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACC}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {PANEL}; border: 1px solid {GROOVE}; width: 16px; margin: -6px 0; border-radius: 8px;
}}
QSlider::handle:horizontal:focus {{ border: 2px solid {ACC}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url({_ARROW}); width: 10px; height: 6px; }}
QComboBox QAbstractItemView {{
    background: {PANEL}; color: {INK}; selection-background-color: {SELECTED};
    selection-color: {INK}; border: 1px solid {LINE}; outline: 0;
}}
QLabel {{ font-weight: normal; }}
QLabel[role="dim"] {{ color: {DIM}; }}
QLabel[role="preview"] {{ background: {DARK}; color: {PV_INK}; }}
QFrame#card {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 6px; }}
QLabel[note="info"] {{
    color: {NOTE_INFO[0]}; background: {NOTE_INFO[1]}; border: 1px solid {NOTE_INFO[2]};
    padding: 10px; border-radius: 5px;
}}
QLabel[note="error"] {{
    color: {NOTE_ERROR[0]}; background: {NOTE_ERROR[1]}; border: 1px solid {NOTE_ERROR[2]};
    padding: 10px; border-radius: 5px;
}}
"""


def apply(app: QApplication) -> None:
    """Make the look independent of the OS theme: Fusion style, explicit light palette, stylesheet."""
    app.setStyle("Fusion")
    pal = QPalette()
    for role, col in (
        (QPalette.ColorRole.Window, BG), (QPalette.ColorRole.Base, PANEL),
        (QPalette.ColorRole.AlternateBase, BG), (QPalette.ColorRole.Button, PANEL),
        (QPalette.ColorRole.ToolTipBase, PANEL), (QPalette.ColorRole.WindowText, INK),
        (QPalette.ColorRole.Text, INK), (QPalette.ColorRole.ButtonText, INK),
        (QPalette.ColorRole.ToolTipText, INK), (QPalette.ColorRole.PlaceholderText, DIM),
        (QPalette.ColorRole.Highlight, ACC), (QPalette.ColorRole.HighlightedText, "#FFFFFF"),
        (QPalette.ColorRole.Link, ACC),
    ):
        pal.setColor(role, QColor(col))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor("#A8A8A8"))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)


def icon_button(button: QAbstractButton, name: str) -> QAbstractButton:
    """Give a button that shows only a glyph a tooltip and an accessible name."""
    button.setToolTip(name)
    button.setAccessibleName(name)
    return button
