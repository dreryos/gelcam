"""Stage 0: verifying communication with the Canon EOS 100D via EDSDK.

Usage (Windows, camera switched on, connected via USB, M mode, RAW quality,
EOS Utility and digiCamControl closed):

    uv run python tools/edsdk_smoke.py              # read only + one live view frame
    uv run python tools/edsdk_smoke.py --focus      # also AF and a focus step in live view
    uv run python tools/edsdk_smoke.py --capture    # also captures and downloads one RAW

The script does not write any exposure settings to the camera. Results are saved
to testdata/edsdk_smoke/.
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gelcam.camera import FocusStep, Prop, ensure_raw_quality  # noqa: E402
from gelcam.camera import values  # noqa: E402
from gelcam.camera.edsdk import EdsdkCamera  # noqa: E402

OUT = ROOT / "testdata" / "edsdk_smoke"


def step(title: str):
    print(f"\n== {title}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", action="store_true", help="capture and download one image")
    ap.add_argument("--focus", action="store_true", help="try AF and a focus step")
    ap.add_argument("--vendor", type=Path, default=None, help="folder with EDSDK (default vendor/edsdk)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    cam = EdsdkCamera(args.vendor)
    results: list[tuple[str, bool, str]] = []

    def run(name: str, fn):
        t0 = time.perf_counter()
        try:
            detail = fn() or ""
            results.append((name, True, f"{detail} ({time.perf_counter() - t0:.2f} s)"))
            print(f"OK    {name}: {detail}")
        except Exception as exc:  # noqa: BLE001
            results.append((name, False, str(exc)))
            print(f"ERROR {name}: {exc}")
            traceback.print_exc()

    step("Connection")
    try:
        info = cam.connect()
    except Exception as exc:  # noqa: BLE001
        print(f"Connection failed: {exc}")
        traceback.print_exc()
        return 1
    print(f"Model: {info.model}  port: {info.port}  serial no.: {info.serial or '-'}")
    for w in cam.warnings:
        print("WARNING:", w)

    try:
        step("Reading properties")
        run("battery", lambda: f"{cam.get(Prop.BATTERY)}")
        run("AE mode", lambda: f"{cam.get(Prop.AE_MODE)} (3 = M)")
        run("ISO", lambda: values.iso_label(int(cam.get(Prop.ISO))))
        run("shutter", lambda: values.tv_label(int(cam.get(Prop.TV))))
        run("aperture", lambda: values.av_label(int(cam.get(Prop.AV))))
        run("image quality", lambda: values.quality_label(int(cam.get(Prop.IMAGE_QUALITY))))

        step("Lens")

        def lens():
            li = cam.lens_info()
            return (f"name: {li.name or 'not reported'}, attached: "
                    f"{'not reported' if li.attached is None else li.attached}, focal length: "
                    f"{f'{li.focal_mm:g} mm' if li.focal_mm else 'not reported'}")

        run("lens", lens)

        step("Allowed values")
        run("ISO", lambda: ", ".join(values.iso_label(v) for v in cam.allowed_values(Prop.ISO)))
        run("shutter", lambda: ", ".join(values.tv_label(v) for v in cam.allowed_values(Prop.TV)))
        run("aperture", lambda: ", ".join(values.av_label(v) for v in cam.allowed_values(Prop.AV)))
        run("image quality", lambda: ", ".join(
            f"{values.quality_label(v)} (0x{v:X})" for v in cam.allowed_values(Prop.IMAGE_QUALITY)))

        step("Live view")

        def lv_frame():
            cam.start_live_view()
            frame = None
            for _ in range(50):
                frame = cam.live_view_frame()
                if frame is not None:
                    break
                time.sleep(0.1)
            if frame is None:
                raise RuntimeError("no live view frame within 5 s")
            from PIL import Image

            Image.fromarray(frame).save(OUT / "liveview.jpg")
            t0 = time.perf_counter()
            n = sum(cam.live_view_frame() is not None for _ in range(20))
            fps = n / (time.perf_counter() - t0)
            return f"{frame.shape[1]}×{frame.shape[0]}, ~{fps:.1f} fps, saved liveview.jpg"

        run("live view frame", lv_frame)

        if args.focus:
            step("Focus")
            run("zoom 5×", lambda: cam.set_live_view_zoom(5))
            run("autofocus", lambda: cam.autofocus())
            run("step Near1", lambda: cam.drive_focus(FocusStep.NEAR_1))
            run("step Far1", lambda: cam.drive_focus(FocusStep.FAR_1))
            run("zoom 1×", lambda: cam.set_live_view_zoom(1))

        run("live view off", lambda: cam.stop_live_view())

        if args.capture:
            step("Capture")
            run("RAW quality", lambda: "changed to " + hex(q) if (q := ensure_raw_quality(cam)) else "already RAW")
            run("image + download", lambda: str(cam.capture(OUT)))
    finally:
        cam.disconnect()

    step("Summary")
    ok = sum(1 for _, good, _ in results if good)
    print(f"{ok}/{len(results)} steps OK")
    report = OUT / "report.txt"
    report.write_text(
        f"Model: {info.model}\n" + "\n".join(f"{'OK' if g else 'ERROR'}\t{n}\t{d}" for n, g, d in results) + "\n",
        encoding="utf-8",
    )
    print(f"Log: {report}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
