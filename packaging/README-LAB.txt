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
- Cabinet: the focus step needs a high-contrast target in the centre of the image.
- Dark frames: lights off, cabinet closed, eyepiece covered.
- The camera is set to RAW automatically before capture.

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
