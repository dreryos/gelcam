# GelCam – plan, notes and history

Complete context for developing the GelCam application. It originated from a conversation of 29 Oct - 4 Nov 2026. The short version for Claude Code is in `CLAUDE.md` in the repository root.

---

## 1. What it is about

The laboratory photographs agarose gels from PCR with a **Canon EOS 100D** DSLR (for compatibility tests an **EOS 500D** was also available, but it will ultimately not be used). The official EOS Utility 2 on Windows crashes immediately on launch, and the available alternatives (digiCamControl, qDslrDashboard, Lightroom…) either lack a gel workflow, or are paid or complicated.

**GelCam** is a desktop application for Windows which:

- controls the 100D over USB (Canon EDSDK),
- has live view with a magnifier for focusing and a histogram,
- guides the operator through the process to obtain the best possible image of the gel,
- improves quality by physically sound methods: averaging of frames (stacking), dark frame subtraction, flat-field correction, colour channel selection, binning,
- exports a linear 16-bit TIFF suitable for quantification and archives the original RAW,
- runs as a portable folder without administrator rights.

---

## 2. Condensed history of the conversation

1. **EOS Utility 2 crashes on Windows** (100D, crash immediately on launch, still without camera connected). Probable causes: missing/broken .NET Framework 3.5 or a corrupted user config (`%LocalAppData%\\Canon_Inc`). Recommended clean reinstallation of EU2 (2.14.x) from the 100D support page. EU3 does not support this model.
2. **Open source tethering on Windows:** practically only **digiCamControl** (MIT, C#, uses Canon EDSDK underneath, supports 100D). Free, but not open source: **qDslrDashboard**. Other open source tools (gphoto2, Entangle, darktable tethering) run on Linux/macOS; on Windows only via WSL2 + usbipd (bastl). Paid: Smart Shooter 4, Breeze DSLR Remote Pro, Helicon Remote, Lightroom Classic, Capture One, ON1.
3. **Adjusting contrast and brightness during tethering:** either Picture Style in the camera (affects only JPEG and live view), or RAW adjustments after capture (Lightroom, Capture One, darktable). For gels it turned out that the quality of the data itself matters more than cosmetic adjustments.
4. **Decision to write a custom application.** Backend variants: (a) wrapper over digiCamControl (web server/CLI), (b) **direct Canon EDSDK – chosen**, (c) libgphoto2 via MSYS2 – rejected (requires replacing the USB driver via Zadig, which breaks EOS Utility and digiCamControl).
5. **digiCamControl uses the official EDSDK** (`EDSDK.dll`, `EdsImage.dll`). Its source code (C#, GitHub) is a good reference implementation (live view, events, message loop).
6. **100D vs 500D:** same EDSDK base (exposure, shutter release, download, live view). 500D is older (DIGIC 4, slow focusing in live view) and the newest EDSDK version may not support it. Rule: always read the allowed values from the camera at runtime. Development platform 100D, 500D for compatibility testing.
7. **Techniques for better gel images** (core of the application): stacking (noise falls with √N), dark frame, flat field, low ISO and longer exposure, RAW instead of JPEG (linear data), channel selection by dye (EtBr/GelRed → R, SYBR → G), 2×2 binning, saturation indication from RAW, 16-bit TIFF and metadata. **Do not use AI denoising** (it may suppress faint bands or create structure that is not there; a problem for quantification and journal rules). Hardware helps more than software: emission filter (orange for EtBr, yellow for SYBR) and light-tight enclosure.
8. **Application plan created** (document "GelCam – application plan" on claude.ai; its content was taken over into this file).
9. **Development requires** a Windows PC, and the camera itself only for stage 0 and integration tests. EDSDK exists for macOS too, but final verification must take place on Windows. Do not use Windows in a VM on Apple Silicon for testing the SDK.
10. **Deployment without administrator:** yes – PyInstaller (onedir), built-in WPD/PTP driver, bundled VC++ runtime, settings in `%APPDATA%`. Risks: AppLocker/IT policies, SmartScreen warning.
11. **Replacement of the DSLR** (future): a monochrome astro camera is better for gels (no Bayer mask, cooling, electronic shutter). See chapter 12.
12. **Focusing via EDSDK:** only in live view and relatively in steps (`kEdsCameraCommand_DriveLensEvf`, Near/Far 1–3). The lens must be in AF position; absolute position cannot be read. Originally planned for v2.
13. **Similar projects:** no ready-made equivalent exists. Useful: **N.I.N.A.** (open source astro capture, Windows, native Canon/ZWO/QHY support) + **Siril** (open source calibration and stacking). Python wrappers for EDSDK: `edsdk-python` (Jiloc), `pyedsdk` (PyPI). Gel projects are mainly hardware-based (Raspberry Pi, openIVIS) without calibration and stacking.
14. **No need to wait for EDSDK approval.** Pipeline, camera interface, MockCamera, GUI and wizard can be developed immediately on test data. Windows is needed only for EDSDK, packaging and deployment testing.
15. **Specified setup (4 Nov):** metal cabinet with camera from above, focusing ring unreachable (focusing AF only → software focusing belongs in v1), manually changeable zoom, UV 70/100 % and white light, fixed orange filter. Guide for test data: `docs/TESTOVACI_DATA.md`.

---

## 3. Hardware and environment

### Actual setup (specified 4 Nov 2026)

- **Metal cabinet** (darkroom), camera is **inserted from above** with the lens facing down.
- **Zoom** on the lens can be changed manually, **focusing ring is not reachable** → focusing is done exclusively by autofocus (from the camera or from the application via EDSDK).
- **Illumination:** UV lamp with two levels (**70 % and 100 %**) and **white light**, switched **by hand on the cabinet** — not controllable from software (confirmed 10 Nov 2026).
- **Emission filter:** fixed **orange** filter in front of the lens.

### Canon EOS 100D – parameters important for GelCam (from Canon specification)

| Parameter | Value | Impact |
| --- | --- | --- |
| Sensor | CMOS APS-C 22.3 × 14.9 mm, 18 Mpx, Bayer (primary colours) | channel selection from mosaic |
| RAW | 14-bit CR2, 5184 × 3456 px | single channel (R) = 2592 × 1728 px |
| Times | 30 s – 1/4000 s, Bulb | above 30 s only Bulb (in v1 avoid it, prefer more frames) |
| ISO | 100–12800 (H expansion 25600) | for gels ISO 100 |
| Shutter | focal-plane with electronic first curtain, quiet shooting | fewer vibrations in live view |
| Live view | Hybrid CMOS AF II, FlexiZone-Single, magnifier 5×/10×, histogram, grid | focusing and checking from the application |
| Interface | USB 2.0 Hi-Speed (mini-USB) | RAW download ~1–2 s |
| Power | LP-E12; mains kit **ACK-E15** | always mains adapter in the box |
| Power saving | auto power-off after 30 s – 15 min | application must extend it (EDSDK `ExtendShutDownTimer`) or set the longest |
| Viewfinder | eyepiece shutter is only on a strap | eyepiece points out of cabinet → tape/cover (light leak during long exposures) |

### Environment

| Element | Requirement | Note |
| --- | --- | --- |
| Camera | Canon EOS 100D, mode M, RAW (CR2) | 500D for compatibility test; mini-USB cable |
| Power | ACK-E15 mains adapter | live view and battery series drain quickly |
| Card | card in camera, or enable "Release shutter without card" in the menu | otherwise camera refuses to expose |
| Mounting | fixed in cabinet | flat field applies only with the same geometry, zoom and focus |
| Light-tightness | metal cabinet; covered eyepiece | |
| Emission filter | fixed orange | ideal for EtBr/GelRed; for SYBR (emission ~520 nm) the orange filter cuts off much of it – verify on data |
| PC | Windows 10/11 x64, USB 2.0+ | |
| SDK | Canon EDSDK (registration in Canon Developer Programme, approval takes several days) | version supporting 100D (and ideally 500D) |

### Consequences of the setup for the application

- **Focusing must be possible in the application already in v1:** starting AF in live view (`kEdsCameraCommand_DoEvfAf`, FlexiZone-Single on the marker band) and fine adjustment in steps (`DriveLensEvf`) based on sharpness measure. Best focused **under white light** (high contrast), then switch to UV.
- **Shutter release without AF:** during shooting the camera must not refocus (EDSDK release with NonAF variant; for manual focusing move AF to the * button in custom functions).
- **Focus is verified at the start of each session** and after every zoom change (with a zoom lens focus shifts when focal length changes; with STM lenses focus may drift after the camera is switched off).
- **Zoom is part of calibration:** flat is valid only for the given zoom position. Recommendation: choose one position, mark it on the lens, and treat a zoom change as a new calibration.
- **UV level (70/100 %) is part of profile and metadata;** flats are taken for the level in use.
- **White light** serves for focusing, gel alignment and an optional documentation image (well positions). It is not used as flat for fluorescence (different spectrum and distribution).
- **Darks without cap:** lens is inside the cabinet, so dark = lights off, cabinet closed, eyepiece covered.
- **Channel selection is verified on data:** for EtBr behind orange filter R; for SYBR measure SNR in R and G channel and set profile accordingly.

---

## 4. Architecture

Five layers. All communication with the camera goes through a single interface, so the camera can be replaced by a simulation and later by a mono camera.

```
UI (PySide6)              main window, wizard, profiles
        │
Acquisition               live view loop, series, calibration, exposure proposal
        │                         │
Camera interface           Processing
  EdsdkCamera (EDSDK)        rawpy + numpy: dark, flat, stacking,
  MockCamera (files)         channel selection, binning, TIFF export
  [AsiCamera – budoucnost]        │
        │                   Storage
Camera over USB              gel folder, calibration library, profiles
```

### Technologies

- Python 3.12 **x64**, GUI in **PySide6** (Qt 6).
- Canon EDSDK via `ctypes` (own thin wrapper), possibly `edsdk-python` / `pyedsdk` as inspiration or base.
- `rawpy` (LibRaw) – reading CR2, `numpy` – computations, `tifffile` – 16-bit export, `opencv-python-headless` – alignment (phase correlation), `Pillow` – previews.
- `pytest` – tests, `PyInstaller` – packaging (onedir).
- Environment management: `uv` (installation without administrator rights), or venv + pip.
- **Another language was considered and rejected (10 Nov 2026):** see "Performance on the
  target PC". Of the 4.9 ms live-view frame and the 1.6 s eight-frame stack, almost everything
  already runs inside compiled C/C++ — libjpeg for the EVF frame, numpy for the LUT, histogram
  and sigma clipping, OpenCV for sharpness and phase correlation, LibRaw for the CR2. The
  Python part is the glue between those calls and costs microseconds, so Rust, C++ or C# would
  make the same library calls at the same speed; LibRaw needs 190 ms per frame in any language.
  What a rewrite would genuinely buy is a smaller baseline (156 MB, or 108 MB with lazy
  imports, against roughly 60–90 MB for C# or 30–60 MB for Rust) and a much smaller, faster
  starting bundle (PyInstaller onedir is hundreds of MB against ~15 MB for a Rust binary),
  neither of which outweighs discarding the EDSDK layer that is already verified on the real
  camera. C# would additionally have digiCamControl as a reference for EDSDK marshalling —
  the one real argument, and the reason the option stayed open until stage 1b was finished.

### Proposed repository structure

```
gelcam/
  CLAUDE.md
  pyproject.toml
  docs/GELCAM_PLAN.md
  src/gelcam/
    camera/
      base.py            # Protocol Camera + data types
      mock.py            # MockCamera – replays files from the test set
      edsdk/             # EdsdkCamera, ctypes binding, thread with message loop
    acquisition/
      live_view.py       # EVF frame loop
      series.py          # series of N frames, incremental download, resume
      exposure.py        # exposure proposal from a test RAW
      calibration.py     # taking darks and flats
    processing/
      raw_io.py          # CR2 loading, black/white level, CFA pattern
      channel.py         # channel selection from the mosaic, no demosaicing
      calib.py           # master dark (median), master flat, application
      align.py           # shift detection, alignment
      stack.py           # mean with sigma clipping
      binning.py
      export.py          # TIFF + preview PNG + metadata.json
      pipeline.py        # step chaining, processing history
    storage/
      layout.py          # gel folder structure
      metadata.py
      profiles.py        # profily barviv (TOML)
    ui/
      main_window.py
      wizard/            # 7 wizard steps
  profiles/              # etbr.toml, gelred.toml, sybr.toml
  tests/
    test_*.py            # tests; synthetic gels from src/gelcam/testing/synthetic.py
  tools/                 # check_edsdk_constants.py, edsdk_smoke.py (etapa 0)
  vendor/edsdk/          # Canon DLLs and headers – DO NOT COMMIT (.gitignore)
  testdata/              # captured sets – DO NOT COMMIT
```

### Camera interface (proposal)

```python
from typing import Protocol
from pathlib import Path
import numpy as np

class Camera(Protocol):
    def connect(self) -> "CameraInfo": ...            # model, serial no., power state
    def disconnect(self) -> None: ...
    def allowed_values(self, prop: "Prop") -> list: ...  # ALWAYS read from the camera
    def get(self, prop: "Prop"): ...
    def set(self, prop: "Prop", value) -> None: ...   # jen hodnoty z allowed_values()
    def start_live_view(self) -> None: ...
    def live_view_frame(self) -> np.ndarray: ...      # decoded JPEG from EVF
    def set_live_view_zoom(self, factor: int, x: int, y: int) -> None: ...
    def stop_live_view(self) -> None: ...
    def capture(self, dest_dir: Path) -> Path: ...    # shoots without AF and downloads RAW
    def drive_focus(self, step: int) -> None: ...     # -3..+3, jen v live view (v2)
```

`Prop` is an enumeration: `ISO`, `TV` (time), `AV` (aperture), `IMAGE_QUALITY`, `AE_MODE`… EDSDK value codes (e.g. ISO 100 = `0x48`) are converted only by the `camera/edsdk/` layer.

---

## 5. Functions

### Main screen

- **Connection:** camera detection, model, power status, understandable errors, automatic recovery after sleep or disconnection.
- **Live view:** JPEG stream from EVF, 5×/10× magnifier for manual focusing, grid, inverted display.
- **Histogram and saturation:** live histogram of selected channel and highlighting of clipping. From live view it is only an estimate; exact measurement is done on RAW.
- **Exposure:** time, aperture, ISO; allowed values are read from the camera. Bulb (> 30 s) only when needed.
- **Single frame:** quick capture without processing.

### Live View window (main screen, designed 10 Nov 2026)

Mockups: `design/export/lv1_framing.png` (framing under white light) and
`design/export/lv2_focusing.png` (focusing at 10× under UV); script `design/design_liveview.py`.
Window 1280 × 800, preview pane 780 × 520, right column 300 px.

**Layout.** Top bar: application name, camera state as chips (model, power, image quality, UV
level) and the **New gel image…** button that enters the wizard. Below it, on the left, the
view toolbar (grid, invert, clipping overlay, zoom 1×/5×/10×, display gain) and the live view
pane; under the pane a wide histogram with the channel selector. Right column: Camera,
Exposure and Single frame cards in framing mode, Focus and Exposure in focusing mode. Status
bar at the bottom: connection, frame rate, lighting, zoom position, link to the log.

**What the operator does here.** Frame the gel, focus, set exposure and take single frames.
The wizard is the guided path for an actual gel; this window is the free one and is also where
a session starts (connection, focus check after a zoom change).

**Estimate vs measurement — the distinction must be visible.** The live view stream is an 8-bit
JPEG from EVF with a display gamma, so its histogram and clipping overlay are indicative only.
The authoritative numbers come from a captured RAW: brightest region in ADU, share of saturated
pixels, white level of that frame. The Single frame card therefore shows both the file and the
measured values, labelled as measured on RAW.

**Magnification is done in the camera.** `set_live_view_zoom` switches the EVF stream itself to
a 5× or 10× crop, so the pane shows the magnified region, not an inset. A navigator thumbnail in
the corner shows which part of the frame is displayed; step 3 of the wizard uses the same
idiom.

**Display adjustment (preview only).** Under UV the scene is dim and a faint band is barely
distinguishable from the background in the raw preview, so the window carries a display
transfer function: **black point, white point and gamma**, with the black and white handles
sitting directly on the histogram under the preview, plus **Auto stretch**, **Reset** and
**Invert**. It is a lookup table applied to the 8-bit preview frame — the EVF stream, the
captured CR2 and `result.tif` are untouched, and the panel is labelled that way. The same
control serves the review step of the wizard, and the chosen settings are what `preview.png`
is written with and what goes into `metadata.json`; they never alter the quantitative data.
Auto stretch derives the points from the current frame statistics (the astro-software screen
transfer function, as in Siril or N.I.N.A.).

**Focusing.** Sharpness is the variance of the Laplacian computed on the magnified EVF frame,
shown as a large number with a sparkline of recent values, so the operator sees whether a step
helped. `Run autofocus` is the coarse move (measured: 5.5 → 53.1), the six fine steps are
`DriveLensEvf` Near/Far 1–3, and `Auto fine-focus` walks the steps and keeps the maximum.
Focusing is done under white light; the shutter never refocuses.

**Exposure.** ISO, shutter and aperture come from `allowed_values()` only. A value outside what
gels need is flagged rather than blocked (e.g. ISO 800 — the state the camera was actually found
in during stage 0).

**Live view and heat.** Live view warms the sensor, which raises the dark current of warm pixels
(measured: 2035 warm pixels after 1.5 h of work against 421 on a cold sensor at twice the
exposure time). The window turns live view off before a series and the status bar says so.

**How the app learns the UV level.** It cannot sense it — the lamp has no feedback to the
camera or the PC, and the image alone is not reliable evidence (a weak gel under UV 100 % and a
strong one under 70 % look alike). The level is therefore **declared by the operator**: the
radio buttons in step 1 of the wizard, the `Which light is on?` row in step 2, and the
clickable light chip in the Live View top bar all write the same session state, which goes into
`metadata.json` and decides which flat field applies. A cheap cross-check is possible later and
worth having: UV 70 % gives 0.80–0.81× the signal of UV 100 % on the same scene (measured), so
once a test exposure exists the app can compare the background level against the flat of the
declared level and warn when the two disagree by much more than that factor. It stays a
warning, never an automatic correction.

**Lighting is manual** (confirmed 10 Nov 2026). The lamp cannot be switched from software, so
the UI only shows the current level as a state — in the top bar of the Live View window and as
a line in step 2 of the wizard — and the wizard tells the operator when to switch by hand.
The level is still recorded in metadata and decides which flat field applies.

### Interface language

The interface is **in English**; texts go through Qt `tr()` and translations are supplied as `.ts`/`.qm`;
Czech is the second language. The language is selected in application settings, not in the wizard.

### Wizard (7 steps)

Mockup of all seven steps is in `design/` (document `gelcam-ui.figcraft`, exports
`design/export/*.png`). The design is scripted — `design/design_wizard.py` builds the whole set via
`build_all(mcp, lang="en"|"cs")`, so changing style or language is a rebuild, not redrawing. The content of individual steps
corresponds to this list:


1. **Profile and gel description:** dye (EtBr, GelRed, SYBR…), UV level (70/100 %), name, note. The profile determines the channel and default exposure.
2. **Scene check:** white light, live view with grid; checklist (closed cabinet, covered eyepiece, gel in centre, zoom at marked position).
3. **Focusing:** under white light AF in live view on the marker band, then fine adjustment in steps based on sharpness; operator confirms on 10× magnifier. Then switch to UV (selected level 70/100 %).
4. **Test exposure:** one RAW; application measures brightest area in selected channel and proposes a time so it is at 70–80 % of range without saturation. Above the limit (e.g. 30 s) rather take more frames.
5. **Calibration:** dark frames automatically (lights off, cabinet closed, same time and ISO). Flat field once in a while for the given arrangement; warning when it is older than the limit.
6. **Series:** N frames (default 8, option 4–32), progress, estimate of SNR gain (√N), check of saturation and shift.
7. **Check and export:** result next to single frame for noise comparison, saturation map, inversion; export with one button.

### Error states and the remaining screens (designed 10 Nov 2026)

Three tiers, and which one applies is decided by what the operator can do about it:

| Tier | When | Example |
| --- | --- | --- |
| Full-area state | the camera is not usable at all, so nothing else on screen means anything | no camera found; connection lost |
| Inline banner in the step | a problem that does not stop the work | saturated marker; flat field older than 30 days; zoom off the mark |
| Dialog | a decision that has to be made now, with the work paused | series interrupted at frame 5 of 8 |

Everything else — progress, retries, what the application just did — goes to the status bar and
the log, never into a popup.

Mockups in `design/export/`, built by `design/design_errors.py`:

- `e1_no_camera` — EDSDK reports nothing. Lists the blocking applications found running
  (`edsdk/blockers.py`), names the one holding the camera, and gives the four things worth
  checking. Retries every 5 s by itself.
- `e2_connection_lost` — the stream dims and a card counts the reconnect attempt, stating that
  ISO, shutter and aperture will be restored. The measured reconnect time (9 s after a cable
  pull) is what the wording promises.
- `e3_series_interrupted` — the only dialog in the design. Resume from frame 6, start over, or
  stack the five frames already downloaded, with what the shortfall costs in signal-to-noise
  (x2.2 instead of x2.8) so the choice is informed.
- `e4_saturated` — the marker sits at the white level and cannot be quantified. Proposes a
  shorter exposure but lets the operator continue if only the faint bands matter.
- `e5_af_failed` — autofocus found no contrast under UV; switch to white light, focus, switch
  back.
- `e6_flat_library` — the picker behind "Pick from library" in step 5: date, UV level, zoom,
  exposure, frame count and age with a colour for staleness.
- `e7_export_done` — what was written and what each file is for, with the reminder that
  `result.tif` is the file to quantify and `preview.png` carries the display settings.
- `s1_settings` — language, root folder, defaults for a new gel, dye profile table.

**Deliberately not designed:** disk-full and write errors (the inline banner pattern covers
them), and the first-run state before any calibration exists.

### Calibration capture, dye profiles and log (designed 10 Nov 2026)

Tool windows opened from step 5, Settings and the status bar. They share one shell (header,
body, footer with actions), built by `design/design_tools.py`; exports in `design/export/`.

- `c1_flat_capture` — taking a new flat: arrangement it will be valid for (zoom, UV level,
  target, exposure — same as the gels), the last flat with centre level, corner falloff and
  saturation, then progress of 16 flats followed by 16 darks for the flat. The flat is divided
  out, so the target is only "centre at 50–80 %, nothing saturated", not a specific level.
- `c2_dark_frames` — the interstitial after a series: turn off all light, progress, and a check
  of the last dark (mean above bias, noise, hot pixels, light leak). Explains why darks are
  taken now rather than from a library (hot pixels depend on sensor temperature, measured
  4 Nov). "Skip, use stored darks" stays available but is not the default.
- `p1_dye_profiles` — list of profiles and an editor: name, channel R/G, emission filter, UV
  level, start exposure (dropdowns filled only from values the camera reports), frames, note.
  Editing a profile never changes images already taken; `metadata.json` keeps the profile used.
- `l1_log_about` — the log behind the status-bar link: level filter, search, one line per
  event; next to it version, EDSDK and Python versions, camera, log folder
  (`%APPDATA%\GelCam\logs`, one file per day, 30 days) and "Copy for support".

The page was built by `figcraft-cli` without an MCP host: `design/record_cli.py build_tools`
records the builder as a `node.create` script, `figcraft-cli run --in … --out …` applies it.


### Dye profiles (default)

| Dye | Channel | Filter |
| --- | --- | --- |
| EtBr | R | orange |
| GelRed | R | orange |
| SYBR Safe / SYBR Green / Midori Green | G (both G pixels) | yellow / amber |

---

## 6. Processing pipeline

All steps up to the result are linear and work with non-demosaiced RAW data.

```
Light RAW ×N → − master dark → ÷ normalised flat → channel selection
  → alignment (only when shift > 0.5 px) → mean with sigma clipping
  → binning 2×2 (optional) → result.tif (16-bit, linear)
                                   ╰┄→ optional denoise → separate file
```

Formula:

```
R = mean_σ( (L_i − D) / F̂ ),    F̂ = (F − D_F) / mean(F − D_F)
```

- `L_i` light frames, `D` master dark (median of 8–16 darks with the same time, ISO and similar temperature), `F` master flat, `D_F` dark for the flat (or bias).
- **Black level:** dark includes the black level, so `L − D` removes it. For the flat, `D_F` must be subtracted (or at least the black level from `raw.black_level_per_channel`), otherwise normalization will be distorted.
- **Saturation:** pixels ≥ `raw.white_level` (or close) are flagged already in the light frames, before subtraction; a saturated band cannot be quantified.
- **Channel selection:** `raw.raw_image_visible` + `raw.raw_colors_visible` (CFA colour indices). For R take R pixels, for G both G pixels (average 2×2 cell → half resolution). No interpolation.
- **Sigma clipping:** e.g. 3σ along the frame axis, iteratively; removes flashes, cosmic rays and one-off shifts.
- **Alignment:** `cv2.phaseCorrelate` on the channel; below 0.5 px no resampling.
- **Denoising:** median or non-local means, default off, always only as a separate file. **No AI denoising.**

### Correctness checks (tests)

Synthetic gel: background + Gaussian bands with known intensity + Poisson noise + readout noise + hot pixels + vignetting. The test verifies that:

- background noise after stacking N frames drops roughly √N×,
- the ratio of band intensities is preserved (linearity) within tolerance,
- hot pixels disappear after dark subtraction,
- vignetting disappears after flat-field correction.

---

## 7. Data integrity, storage and export

**Rules**

- The original RAW is never modified.
- Quantification output contains only linear operations applied to the whole image (subtraction, division by flat, averaging, binning).
- Brightness, contrast, gamma and inversion change only the preview, never the data in the TIFF.
- Every processing step is written to `metadata.json`.

**Structure of a gel folder**

```
2026-10-29_PCR-kontrola-primeru/
  raw/            original CR2 (light frames)
  calib/          dark frames, reference to the flat used
  result.tif      16-bit, linear, single channel
  preview.png     8-bit preview with the chosen display settings
  metadata.json   exposure, ISO, frame count, profile, processing steps, app version
```

- Flats are stored separately in the calibration library (date, description of the arrangement).
- The root folder is configurable (local or network drive).

---

## 8. Deployment without administrator rights

- **Package:** PyInstaller **onedir** (not onefile – more frequent antivirus false alarms). Contains Python, PySide6, numpy, rawpy and the EDSDK DLLs.
- **Camera driver:** not needed; Windows uses the built-in WPD/PTP and EDSDK works through it.
- **Visual C++ runtime:** bundle the required DLLs in the application folder.
- **Settings and profiles:** in the application folder or `%APPDATA%\\GelCam`, never in Program Files.
- **First launch:** SmartScreen "Unknown publisher" can be confirmed once.
- **Test:** clean user account without administrator rights and a PC without VC++ runtime.
- **Check in advance:** whether IT blocks running unsigned applications from user folders or USB (AppLocker, GPO).

---

### Performance on the target PC (measured 10 Nov 2026)

The lab PC is a dual-core below 2 GHz with **2 GB RAM** on Windows 10 x64. The numbers below
were measured single-threaded on a development machine over the real test sets
(`tools/bench.py` reproduces them on any machine; run it on the lab PC before trusting the
scaling). A 2 GHz Core 2 / early i3 / Atom-class core is roughly 4–6× slower per thread than
the machine these came from.

| Operation | Measured | Expected on the lab PC |
| --- | --- | --- |
| Live view: JPEG decode + display LUT + histogram + sharpness | 4.9 ms per frame | 20–30 ms → 33–50 fps |
| Sharpness (variance of Laplacian), full 960 × 640 | 2.6 ms | 10–16 ms |
| Sharpness on half resolution | 0.2 ms | ~1 ms |
| CR2 read + R channel extraction | 190 ms per frame | 0.8–1.1 s per frame |
| 3σ clip + mean over 8 frames (4.5 Mpx) | 0.09 s | 0.4–0.6 s |
| Whole 8-frame stack | 1.6 s | 7–10 s |
| Phase correlation 512 × 512 | 2.8 ms | 10–17 ms |

**The CPU is not the problem; memory is.** The camera delivers ~16.5 fps, so even at 4–6× slower
the live view loop has headroom. A series of 8 frames plus 16 darks will take on the order of
half a minute, which is acceptable next to the exposure time itself.

Baseline footprint with the window open: **156 MB** (numpy 27, rawpy +1, PySide6 +42,
opencv +38, tifffile +11). On Windows expect 180–220 MB. Of a 2 GB machine, Windows 10 x64
leaves roughly 700–1000 MB, so the pipeline must stay inside a few hundred MB.

Rules that follow, to be respected in `processing/`:

1. **Never hold all frames in RAM.** Holding 8 channels as one array peaked at **824 MB** —
   that machine would swap. Read each CR2 once, write the extracted channel into a
   `numpy.memmap` on disk (145 MB for 8 frames), then stack in horizontal tiles: measured peak
   **374 MB** bare, **460–523 MB** with OpenCV and Pillow also loaded, at the same 1.6 s.
   Measured breakdown of the 374 MB: 30 MB at start, +79 MB that LibRaw leaves resident after
   eight reads even when nothing is kept, +148 MB of mapped file pages (reclaimable — the OS
   drops them under pressure), +117 MB of tile buffers at 16 tiles. So this is a saving of
   roughly 300–450 MB, not a return to the baseline; it should fit a 2 GB machine but must be
   confirmed there with `tools/bench.py`. More tiles and releasing the LibRaw buffer promptly
   are the levers if it does not. The same structure is what makes N = 32 possible at all,
   which would be 580 MB held in RAM.
2. **`float32` everywhere**, never let numpy promote to `float64`; it doubles every buffer.
3. **Import `cv2` and `tifffile` lazily** — measured: the window opens at **108 MB** instead of
   156 MB when neither is imported at startup, and neither is needed before alignment or
   export. Phase correlation over numpy FFT would remove the OpenCV dependency altogether;
   worth measuring.
4. **Decouple the overlays from the frame rate.** Decode and LUT run per frame; the histogram
   and the sharpness measure run on every second or fourth frame and on half-resolution data
   (13× cheaper and precise enough for finding a focus maximum).
5. **Live view off during a series** — already required because of sensor heating, and it also
   frees the CPU for downloading and writing frames.
6. **Trim the PyInstaller bundle**: exclude QtWebEngine, QtQuick, Qt3D and the other unused Qt
   modules. On an HDD this is the difference between a few seconds and half a minute of startup.

If the machine turns out to be too slow anyway, the fallback is not a rewrite: capture and
processing are separate, so the series can be shot on the lab PC and stacked elsewhere.

## 9. Technical risks

| Risk | Solution |
| --- | --- |
| EDSDK events require a Windows message loop in the correct thread | all camera communication in one dedicated thread with a message pump (or in the main Qt thread); GUI talks to it via queue/signals; inspiration in digiCamControl |
| EDSDK does not check validity of set values – a wrong value can block the camera (error 99; a damaged 50D case reported) | set **only** values from `allowed_values()`, do not touch settings outside the necessary range, test carefully |
| The latest EDSDK may not support 100D/500D | verify in stage 0; use the version with which the cameras work in digiCamControl |
| EDSDK licence | do not commit DLLs or headers to git; verify the terms at registration |
| 32/64 bit | 64-bit Python + 64-bit EDSDK, check at start |
| Camera sleep / battery drain during a series | disable auto power off, mains adapter, resume the series from the last downloaded frame |
| Sensor heating during live view | turn live view off before the series; take darks right after the series |
| Shift of gel or camera during a series | shift detection, alignment or warning |
| EOS Utility or digiCamControl holds the camera | check at start, understandable message "close the other application that uses the camera" |
| Shutter wear | reasonable default N, frame counter |
| Focusing ring unreachable, AF fails for weak fluorescence | focus under white light, software fine adjustment in steps, shutter release without AF, sharpness check at start of session |
| Focus drifts after a zoom change or after the camera is switched off | refocus after each zoom change and at the start of the session; hold zoom at the marked position |
| Light through the eyepiece during a long exposure | cover eyepiece; warning in the wizard |

---

## 10. Development stages

Total approximately 4–6 weeks of focused work; estimates are indicative.

**Status 4 Nov 2026 (stage 0 without capture done, see results below):** access to Canon EDSDK is approved. The order therefore changes: immediately after preparation **stage 0 and 1b (camera control)** go, and the pipeline (stage 2) runs in parallel on test data. Project skeleton, `Camera` interface, `MockCamera`, EDSDK layer (`src/gelcam/camera/edsdk/`), stage 0 diagnostic script (`tools/edsdk_smoke.py`), constants check against headers (`tools/check_edsdk_constants.py`) and basic window are set up; they await the first run on Windows with the camera.

| Stage | Content | Done when | Estimate |
| --- | --- | --- | --- |
| P. Preparation | repo, `uv`, structure, CI tests; capturing test sets; ~~EDSDK application~~ (approved 4 Nov) | repo runs, test data available | 1 day |
| 2. Pipeline | `processing/` + CLI over stored RAW, synthetic tests | synthetic test confirms SNR gain ≈ √N and linearity | 3–5 days |
| 1a. GUI over simulation | `Camera` interface, `MockCamera`, main window, live view, histogram | GUI runs without camera | 3–4 days |
| 0. EDSDK verification | script: connect, read allowed values, set time and ISO, take picture, download RAW, one live view frame | works with 100D (and 500D) | 1–2 days |
| 1b. EdsdkCamera | implementation of the interface over EDSDK, thread with message loop, reconnection, extending power-off timer, **AF in live view and step focus adjustment** | main screen works with a real 100D and can focus | 4–6 days |
| 3. Wizard | 7 steps, exposure proposal, automatic darks, series | operator without instructions captures a processed image | 5 days |
| 4. Profiles and export | dye profiles, flat library, metadata, folder structure | output passes integrity rules | 3–5 days |
| 5. Pilot | tests on real gels, PyInstaller package, test without admin | one week of operation without blocking error | 1–2 weeks ongoing |

### Test data to capture right away (via digiCamControl, RAW)

- 16 light frames of one gel (same time, ISO 100–200, live view off),
- 16 darks with the same time and ISO (transilluminator off, or cap),
- 8 flats (uniformly lit board or empty gel with dye, same geometry) + 8 darks for the flats,
- 1 set with a deliberately saturated marker (saturation detection test),
- optionally 1 set with a small shift of the gel (alignment test),
- record dye, filter, time, ISO, aperture, lens and distance.

### Results of stage 0 (4 Nov 2026, Windows 11, Canon EOS 100D)

- **SDK:** Canon EDSDK **13.21.10** (EDSDKv132110W, released 3 Mar 2026), 64-bit `EDSDK_64/Dll` used. The 100D is not explicitly listed in the release notes, yet it works.
- `uv sync` and `uv run pytest`: 45 tests passed.
- `check_edsdk_constants.py`: 62 constants checked. **Fixed 2 incorrect error codes:** `EDS_ERR_TAKE_PICTURE_NO_CARD_NG` 0x8D07 → **0x8D06**, `EDS_ERR_TAKE_PICTURE_CARD_PROTECT_NG` 0x8D0B → **0x8D08**. The "MISSING\" messages for `kEdsAccess_ReadWrite`, `kEdsFileCreateDisposition_CreateAlways`, `kEdsSaveTo_Both` are false alarms (implicit enum values, verified manually: 2, 1, 3).
- `edsdk_smoke.py` without `--capture`: **10/10 steps**. Connection OK (serial no. (hidden)), property reading OK (battery 80 %, mode M), allowed values loaded (ISO 100–12800 + Auto, times Bulb–1/4000, apertures f/5.6–f/36), live view frame 960×640 at ~16.5 fps, live view shutdown OK.
- Camera state during the test: ISO 800, 8\", f/8. For gels set ISO 100.
- `edsdk_smoke.py --capture`: **11/11 steps.** Capture and download of RAW (`IMG_0001.CR2`, ~24 MB) works. The first attempt ended with JPEG, because the camera had JPEG quality set in the menu: **the application does not yet set image quality** (`Prop.IMAGE_QUALITY` is missing); add reading/setting from the allowed values list in stage 1b.
- **Remaining:** see stage 1b results below.

### Results of stage 1b (4 Nov 2026, EDSDK layer, Canon EOS 100D)

- **`Prop.IMAGE_QUALITY`:** reading and setting only from values the camera returns (`EdsGetPropertyDesc`). The 100D offers JPEG variants, RAW+JPEG (0x640013) and RAW (0x64FF0F); M-RAW/S-RAW are not offered. `ensure_raw_quality(camera)` selects RAW without JPEG at full size and `capture()` calls it itself, so the operator does not have to watch the camera menu. Verified on the camera: after switching to JPEG, RAW was returned when shooting. On connection a warning is added if the camera does not save RAW.
- **Reconnection:** `EdsdkCamera.reconnect()` (closes the connection, tries to establish a new one and returns the last set ISO, time and aperture). **Verified on an actual disconnection:** pulling and reconnecting the USB cable and switching the camera off/on (`tools/edsdk_reconnect_test.py`); loss of connection is detected within ~2 s and the connection is restored ~9 s after disconnection. The test revealed a bug: after a failed connection the SDK remained initialized and every further attempt ended with "EDSDK initialization: 0x2\"; fixed by cleanup (`EdsTerminateSDK`) on failure of `_connect`. Camera sleep (auto power off) not yet tested.
- **Blocking applications:** before connecting, the code searches for running EOS Utility, digiCamControl, qDslrDashboard, Lightroom, Capture One, N.I.N.A. (`edsdk/blockers.py`). On a "camera not found/busy" error their names are added to the message, otherwise only to `warnings`.
- **Already implemented before and now verified without error on 100D:** magnifier 5×/1×, `DoEvfAf` (autofocus), `DriveLensEvf` (Near/Far steps), shutter release without AF (`Completely_NonAF`), extension of the power-off timer (every 60 s + on `WillSoonShutDown`). `edsdk_smoke.py --focus --capture`: 19/19 steps.
- **Focusing verified (4 Nov 2026, second attempt, contrasting scene with comparison comb):** from strong defocus, **AF** (`DoEvfAf`) gave a sharp image (sharpness measure 5.5 → 53, visually confirmed on the saved live view frame). Individual `DriveLensEvf` steps Near3/Far3 change sharpness smoothly and by small amounts (measure 5.5–8.9 over 12 steps), so they are suitable only for fine adjustment, not coarse setting; coarse focusing is done by AF. The first attempt on an empty scene showed nothing.
- **Remaining from 1b:** test of camera sleep (auto power off).
- **500D:** compatibility test **will not be done** (decision 4 Nov 2026, 500D will not be used). Only the 100D is supported; the code still reads allowed values from the camera.


### Stage 2 pipeline procedure (4 Nov 2026)

- **Done:** `processing/raw_io.py` (`RawFrame`, `read_raw`: CR2 via rawpy without demosaicing, file is not modified) and `processing/channel.py` (`select_channel` R/G/B without interpolation, G = average of the two G pixels in a 2×2 cell, half-resolution output; `saturation_mask`). Tests: synthetic mosaic (exact pixels, different CFA phase, odd dimensions, unchanged input) and a real CR2 from the 100D. `rawpy`, `tifffile` and `opencv-python-headless` are now common dependencies.
- **Notes on CR2 from the 100D (IMG_0001.CR2):** visible area **5208 × 3476** (not 5184 × 3456, which is only the `crop_*` subset), pattern `RGBG` with R at top-left (`raw_pattern` [[0,1],[3,2]]), black level 2048/2048/2048/2047, R/G channel after selection 2604 × 1738.
- **Saturation:** LibRaw reports `white_level` = **13,583** and **at ISO 100 it matches exactly** (see the time series below; hundreds of thousands of pixels exactly at 13,583). IMG_0001.CR2 was taken at ISO 800, where the real clipping is higher (**~15,304**); the saturation threshold therefore **depends on ISO**. The clipping mask therefore uses `white_level` from the header of the given frame, not a fixed number; pixels slightly above the threshold (hot pixels, noise) are also treated as saturated.
- **Remaining from stage 2:** `calib` (master dark – median, master flat with `D_F`), `align` (phase correlation), `stack` (sigma clipping), `binning`, `export` (16-bit TIFF, preview, metadata), `pipeline` with a history of steps and tests: SNR gain ≈ √N, linearity, hot pixels after dark, vignetting after flat.

### Measured darks and bias (4 Nov 2026, 100D, ISO 100, f/8)

Taken with `tools/capture_series.py` (only values from `allowed_values`; camera settings are restored afterwards), 16 frames in each set, in `testdata/calib/` (not committed). Conditions: lights off, cabinet closed, eyepiece covered. Statistics on raw mosaics.

| Set | mean above black | noise over time (σ) | pixels > median+20 ADU | pixels > median+100 ADU | max (median of 16) |
| --- | --- | --- | --- | --- | --- |
| bias 1/4000 s | 2047.5 ADU | 7.2–7.5 ADU | 7 | 1 | 2150 |
| dark 8 s | 2047.5 ADU | 7.2–7.3 ADU | 421 | 121 | 9205 |
| dark 30 s | 2047.2 ADU | 7.3–7.4 ADU | 2228 | 124 | 11090 |

- **No light leak** and no doubling of time: the 30 s frame lasted 35.8 s, so long-exposure noise reduction is off and the darks are raw data.
- **Black level** is in practice 2047.5 ADU in all colours and stable (drift of the mean < 1 ADU across the whole set); LibRaw reports 2048/2048/2048/2047, the 0.5 ADU difference is negligible, but the dark removes it in the same way.
- **Noise over time ≈ 7.3 ADU** (readout noise at ISO 100, same for R, G, B and independent of time up to 30 s).
- **No increase of average dark current and no amp glow:** the mean after 30 s does not differ from bias. The background is uniform.
- **Hot pixels:** about **120 pixels** are strongly hot (> 100 ADU above background) already at 8 s and their number does not change at 30 s; the number of "warm" pixels (> 20 ADU) however grows with time: 7 → 421 → 2228 (of 18.1 Mpx). Darks must therefore have the **same time as the light frames**; bias as a substitute for a dark is not enough.
- **Consequence for the pipeline:** master dark = median of 8–16 darks (noise after median ~2.2 ADU), `D_F` for the flat can be taken from a dark of the same time; a single frame with noise ~7.3 ADU is the main source of error at weak signal, so stacking pays off.

### Measured flat and time series under white light (4 Nov 2026, 100D, ISO 100, f/8)

White light through the fixed orange filter, white matte paper across the whole field, zoom and focus unchanged. Taken with `tools/capture_series.py` (`flat`, `ladder`), `testdata/calib/` (not committed).

- **Flat:** 16× 8 s; in the centre R ≈ 8650 and G ≈ 4750 ADU above black (R ≈ 75 % of range), 0 % saturation, brightness variation between frames ±1 % without trend (the lamp does not heat up). **Vignetting: the corners have ~73–75 % of centre brightness** (G), which is exactly what the flat field corrects. Flat and dark times are identical (8 s), so we have `D_F` for it.
- **Scene spectrum:** R : G : B ≈ 1 : 0.55 : 0.04 (white light through the orange filter). The B channel is not computed.
- **Time series** (1/64 to 32 s of actual time, 2 frames per time, 12 times):
  - **Saturation:** at ISO 100 clipping is exactly at **13,583** (= `white_level`, 4.3 million pixels at the same value). R saturates already at 16 s, G at 32 s. A few pixels are slightly above the threshold (max 14,962).
  - **Gain:** the photon transfer curve gives **≈ 2.2 e⁻/ADU** (R and G after conversion to two G pixels; B is unreliable due to weak signal). Readout noise **≈ 6.7 ADU (~15 e⁻)**, matches the noise from bias (7.3 ADU).
  - **Linearity:** the signal is proportional to nominal time within **±6 %**, grows smoothly with time length (rate 1004 → 1078 ADU/s for R from 1/4 s to 8 s). An interleaved measurement (8 s, 1 s, 8 s, 1 s…) excluded lamp drift and order: the ratio 8 s / 1 s comes out consistently **8.4** instead of 8.0. The cause is probably the real shutter duration versus nominal (Canon gives times in third-EV steps); **source not verified**. For the pipeline this does not matter, because light frames, darks and flats are always taken at the **same time**; comparing signal across different times cannot be done with accuracy better than ~5 %.
- **Remaining:** UV flat (uniformly fluorescing area) and stacking on a fluorescent scene: the scene has been captured, see below.

### Fluorescent scene under UV (4 Nov 2026, 100D, ISO 100, f/8)

Gel substitute: three lines of highlighter of different intensity on white paper under UV, through the fixed orange filter. Taken with `tools/capture_series.py scene` (16× 4 s), `testdata/calib/` (not committed). Paper, zoom and focus unchanged between sets.

- **Signal:** the lines glow in R and G, the paper in the background weakly fluoresces (R ≈ 740 ADU at UV 100 %), the B channel is weak. At 4 s the strongest line slightly saturates (0.14 % of pixels at UV 100 %, 0.05 % at UV 70 %), at 8 s already 0.9 %.
- **UV level:** signal at **UV 70 % = 0.80–0.81 of the signal at UV 100 %**, the same for lines and background, in R and G. The UV level is thus a pure multiplication of the signal (no change of shape or spectrum). "70 %" corresponds to ~81 % of the light. The UV level is nonetheless stored in metadata and the flat is taken for the level in use.
- **Darks 4 s** (16×, for both scene sets): no light leak, noise over time 7.3 ADU as before. **Warm pixels (> 20 ADU) are however 2035 and strongly hot (> 100 ADU) 116**, although earlier at double the time (8 s) there were only 421 (resp. 121). The darks 8 s and 30 s were taken at the start of the day with a "cold" sensor, these after ~1.5 h of shooting (long exposures, live view, UV series). The dark current of hot pixels therefore **strongly depends on sensor temperature**; darks must be taken immediately after the light frames and in the same camera state, as the plan already requires (ch. 9, sensor heating). Subtracting a dark from a different time or temperature will not be accurate for warm pixels; temperature is not measured yet (EDSDK does not return it for the 100D).
- **Consequence for tests:** for dark subtraction on the 4 s scene use darks 4 s (same sensor state), not darks 8 s.
- **Use:** the sets serve for the stacking test (SNR gain ≈ √N), comparison of the R and G channels and the alignment test. It is not a real gel, so the band shape and detection limit are not verified by it.

---

## 11. Open questions

- [x] Setup: metal cabinet, camera from above, UV 70/100 % + white light, fixed orange filter, focusing by AF only.
- [ ] Which dyes are used? (For SYBR verify how much signal passes the orange filter.)
- [ ] Which lens (model, STM?) and at what zoom position is shooting done?
- [ ] UV wavelength (302/312/365 nm) and where does the white light come from (below through a conversion plate, or from above)?
- [ ] What are the parameters of the orange filter (type, transmission edge)?
- [x] **UI language: English, with option to switch** (decided 10 Nov 2026). Texts via Qt `tr()`, translations in `.ts`/`.qm`, Czech as second language.
- [ ] Who will operate the application?
- [ ] Where to store results (locally, network drive, electronic laboratory notebook)?
- [ ] One PC, or several stations?
- [ ] Python + PySide6 (default), or C#?
- [ ] Should simple band quantification belong to v1, or remain in Fiji?
- [ ] Does the lab PC IT manage it? Do they prevent running unsigned applications?

---

## 12. Future

### Monochrome camera instead of DSLR

Advantages for gels: no Bayer mask (all pixels collect the dye emission), cooling (stable, repeatable darks), electronic shutter, simple SDK with a Python wrapper. Disadvantage: usually requires an installed USB driver (one-time administrator). The GelCam architecture can handle it – a new `Camera` implementation is enough (e.g. `AsiCamera` via `zwoasi`); the pipeline is simplified (data are directly mono and linear).

Prices found 30 Oct 2026 (European sellers, incl. VAT, indicative):

| Model | Type | Price |
| --- | --- | --- |
| ZWO ASI678MM | mono, uncooled, IMX678, 8.3 MP, 12 bit | ~380–425 € |
| ZWO ASI533MM Pro | mono, cooled, IMX533 1\" 3008×3008, zero amp glow; needs a 12 V / 3 A power supply | ~1,285–1,350 € |
| QHY533M | mono, cooled, IMX533 | ~1,199 € on sale, normally ~1,450 € |
| Player One Ares-M Pro | mono, cooled, IMX533 | ~1,409 € |
| Basler ace 2 a2A2600-64umBAS | industrial mono, 5.6 MP, USB-powered, C-mount, pypylon SDK | ~569 $ (USA) |

Recommendation: ASI533MM Pro or QHY533M; cheap test of the benefit of a mono camera: ASI678MM. Plus a lens (C-mount or Canon EF adapter) and, for cooled models, a 12 V power supply.

### Software autofocus (moved to v1)

Live view with the magnifier on the marker band → `DriveLensEvf` steps (Near/Far 1–3) → sharpness measure (variance of the Laplacian) → coarse search for the maximum, then fine. The lens must be in AF; for shooting use shutter release without AF. Because the focusing ring is unreachable, this is the only way of focusing in v1 (see ch. 3).

### Quick verification without programming

Series via digiCamControl or N.I.N.A. → calibration and stacking in Siril (turn alignment off, export linearly). Shows the real gain on your gels.

---

## 13. Links

- Canon Developer Programme (EDSDK): registration via the Canon website (Canon Developer Community / Developer Programme for Europe). **Access approved 4 Nov 2026.**

### How to insert EDSDK into the project

1. Download the latest EDSDK for Windows from the Canon portal and unpack it.
2. Copy the **64-bit** DLLs (`EDSDK_64/Dll/EDSDK.dll`, `EdsImage.dll`) into `vendor/edsdk/Dll/` and the headers (`EDSDK/Header/*.h`) into `vendor/edsdk/Header/`.
3. Run `uv run python tools/check_edsdk_constants.py` – it compares the constants in `src/gelcam/camera/edsdk/constants.py` with the headers.
4. In the SDK release notes verify that the **EOS 100D** is in the list of supported models, and record the SDK version here.
5. `vendor/edsdk/` is not committed (Canon licence).
- digiCamControl (reference EDSDK implementation in C#): https://github.com/dukus/digiCamControl
- edsdk-python (Jiloc): https://github.com/Jiloc/edsdk-python
- pyedsdk (PyPI): https://pypi.org/project/pyedsdk/
- edsdk4j (warning about error 99): https://github.com/WolfgangFahl/edsdk4j
- Siril: https://siril.org
- N.I.N.A.: https://nighttime-imaging.eu
- rawpy: https://pypi.org/project/rawpy/
- openIVIS (PLoS ONE 2024): https://doi.org/10.1371/journal.pone.0299875

---

## 14. Opening prompt for the first session in Claude Code

> Read `CLAUDE.md` and `docs/GELCAM_PLAN.md`. The project skeleton and the EDSDK layer already exist. A Canon EOS 100D is connected to this Windows PC and EDSDK is in `vendor/edsdk/`. Run `uv sync`, `uv run pytest`, then `uv run python tools/check_edsdk_constants.py` and `uv run python tools/edsdk_smoke.py` (first without `--capture`). Fix whatever does not work, and record the results of stage 0 in the plan. Ask when you encounter an ambiguity.
