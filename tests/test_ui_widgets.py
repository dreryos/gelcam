import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gelcam.ui import theme  # noqa: E402
from gelcam.ui.widgets import Card, HistogramView, Note, PreviewView, StatValue  # noqa: E402


def test_widgets_render():
    app = QApplication.instance() or QApplication([])
    card = Card("Title")
    note = Note("Careful", "error")
    card.body.addWidget(note)
    assert card.objectName() == "card" and note.property("note") == "error"
    card.grab()

    pv = PreviewView()
    pv.resize(400, 300)
    pv.set_message("No frame")
    pv.grab()
    pv.set_frame(np.random.default_rng(0).integers(0, 255, (60, 90, 3), dtype=np.uint8))
    pv.set_caption("caption")
    pv.set_grid(True)
    assert not pv.grab().isNull()
    pv.set_frame(None)
    pv.grab()

    hv = HistogramView()
    hv.set_data(np.arange(64), 10, 200)
    assert not hv.grab().isNull()
    hv.set_data(np.zeros(64))
    hv.grab()

    sv = StatValue("Peak")
    sv.set_value("12 %", theme.OK)
    sv.grab()
