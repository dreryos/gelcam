# GelCam

Windows application for photographing agarose gels with a Canon EOS 100D DSLR over USB: live view, a capture wizard, and physically sound processing (stacking, dark frame, flat field, color channel selection, binning) with linear 16-bit export for quantification.

Status: camera control via EDSDK verified on the 100D (live view, AF, RAW, connection recovery); the processing pipeline is in progress (RAW loading, channel selection).

## Running

```
uv sync
uv run python -m gelcam --mock      # without a camera (simulation)
uv run python -m gelcam             # Canon EOS 100D over EDSDK (Windows)
uv run pytest                       # testy
```

For a real camera, copy the 64-bit DLLs from the Canon EDSDK into `vendor/edsdk/Dll/` and the headers into `vendor/edsdk/Header/`, then run `uv run python tools/check_edsdk_constants.py` and `uv run python tools/edsdk_smoke.py`.

## Setup on another computer (Windows)

1. Install Git and `uv` (without administrator rights, `winget install astral-sh.uv` is enough; otherwise see https://docs.astral.sh/uv/).
2. `git clone https://github.com/dreryos/gelcam`, then run `uv sync` in the directory (downloads Python 3.12 x64 and the dependencies).
3. `uv run pytest` – the tests run without a camera (simulated). Tests that use real RAW files are skipped when the `testdata/` folder is absent.
4. **Canon EDSDK** (only needed for camera work): download it from the Canon Developer Programme (tested with version 13.21.10, `EDSDKv132110W`), copy the 64-bit `EDSDK_64/Dll/*.dll` into `vendor/edsdk/Dll/` and `EDSDK/Header/*.h` into `vendor/edsdk/Header/`, then run `uv run python tools/check_edsdk_constants.py` and `uv run python tools/edsdk_smoke.py`. The `vendor/` folder is never committed (Canon license).
5. Close EOS Utility, digiCamControl and similar programs before starting the application with the camera.
6. **Test images** (`testdata/`, CR2 from the 100D, about 2.6 GB) are not in git; see the agreed sharing method in `docs/GELCAM_PLAN.md`. Without them, development can proceed on synthetic data (`src/gelcam/testing/synthetic.py`) and `MockCamera`.

## Working on a system other than Windows (macOS, Linux)

UI and image processing can be worked on anywhere; only work with a real camera is tied to Windows.

- **Works everywhere:** the PySide6 UI and `uv run python -m gelcam --mock` (simulated camera `MockCamera`), the pipeline (`rawpy`, `numpy`, `tifffile`, `opencv-python-headless` have packages for macOS and Linux), the tests (`uv run pytest`) and synthetic data (`src/gelcam/testing/synthetic.py`). Tests that use real CR2 files are skipped when the `testdata/` folder is absent. On macOS, install `uv` e.g. with `brew install uv`.
- **Windows only:** the real camera (`EdsdkCamera` calls `EDSDK.dll` via `ctypes` and handles Windows messages), final verification of UI appearance and behavior (fonts, display scaling, window layout may differ), packaging with PyInstaller, and a test without administrator rights.
- **Practice:** build the UI on top of `MockCamera` (live view, histogram, focusing, connection errors must be covered by the simulation); anything that concerns the camera is verified on Windows with the 100D connected. Nothing in `ui/` or `acquisition/` may call EDSDK directly, only the `Camera` interface; otherwise the code will not run on a non-Windows system.

- Plan, architecture and decision history: [docs/GELCAM_PLAN.md](docs/GELCAM_PLAN.md)
- Context for Claude Code: [CLAUDE.md](CLAUDE.md)
- Guide to capturing test data: [docs/TESTOVACI_DATA.md](docs/TESTOVACI_DATA.md)

The Canon EDSDK is not part of the repository; obtain it through the Canon Developer Programme and place it in `vendor/edsdk/`.
