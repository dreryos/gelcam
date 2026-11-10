"""Small reusable widgets. Colours come from `theme` only."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from . import theme

HIST_BG = "#1C1C1C"
HIST_BAR = "#8FB4F2"


class Card(QFrame):
    def __init__(self, title: str | None = None) -> None:
        super().__init__()
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        if title:
            label = QLabel(title)
            label.setStyleSheet("font-weight: bold;")
            self.body.addWidget(label)


class Note(QLabel):
    def __init__(self, text: str, kind: str = "info") -> None:
        super().__init__(text)
        self.setWordWrap(True)
        self.setProperty("note", kind)


class PreviewView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(320, 213)
        self._image: QImage | None = None
        self._frame: np.ndarray | None = None  # keeps the buffer alive for QImage
        self._caption = ""
        self._message = ""
        self._grid = False

    def set_frame(self, frame: np.ndarray | None) -> None:
        self._frame = None if frame is None else np.ascontiguousarray(frame)
        if self._frame is None:
            self._image = None
        else:
            h, w, _ = self._frame.shape
            self._image = QImage(self._frame.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        self.update()

    def set_caption(self, text: str) -> None:
        self._caption = text
        self.update()

    def set_message(self, text: str) -> None:
        self._message = text
        self.update()

    def set_grid(self, on: bool) -> None:
        self._grid = on
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.DARK))
        if self._image is not None:
            size = self._image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            r = QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2,
                       size.width(), size.height())
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(r, self._image)
            if self._grid:
                p.setPen(QPen(QColor(255, 255, 255, 51), 1))
                for i in (1, 2):
                    x = r.left() + r.width() * i / 3
                    y = r.top() + r.height() * i / 3
                    p.drawLine(int(x), int(r.top()), int(x), int(r.bottom()))
                    p.drawLine(int(r.left()), int(y), int(r.right()), int(y))
        elif self._message:
            p.setPen(QColor(theme.PV_INK))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._message)
        if self._caption:
            p.setPen(QColor(theme.PV_INK))
            p.drawText(self.rect().adjusted(8, 8, -8, -8),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self._caption)


class HistogramView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(90)
        self._hist: np.ndarray | None = None
        self._black: int | None = None
        self._white: int | None = None

    def set_data(self, hist: np.ndarray, black: int | None = None, white: int | None = None) -> None:
        self._hist, self._black, self._white = hist, black, white
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(HIST_BG))
        w, h = self.width(), self.height()
        if self._hist is not None and len(self._hist):
            v = np.log1p(self._hist.astype(np.float64))
            v = v / max(v.max(), 1e-9)
            bw = w / len(v)
            for i, x in enumerate(v):
                p.fillRect(QRectF(i * bw, h * (1 - x), max(bw - 1, 1), h * x), QColor(HIST_BAR))
        p.setPen(QPen(QColor("#FFFFFF"), 1))
        for marker in (self._black, self._white):
            if marker is not None:
                x = int(marker / 255 * (w - 1))
                p.drawLine(x, 0, x, h)


class StatValue(QWidget):
    def __init__(self, label: str = "") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._label = QLabel(label)
        self._label.setProperty("role", "dim")
        self._value = QLabel("–")
        font = QFont(self._value.font())
        font.setPixelSize(15)
        self._value.setFont(font)
        layout.addWidget(self._label)
        layout.addWidget(self._value)

    def set_value(self, text: str, colour: str | None = None) -> None:
        self._value.setText(text)
        self._value.setStyleSheet(f"color: {colour};" if colour else "")
