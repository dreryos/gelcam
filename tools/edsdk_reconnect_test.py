"""Manual reconnection test: unplug the USB cable or switch the camera off and on again.

    uv run python tools/edsdk_reconnect_test.py [--duration 300]

Every 2 s the script reads the battery state from the camera. When a read fails, it prints the error
and tries `reconnect()` until the connection is restored. At the end it prints a summary.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gelcam.camera import CameraError, Prop  # noqa: E402
from gelcam.camera.edsdk import EdsdkCamera  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=300.0, help="how long the test runs (s)")
    args = ap.parse_args()

    cam = EdsdkCamera()
    info = cam.connect()
    print(f"Connected: {info.model}. Now unplug the USB cable (or switch the camera off), wait a few seconds "
          "and then plug it back in (switch it on).")
    t_end = time.time() + args.duration
    outages: list[float] = []
    down_since: float | None = None
    try:
        while time.time() < t_end:
            try:
                batt = cam.get(Prop.BATTERY)
                if down_since is not None:
                    outages.append(time.time() - down_since)
                    print(f"{time.strftime('%H:%M:%S')}  connection restored after {outages[-1]:.1f} s, battery {batt}")
                    down_since = None
                else:
                    print(f"{time.strftime('%H:%M:%S')}  OK, battery {batt}")
                time.sleep(2.0)
            except CameraError as exc:
                if down_since is None:
                    down_since = time.time()
                    print(f"{time.strftime('%H:%M:%S')}  CONNECTION LOST: {exc}")
                try:
                    cam.reconnect(attempts=1, delay=0.0)
                except CameraError as exc2:
                    print(f"{time.strftime('%H:%M:%S')}  trying to restore… ({exc2})")
                    time.sleep(3.0)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            cam.disconnect()
        except Exception:  # noqa: BLE001
            pass
    print(f"\nOutages: {len(outages)}" + (f", restore times: {', '.join(f'{o:.1f} s' for o in outages)}"
                                         if outages else ""))
    return 0 if down_since is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
