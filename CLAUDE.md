# GelCam

Desktop application for Windows for photographing agarose gels (PCR) with a Canon EOS 100D DSLR over USB. Live view, a capture wizard and physically sound processing (stacking, dark frame, flat field, channel selection, binning) with linear 16-bit export.

The full plan, technical details and decision history: **`docs/GELCAM_PLAN.md`**. Before any major change, read the relevant chapter.

## Hardware

- Metal cabinet, Canon EOS 100D inserted from above, fixed orange filter, UV lamp at 70/100 % and white light.
- Zoom manually adjustable, **focus ring not reachable** → focusing by AF only (in the app via EDSDK: AF in live view + stepwise movement). The shutter release always runs without AF.
- Zoom and UV level are part of the calibration and metadata. Dark frame = lights off, cabinet closed, eyepiece covered.

## Status

- Phase: stages 0 and 1b (100D control via EDSDK) complete and verified on the camera; stage 2 (pipeline) in progress: `processing/raw_io.py`, `channel.py`. Next step `calib` (master dark/flat). Details and measured values in `docs/GELCAM_PLAN.md`; current checklist and next steps in **`STATUS.md`**.
- Test RAW sets (light frames, dark frames, flat fields) are in `testdata/` (not committed).

## Stack

- Python 3.12 **x64**, environment management with `uv`
- PySide6 (GUI), numpy, rawpy, tifffile, opencv-python-headless, Pillow
- Canon EDSDK via ctypes (`src/gelcam/camera/edsdk/`), DLLs and headers in `vendor/edsdk/`
- pytest, PyInstaller (onedir)

## Commands

- `uv sync` – install dependencies
- `uv run pytest` – tests
- `uv run python -m gelcam` – run the application (`--mock` without a camera)
- `uv run python tools/check_edsdk_constants.py` – check EDSDK constants against the headers
- `uv run python tools/edsdk_smoke.py [--capture]` – stage 0 diagnostics (Windows + 100D)

## Architecture in brief

`ui/` → `acquisition/` → `camera/` (interface `Camera`, implementations `MockCamera`, `EdsdkCamera`) and `processing/` → `storage/`. Neither the GUI nor acquisition control may call EDSDK directly; everything goes through the `Camera` interface.

## Working on multiple systems

- The UI, `acquisition/`, `processing/` and the tests are developed and run on Windows, macOS and Linux (`uv sync`, `uv run python -m gelcam --mock`, `uv run pytest`). For UI development without a camera, `MockCamera` is used; extend it when the UI needs further behavior (histogram, errors, loss of connection).
- Windows only: `EdsdkCamera` (EDSDK.dll via ctypes, message loop), work with the camera, final UI verification (fonts, DPI), PyInstaller. Code outside `camera/edsdk/` must not import EDSDK or anything from the Windows API.
- `vendor/edsdk/` and `testdata/` are added manually on a new computer (see README); they are not in git.

## Rules not to break

1. **Data integrity:** the original RAW files are never modified. `result.tif` contains only linear operations applied to the whole image. Brightness, contrast, gamma and inversion affect only the preview. Every processing step is written to `metadata.json`.
2. **No AI denoising.** Classical denoising only optionally and as a separate file.
3. **Work with RAW, not JPEG.** Channel selection from the CFA mosaic without demosaicing (EtBr/GelRed → R, SYBR → G).
4. **Set camera values only from the list of allowed values that the camera returns.** EDSDK does not validate values, and a wrong setting can lock up the camera (error 99).
5. **EDSDK only on one thread, with the Windows message loop.** The GUI communicates via a queue or Qt signals.
6. **No administrator rights:** write nothing to Program Files or the registry; settings go to `%APPDATA%\GelCam`. No dependencies that require installing drivers.
7. **Canon license:** never commit the contents of `vendor/edsdk/` or `testdata/`.
8. Code must be developable and testable without a connected camera (MockCamera, synthetic data in `src/gelcam/testing/synthetic.py`).

## Conventions

- **Everything in English**: code, identifiers, comments, documentation and the application interface. User-facing texts go through Qt `tr()` + `.ts`/`.qm` (Czech as a translation), no hard-coded strings.
- Type annotations, small pure functions in `processing/` (numpy arrays in and out), tests for every pipeline step.
- Add new findings and decisions to `docs/GELCAM_PLAN.md`.
