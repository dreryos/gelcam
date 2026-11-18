# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe: a one-folder build with a windowed GelCam.exe and a console GelCam-console.exe.

Build with `uv run python packaging/build.py` (it also adds the Canon EDSDK DLLs and writes the zip).
onedir, not onefile: a self-extracting exe triggers antivirus false alarms more often.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent

datas, binaries, hiddenimports = [], [], []
for package in ("rawpy",):  # native extension + its data files
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

translations = ROOT / "src" / "gelcam" / "translations"
if any(translations.glob("*.qm")):
    datas.append((str(translations), "translations"))
datas.append((str(ROOT / "packaging" / "README-LAB.txt"), "."))

# Not used by GelCam; keeping them out saves tens of megabytes.
excludes = [
    "tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest", "setuptools", "pkg_resources",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D", "PySide6.Qt3DCore",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtRemoteObjects",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSvg", "PySide6.QtSvgWidgets",
    "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtDesigner",
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="GelCam", console=False, upx=False)
console = EXE(pyz, a.scripts, [], exclude_binaries=True, name="GelCam-console", console=True, upx=False)
coll = COLLECT(gui, console, a.binaries, a.datas, name="GelCam", upx=False)
