# Guide: capturing test data for GelCam

Test sets serve to develop and verify the processing pipeline (dark frames, flat fields, stacking, channel selection, saturation, alignment) before the application can control the camera. Shooting is done to a memory card or via digiCamControl; the output is CR2 files.

This guide assumes our setup: **metal cabinet, Canon EOS 100D inserted from above, manually adjustable zoom, unreachable focus ring, UV lamp at 70/100 %, white light, fixed orange filter.**

Shooting takes about an hour and around 4 GB (one CR2 from the 100D is roughly 25 MB).

---

## 1. Preparation

- **Gels:** ideally two.
  - **Gel A – standard:** marker + several PCR products, as you normally photograph them.
  - **Gel B – dilution series** (strongly recommended): the same product or marker in two-fold dilutions across 6–8 wells (e.g. 100 → 1.5 ng). It shows linearity and how much stacking shifts the detection limit.
- **Blank gel** of the same thickness and staining, without DNA (for the flat field). It should cover the whole area the camera sees.
- Camera powered by the **AC adapter (ACK-E15)** or a fully charged battery; empty card.
- **Cover the viewfinder eyepiece** (eyepiece cap on the strap, or opaque tape). The eyepiece points out of the cabinet, and during a long exposure room light can leak through it.
- Safety: gloves when working with EtBr; cabinet closed while the UV is on.

---

## 2. Camera settings (Canon EOS 100D)

Settings **do not change across any set**, unless a set states otherwise.

| Setting | Value | Why |
| --- | --- | --- |
| Mode | **M** (manual) | same exposure for every frame |
| Quality | **RAW** (RAW + JPEG L is fine for quick preview) | the pipeline works with RAW |
| ISO | **100** | lowest noise; a longer exposure is better than a higher ISO |
| Aperture | **f/5.6–f/8**, fixed | sharpness and depth of field; for a weak signal f/4–5.6 |
| Shutter speed | according to the test frame (section 4), max. 30 s | |
| Zoom | one position for all sets, **mark it on the lens** (permanent marker, tape) and record the focal length | flat fields are valid only for the same zoom; changing the zoom also shifts focus |
| AF mode | **One-Shot**, in live view **FlexiZone-Single** | one point, which you place on the stripe |
| Focusing on shutter press | move AF to the * button (Custom Functions → *Shutter button / AE lock* → variant with AF on the \* button) | so the camera does not refocus on weak fluorescence when the shutter is pressed |
| Image stabilization (IS) | **off** | the camera is firmly mounted |
| Long exposure noise reduction | **off** | otherwise the camera subtracts its own dark frame, doubling the time and distorting the data |
| High ISO speed noise reduction | off | |
| Auto Lighting Optimizer | off | |
| Highlight tone priority (HTP / D+) | off | changes ISO behavior |
| Vignetting / lens aberration correction | off | vignetting is handled by the flat field |
| White balance | fixed (e.g. Daylight) | no effect on RAW; JPEG previews will be consistent |
| Picture Style | Neutral | only for JPEG and live view |
| Auto power off | **longest available time** (15 min), or Disable | the camera must not go to sleep in the middle of a series; after waking, check focus |
| Shutter release | **2 s self-timer** or from a PC (digiCamControl) | no shake from handling |
| Live view | only for focusing and checking; **switched off during series** | the sensor heats up in live view and thermal noise increases |

Menu item names may differ slightly depending on language and firmware version.

---

## 3. Focusing (focus ring not reachable)

1. Turn on the **white light**, place gel A in position and close the cabinet.
2. Set the zoom to the marked position.
3. Turn on live view, move the AF point (FlexiZone-Single, by touching the display) to a **sharp edge of the marker band or the edge of the wells**.
4. Focus (with the * button or a half-press, depending on the setting).
5. Check at **10× magnification** with a loupe. If it is not sharp, focus again on another high-contrast detail (edge of the gel, text on the tray in the same plane).
6. Turn off live view. **Do not refocus any further** and do not change the zoom.
7. Switch to UV. Focus does not change when the light is switched.

If the camera goes to sleep or is switched off between sets, check focus in live view before the next set (with some lenses it may shift after being switched off).

---

## 4. Choosing the exposure

1. Switch to **UV 100 %** and wait about a minute for the lamp brightness to stabilize.
2. Take a test frame of gel A.
3. Check the histogram and the blinking overexposure warning. The brightest band (usually the marker) should sit at roughly **2/3 of the histogram and must not blink as overexposed**. The camera histogram is computed from the JPEG, so it is rather conservative; the RAW has headroom.
4. Adjust the time and repeat. If the correct time would exceed 30 s, open the aperture (f/4–5.6). Keep ISO at 100.
5. Record the resulting time and **do not change it further** (except for sets where stated otherwise).

---

## 5. Image sets

Shoot in this order. Dark frames always right after the light frames, so the sensor has the same temperature.
**Dark frame = UV and white light both off, cabinet closed, eyepiece covered** (a lens cap is neither needed nor possible).

| # | Set | Count | How | Folder |
| --- | --- | --- | --- | --- |
| 1 | **White light – gel A** | 2 | white light, short exposure time per the histogram; documentation of the gel position | `white/` |
| 2 | **Light frames – gel A, UV 100 %** | 16 | time from section 4, nothing is moved | `lights/` |
| 3 | **Dark frames** | 16 | **right after set 2**, same time and ISO, lights off | `darks/` |
| 4 | **Light frames – gel A, UV 70 %** | 8 | same time as set 2 (shows the ratio of lamp levels) | `uv70/` |
| 5 | **Saturation** | 4 | gel A, UV 100 %, exposure 4× longer (or wider aperture), the marker must be overexposed | `saturation/` |
| 6 | **Shift** | 8 | gel A, move the gel slightly between frames (≈ 0.5–1 mm); after the 4th frame a larger shift ≈ 3 mm | `shift/` |
| 7 | **Light frames – gel B** (dilution series) | 16 | UV 100 %, time according to the strongest band of gel B (section 4) | `dilution/lights/` |
| 8 | **Dark frames for gel B** | 16 | right after set 7, same time as set 7 | `dilution/darks/` |
| 9 | **Flat fields, UV 100 %** | 16 | blank gel **in the same position**, same zoom, focus and aperture; time such that the histogram sits **at the midpoint**, without overexposure | `flats/` |
| 10 | **Dark frames for flat fields** | 16 | right after set 9, same time as the flat fields | `flat_darks/` |
| 11 | **Flat fields, UV 70 %** | 8 | as set 9 at UV 70 %, own time | `flats_uv70/` |
| 12 | **Bias** | 16 | shortest time (1/4000 s), ISO 100, lights off | `bias/` |
| 13 | *(optional)* **ISO comparison** | 8 | gel A, UV 100 %, ISO 800 and a time 8× shorter | `iso800/` |
| 14 | *(optional)* **500D** | sets 2, 3, 9, 10 | the same with the EOS 500D (own settings, record separately) | `500d/…` |

The minimum without which development cannot proceed: **sets 2, 3, 9, 10**. Sets 5 and 6 are for the saturation and alignment tests, sets 7–8 for linearity and the detection limit, sets 4 and 11 for the difference between UV levels.

If you also use **SYBR** (or another green dye), shoot sets 2, 3, 9 and 10 also with a gel stained with SYBR. The orange filter cuts off much of its emission, and the data will show whether the R or the G channel is better.

### Tips for flat fields

- The flat field is made with a **blank gel with the same dye** at the same UV level: it captures the non-uniformity of the lamp as well as lens vignetting.
- **Do not use white light for flat fields:** it has a different spectrum and distribution from UV.
- A flat field **must not be overexposed** or too dark: the target is around the midpoint of the histogram.
- If the zoom or focus changes between shooting the gel and the flat fields, the flat fields are useless – it is better to shoot them again.

---

## 6. Folder structure and log

Copy the files from the card without renaming them into:

```
testdata/
  2026-11-XX_sada01/
    notes.md
    white/
    lights/
    darks/
    uv70/
    saturation/
    shift/
    dilution/
      lights/
      darks/
    flats/
    flat_darks/
    flats_uv70/
    bias/
```

Record the following in `notes.md`:

```
Date and time:
Camera: Canon EOS 100D (firmware:)
Lens (model) and focal length (zoom position):
Clona / ISO:
Time – lights: ... s, uv70: ... s, gel B: ... s, flats: ... s, flats_uv70: ... s
Barvivo a koncentrace:
UV lamp – wavelength (302/312/365 nm, if known):
White light – from below, or from above:
Orange filter – type, if known:
Eyepiece covered: yes/no
Gel A – obsah jamek:
Gel B – dilution series (amounts in wells):
Room temperature (approximately):
Notes / what went wrong:
```

The `testdata/` folder is listed in `.gitignore` and is not uploaded to the repository.

---

## 7. Quick check after shooting

- File counts in each folder match.
- Open one light frame at random: it is sharp and the marker is not overexposed.
- One dark frame is really dark (no forgotten light or light leaking through the eyepiece).
- The flat field is uniform and free of gel structure or dirt.
- In the EXIF data of all frames in one set, the exposure time, aperture, ISO and focal length are the same.
