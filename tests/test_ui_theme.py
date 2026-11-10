"""Rules from the mockup accessibility audit (docs/GELCAM_PLAN.md), checked on the real window."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QSlider, QWidget  # noqa: E402

from gelcam.camera import MockCamera  # noqa: E402
from gelcam.ui import theme  # noqa: E402
from gelcam.ui.controller import CameraController  # noqa: E402
from gelcam.ui.main_window import MainWindow  # noqa: E402


def test_contrast_reference_values():
    assert theme.contrast("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert theme.contrast("#777777", "#777777") == pytest.approx(1.0)


@pytest.mark.parametrize("fg", [theme.INK, theme.DIM, theme.ACC, theme.OK, theme.WARN, theme.BAD])
@pytest.mark.parametrize("bg", [theme.BG, theme.PANEL, theme.SELECTED])
def test_text_colours_meet_aa(fg, bg):
    assert theme.contrast(fg, bg) >= 4.5


def test_preview_and_primary_button_meet_aa():
    assert theme.contrast(theme.PV_INK, theme.DARK) >= 4.5
    assert theme.contrast("#FFFFFF", theme.ACC) >= 4.5


@pytest.mark.parametrize("note", [theme.NOTE_INFO, theme.NOTE_ERROR])
def test_note_colours_meet_aa(note):
    assert theme.contrast(note[0], note[1]) >= 4.5


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    win = MainWindow(CameraController(lambda: MockCamera(seed=1)))
    win.show()
    app.processEvents()
    yield win
    win.close()


def test_buttons_are_named_and_large_enough(window):
    for b in window.findChildren(QAbstractButton):
        if not any(ch.isalpha() for ch in b.text()):
            assert b.toolTip() and b.accessibleName(), f"glyph-only button {b.text()!r} has no name"
        assert b.sizeHint().height() >= theme.MIN_TARGET, b.text()
        assert b.sizeHint().width() >= theme.MIN_TARGET, b.text()


def test_tab_order_follows_the_right_column(window):
    window.zoom_btns[10].click()  # Focus card replaces the Camera card
    expected = [window.btn_af, *window.focus_btns.values(), *window.combos.values(), window.btn_capture]
    chain, w = [], window.btn_af
    for _ in range(300):
        if w in expected and w not in chain:
            chain.append(w)
        w = w.nextInFocusChain()
    assert chain == expected


def _dark(app):
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor("black"))
    pal.setColor(QPalette.ColorRole.Base, QColor("black"))
    pal.setColor(QPalette.ColorRole.Text, QColor("white"))
    app.setPalette(pal)


def test_apply_overrides_dark_palette():
    app = QApplication.instance()
    _dark(app)
    theme.apply(app)
    pal = app.palette()
    assert pal.color(QPalette.ColorRole.Window) == QColor(theme.BG)
    assert pal.color(QPalette.ColorRole.Text) == QColor(theme.INK)


def test_slider_groove_visible_in_dark_os():
    app = QApplication.instance()
    _dark(app)
    theme.apply(app)
    box = QWidget()
    box.setStyleSheet(f"background: {theme.PANEL};")
    box.resize(240, 40)
    s = QSlider(Qt.Orientation.Horizontal, box)
    s.setGeometry(10, 8, 200, 24)
    s.setValue(0)
    box.show()
    app.processEvents()
    img = box.grab().toImage()
    px = img.pixelColor(180, 20)
    assert px != QColor(theme.PANEL)
    assert px.lightness() < QColor(theme.PANEL).lightness() - 60


def test_groove_contrast_non_text():
    assert theme.contrast(theme.GROOVE, theme.PANEL) >= 3.0
    assert theme.contrast(theme.GROOVE, theme.BG) >= 3.0


def test_combo_popup_is_light():
    app = QApplication.instance()
    _dark(app)
    theme.apply(app)
    combo = QComboBox()
    combo.addItems(["a", "b"])
    combo.show()
    app.processEvents()
    assert combo.view().viewport().palette().color(QPalette.ColorRole.Base) == QColor(theme.PANEL) or (
        combo.view().viewport().grab().toImage().pixelColor(2, 2) == QColor(theme.PANEL))
