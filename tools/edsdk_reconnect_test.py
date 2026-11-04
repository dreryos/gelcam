"""Ruční test obnovení spojení: odpojte kabel USB nebo foťák vypněte a znovu zapněte.

    uv run python tools/edsdk_reconnect_test.py [--duration 300]

Skript každé 2 s čte z foťáku stav baterie. Když čtení selže, vypíše chybu
a zkouší `reconnect()`, dokud se spojení neobnoví. Na konci vypíše přehled.
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
    ap.add_argument("--duration", type=float, default=300.0, help="jak dlouho test běží (s)")
    args = ap.parse_args()

    cam = EdsdkCamera()
    info = cam.connect()
    print(f"Připojeno: {info.model}. Nyní odpojte kabel USB (nebo foťák vypněte), počkejte pár sekund "
          "a pak ho zase připojte (zapněte).")
    t_end = time.time() + args.duration
    outages: list[float] = []
    down_since: float | None = None
    try:
        while time.time() < t_end:
            try:
                batt = cam.get(Prop.BATTERY)
                if down_since is not None:
                    outages.append(time.time() - down_since)
                    print(f"{time.strftime('%H:%M:%S')}  spojení obnoveno po {outages[-1]:.1f} s, baterie {batt}")
                    down_since = None
                else:
                    print(f"{time.strftime('%H:%M:%S')}  OK, baterie {batt}")
                time.sleep(2.0)
            except CameraError as exc:
                if down_since is None:
                    down_since = time.time()
                    print(f"{time.strftime('%H:%M:%S')}  SPOJENÍ ZTRACENO: {exc}")
                try:
                    cam.reconnect(attempts=1, delay=0.0)
                except CameraError as exc2:
                    print(f"{time.strftime('%H:%M:%S')}  zkouším obnovit… ({exc2})")
                    time.sleep(3.0)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            cam.disconnect()
        except Exception:  # noqa: BLE001
            pass
    print(f"\nVýpadků: {len(outages)}" + (f", doby obnovení: {', '.join(f'{o:.1f} s' for o in outages)}"
                                         if outages else ""))
    return 0 if down_since is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
