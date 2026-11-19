GelCam - gel imaging with a Canon EOS 100D
==========================================

No installation and no administrator rights are needed. This folder is the whole program.

Start
-----
Double-click GelCam.exe. (If Windows SmartScreen says "Unknown publisher": More info -> Run anyway.
This is asked once; the program is not code-signed.)

First time on a PC: check the installation
------------------------------------------
Open a Command Prompt in this folder and run
    GelCam-console.exe --selftest
    GelCam-console.exe --selftest --camera        (camera connected and switched on)
Every line should say OK and the last one "all required checks passed".

Before taking images
--------------------
- Camera: connected by USB, switched on, mode dial on M, powered from the mains adapter (ACK-E15).
- Close EOS Utility, digiCamControl and any other program that uses the camera.
- Lens: the AF/MF switch on the lens must be on AF (otherwise autofocus does nothing, silently).
- Camera menu: switch Movie servo AF off (and Continuous AF in the live view settings, if the menu has it), keep the
  AF method on FlexiZone-Multi and the AF operation on One-Shot. Otherwise the camera keeps re-focusing on its own
  under UV after the autofocus (measured: the sharpness drifted by 20 % within 45 s; with the setting off, by 2 %).
- The live view runs at f/5.6 (wide open, brighter) by default; every capture uses the aperture you set (f/8). The
  switch is in Settings... ("Live view").
- Live view under UV: it shows the exposure that is set, so a weak light is black. Switch on "Bright live view" in the
  Focus card (ISO 6400 for the live view only; captures keep your ISO; the wizard does it by itself in the focus step); focusing under white light is easier and the focus holds when you switch to UV.
- Single frame: the CR2 / TIFF switch chooses the file (default TIFF = black-and-white, selected channel; the CR2 is
  deleted once the TIFF is written). Tick "Inverted TIFF" for dark bands on white. Measure on the non-inverted TIFF
  or on a CR2; series in the wizard are always RAW.
- Cabinet: the focus step needs a high-contrast target in the centre of the image.
- Dark frames: lights off, cabinet closed, eyepiece covered.
- The camera is set to RAW automatically before capture.

Flat field (uneven illumination)
--------------------------------
Step 5 of the wizard can divide out a flat field. A flat belongs to one arrangement: the same UV level (70 % and
100 % are two different flats), aperture, lens and zoom position. Take it with "Take new flat..." in step 5:
put a uniformly fluorescing target (best: a blank gel with the same dye and thickness) where the gel goes, switch
on the UV level you will use, find the exposure with the test frame (centre at 50-80 %, nothing saturated), take
16 frames, then switch all light off and take the 16 dark frames. Repeat it about once a month; the wizard
warns when a flat is older than 30 days or does not fit the series. One set takes about 600 MB in
Documents\GelCam\calibration\flats.

Language
--------
The interface is English. A Czech translation is included: it is used automatically when Windows runs in
Czech. To start in Czech on any PC, double-click GelCam-Czech.cmd (or make a shortcut to it). From a command
line:   GelCam.exe --lang cs   or   --lang en   (also the GELCAM_LANG variable). Technical messages that come
from the camera driver stay in English.

Where things are
----------------
- Images: Documents\GelCam\images\<date>_<gel name>\  (raw frames are never modified).
- Log file and settings: %APPDATA%\GelCam\gelcam.log - send this file when something goes wrong.
- edsdk\Dll: the Canon EDSDK libraries (needed for the real camera; not needed with --mock).

Try without a camera
--------------------
    GelCam.exe --mock

Uninstall
---------
Delete this folder and, if you wish, %APPDATA%\GelCam.
