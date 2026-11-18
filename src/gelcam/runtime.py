"""Running the application on a user's PC: data folder, log file, crash report, language, self-test.

Nothing here needs administrator rights: everything is written under `%APPDATA%\\GelCam`
(CLAUDE.md rule 6). A packaged (PyInstaller, windowed) build has no console, so without a log file
and an exception hook a crash would be completely silent.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Callable

from platformdirs import user_data_path

from . import __version__

LOG_NAME = "gelcam.log"


def is_frozen() -> bool:
    """True in a packaged (PyInstaller) build."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Folder with the executable (packaged build) or with the project sources."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """`%APPDATA%\\GelCam` (roaming) on Windows; created on first use."""
    path = user_data_path("GelCam", appauthor=False, roaming=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    return data_dir() / LOG_NAME


def setup_logging() -> Path | None:
    """Rotating log file (3 x 512 kB). Returns its path, or None when the folder is not writable."""
    try:
        path = log_path()
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=512_000, backupCount=2, encoding="utf-8")
    except OSError:
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)
    logging.getLogger("gelcam").info("GelCam %s starting (frozen=%s, python %s, %s)",
                                     __version__, is_frozen(), platform.python_version(), platform.platform())
    return path


def install_excepthook(show: Callable[[str, str], None] | None = None) -> None:
    """Log uncaught exceptions; `show(title, text)` tells the operator where to find the log."""
    log = logging.getLogger("gelcam")

    def hook(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("Uncaught exception:\n%s", text)
        if show is not None:
            try:
                show("GelCam crashed", f"An unexpected error occurred.\n\n{exc}\n\nDetails are in the log file:\n"
                                       f"{log_path()}")
            except Exception:  # noqa: BLE001 - never raise from the exception hook
                pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook


# ----------------------------------------------------------------------------------------- language
def translations_dir() -> Path:
    """Folder with `gelcam_<lang>.qm` files (the bundled data folder, `_internal`, in a packaged build)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_dir())) / "translations"
    return Path(__file__).resolve().parent / "translations"


def choose_language(requested: str | None = None, system_locale: str | None = None) -> str:
    """Language code: explicit request, then `GELCAM_LANG`, then the system language if translated."""
    for candidate in (requested, os.environ.get("GELCAM_LANG")):
        if candidate:
            return candidate.lower()
    code = (system_locale or "").split("_")[0].lower()
    if code and code != "en" and (translations_dir() / f"gelcam_{code}.qm").exists():
        return code
    return "en"


def install_translator(app: object, lang: str) -> bool:
    """Install the Qt translation for `lang`; English is the source language and needs none."""
    if lang == "en":
        return False
    from PySide6.QtCore import QLibraryInfo, QTranslator

    path = translations_dir() / f"gelcam_{lang}.qm"
    translator = QTranslator(app)  # type: ignore[arg-type]
    if not path.exists() or not translator.load(str(path)):
        logging.getLogger("gelcam").warning("No translation for %r (%s); using English.", lang, path)
        return False
    app.installTranslator(translator)  # type: ignore[attr-defined]
    keep = [translator]
    # Qt's own texts (the Yes / No / OK buttons of message boxes, ...)
    import PySide6

    base = QTranslator(app)  # type: ignore[arg-type]
    for folder in (QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
                   str(Path(PySide6.__file__).resolve().parent / "translations")):
        if base.load(f"qtbase_{lang}", folder):
            app.installTranslator(base)  # type: ignore[attr-defined]
            keep.append(base)
            break
    app._gelcam_translators = keep  # type: ignore[attr-defined]  # keep them alive
    return True


# ----------------------------------------------------------------------------------------- self-test
def selftest(check_camera: bool = False, out: Callable[[str], None] = print) -> int:
    """Checks that a build is complete on this PC; exit code 0 when everything required works.

    Verifies the imports of the heavy native libraries, a window over the simulated camera, TIFF/PNG
    writing, the EDSDK DLL and (with `check_camera`) the connection to a real camera. It is what
    to run first on a new PC: `GelCam.exe --selftest [--camera]`.
    """
    failures: list[str] = []

    def step(name: str, fn: Callable[[], str | None], required: bool = True) -> None:
        try:
            detail = fn()
            out(f"OK    {name}" + (f": {detail}" if detail else ""))
        except Exception as exc:  # noqa: BLE001
            out(f"{'FAIL' if required else 'WARN'}  {name}: {exc}")
            if required:
                failures.append(name)

    out(f"GelCam {__version__}  |  Python {platform.python_version()}  |  {platform.platform()}  |  "
        f"frozen={is_frozen()}")
    out(f"data folder: {data_dir()}")

    def libs() -> str:
        import cv2
        import numpy
        import rawpy
        import tifffile
        from PIL import Image

        return (f"numpy {numpy.__version__}, opencv {cv2.__version__}, rawpy {rawpy.__version__}, "
                f"tifffile {tifffile.__version__}, Pillow {Image.__version__}")

    def tiff_png() -> str:
        import numpy as np
        import tifffile
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            arr = (np.arange(64 * 64, dtype=np.uint16) % 4096).reshape(64, 64)
            tifffile.imwrite(Path(tmp) / "a.tif", arr)
            if not (tifffile.imread(Path(tmp) / "a.tif") == arr).all():
                raise RuntimeError("TIFF round trip differs")
            Image.fromarray((arr >> 4).astype("uint8")).save(Path(tmp) / "a.png")
        return "16-bit TIFF and PNG round trip"

    def phase() -> str:
        import cv2
        import numpy as np

        rng = np.random.default_rng(0)
        a = rng.random((128, 128), dtype=np.float32)
        (dx, dy), _ = cv2.phaseCorrelate(a, np.roll(a, 3, axis=1))
        if abs(abs(dx) - 3) > 0.2:
            raise RuntimeError(f"phase correlation returned {dx:.2f}, expected 3")
        return f"phase correlation found a shift of {abs(dx):.2f} px (expected 3)"

    def window() -> str:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from .camera import MockCamera
        from .ui import theme
        from .ui.controller import CameraController
        from .ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        theme.apply(app)
        win = MainWindow(CameraController(lambda: MockCamera(seed=1)))
        win.show()
        for _ in range(20):
            app.processEvents()
        win.close()
        win.ctrl.shutdown()
        return f"Qt platform '{app.platformName()}', main window over the simulated camera"

    def edsdk_dll() -> str:
        from .camera.edsdk.binding import Edsdk, default_vendor_dir

        Edsdk()
        return f"loaded from {default_vendor_dir()}"

    def czech() -> str:
        from PySide6.QtCore import QTranslator

        path = translations_dir() / "gelcam_cs.qm"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found (the interface stays English)")
        tr = QTranslator()
        if not tr.load(str(path)) or tr.translate("MainWindow", "Connected") != "Připojeno":
            raise RuntimeError(f"{path} cannot be loaded")
        return f"loaded from {path}"

    step("libraries", libs)
    step("Czech translation", czech, required=False)
    step("TIFF / PNG writing", tiff_png)
    step("alignment (OpenCV)", phase)
    step("main window (simulation)", window)
    step("Canon EDSDK DLL", edsdk_dll, required=check_camera)

    if check_camera:
        def camera() -> str:
            from .camera.edsdk import EdsdkCamera

            cam = EdsdkCamera()
            info = cam.connect()
            try:
                return f"{info.model}, lens {cam.lens_info().name or 'not reported'}"
            finally:
                cam.disconnect()

        step("camera connection", camera)

    out("RESULT: " + ("all required checks passed" if not failures else "FAILED: " + ", ".join(failures)))
    return 1 if failures else 0
