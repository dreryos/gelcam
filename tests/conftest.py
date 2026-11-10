import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def _themed_app():
    """One QApplication for the whole run, themed exactly like __main__ does."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from gelcam.ui import theme

    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    return app
