"""Captures a series of RAW images for calibration via EdsdkCamera.

    uv run python tools/capture_series.py dark --tv 8 --tv 30 --n 16
    uv run python tools/capture_series.py bias --n 16
    uv run python tools/capture_series.py flat --tv 1/60 --n 16 --name bile
    uv run python tools/capture_series.py ladder --tv 1/4000 --tv 1/2000 ... --n 2

dark, bias: lights off, cabinet closed, eyepiece covered; the first image is
checked for light leaks. flat, ladder: an evenly lit surface,
`ladder` is a series of times (linearity, saturation, gain), `flat` one time, `scene` a static scene (stacking), `--note` into the metadata.
Output: testdata/calib/<day>_<kind>_<time>_iso<ISO>/ with CR2 files and metadata.json.
Camera settings (ISO, shutter speed, aperture) are restored to their original values at the end.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gelcam.camera import Prop, ensure_raw_quality, values  # noqa: E402
from gelcam.camera.edsdk import EdsdkCamera  # noqa: E402
from gelcam.processing.channel import select_channel  # noqa: E402
from gelcam.processing.raw_io import read_raw  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "testdata" / "calib"
LEAK_LIMIT_ADU = 15.0  # mean above black level at ISO 100; dark frames are on the order of units


def find_code(cam, prop: Prop, label_fn, wanted: str) -> int:
    for code in cam.allowed_values(prop):
        if label_fn(code) == wanted:
            return code
    raise SystemExit(f"Camera does not offer {wanted!r} for {prop.value}.")


def stats(path: Path) -> dict:
    f = read_raw(path)
    out = {}
    for letter in "RGB":
        plane = select_channel(f, letter) - f.black_level(letter)
        out[letter] = {"mean": float(plane.mean()), "std": float(plane.std()),
                       "p99_9": float(np.percentile(plane, 99.9)), "max": float(plane.max())}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["dark", "bias", "flat", "ladder", "scene"])
    ap.add_argument("--tv", action="append", default=[], help='shutter time, e.g. 8 or 30 (in s); ignored for bias')
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--iso", type=int, default=100)
    ap.add_argument("--name", default="")
    ap.add_argument("--note", default="", help="description of the scene/lighting for the metadata, e.g. 'UV 100 %%'")
    args = ap.parse_args()

    tv_labels = ['1/4000'] if args.kind == "bias" else [f'{t}"' if "/" not in t else t for t in args.tv]
    if not tv_labels:
        raise SystemExit("Specify at least one --tv (for darks).")

    cam = EdsdkCamera()
    info = cam.connect()
    print(f"Connected: {info.model}")
    for w in cam.warnings:
        print("WARNING:", w)
    original = {p: int(cam.get(p)) for p in (Prop.ISO, Prop.TV, Prop.AV)}
    day = datetime.now().strftime("%Y-%m-%d")
    code = 1
    try:
        ensure_raw_quality(cam)
        cam.set(Prop.ISO, find_code(cam, Prop.ISO, values.iso_label, f"ISO {args.iso}"))
        av = values.av_label(int(cam.get(Prop.AV)))
        for label in tv_labels:
            cam.set(Prop.TV, find_code(cam, Prop.TV, values.tv_label, label))
            tv_s = values.tv_seconds(int(cam.get(Prop.TV)))
            tag = label.replace('"', "s").replace("/", "-")
            out = ROOT / f"{day}_{args.kind}_{tag}_iso{args.iso}{('_' + args.name) if args.name else ''}"
            out.mkdir(parents=True, exist_ok=True)
            print(f"\n== {args.kind} {label}, ISO {args.iso}, {av}, {args.n}× -> {out.relative_to(ROOT.parent.parent)}")
            files, durations = [], []
            for i in range(1, args.n + 1):
                t0 = time.perf_counter()
                tmp = cam.capture(out / "_tmp")
                durations.append(time.perf_counter() - t0)
                dest = out / f"{args.kind}_{tag}_{i:02d}.CR2"
                if dest.exists():
                    raise SystemExit(f"{dest} already exists, not overwriting.")
                tmp.rename(dest)
                files.append(dest.name)
                if args.kind in ("flat", "ladder", "scene"):
                    f = read_raw(dest)
                    sat = float((f.mosaic >= f.white_level).mean())
                    g = select_channel(f, "G") - f.black_level("G")
                    h, w = g.shape
                    centre = float(g[h // 3:2 * h // 3, w // 3:2 * w // 3].mean())
                    corner = float(np.mean([g[:h // 8, :w // 8].mean(), g[:h // 8, -w // 8:].mean(),
                                            g[-h // 8:, :w // 8].mean(), g[-h // 8:, -w // 8:].mean()]))
                    print(f"  {i:2d}/{args.n} {dest.name} G centre {centre:8.1f} ADU, corners/centre {corner / centre:.2f}, "
                          f"saturated {sat * 100:.2f} % ({durations[-1]:.1f} s)")
                    continue
                if i == 1:
                    st = stats(dest)
                    print(f"  1st image: mean above black level R {st['R']['mean']:.2f}, G {st['G']['mean']:.2f}, "
                          f"B {st['B']['mean']:.2f} ADU; duration {durations[0]:.1f} s")
                    if args.kind == "dark" and max(st[c]["mean"] for c in "RGB") > LEAK_LIMIT_ADU:
                        print("  ERROR: light leak (image is not dark). Turn off the lights, close the cabinet, cover the eyepiece.")
                        return 2
                    if tv_s and tv_s >= 1 and durations[0] > 1.8 * tv_s + 3:
                        print("  WARNING: the image took almost twice the set time. Is long-exposure noise reduction "
                              "enabled? Turn it off in the camera menu, otherwise the darks are not raw data.")
                print(f"  {i:2d}/{args.n} {dest.name} ({durations[-1]:.1f} s)")
            tmpdir = out / "_tmp"
            if tmpdir.exists() and not any(tmpdir.iterdir()):
                tmpdir.rmdir()
            meta = {
                "kind": args.kind, "camera": info.model, "serial": info.serial,
                "iso": args.iso, "tv_label": label, "tv_seconds": tv_s, "av_label": av,
                "n": args.n, "files": files, "started": datetime.now().isoformat(timespec="seconds"),
                "capture_durations_s": [round(d, 2) for d in durations],
                "first_frame_stats_adu": stats(out / files[0]),
                "note": ("dark/bias: lights off, cabinet closed, eyepiece covered" if args.kind in ("dark", "bias")
                         else "lights on, scene; zoom and focus unchanged") + (f" | {args.note}" if args.note else ""),
            }
            (out / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        code = 0
    finally:
        for prop, val in original.items():
            try:
                cam.set(prop, val)
            except Exception as exc:  # noqa: BLE001
                print(f"Could not restore {prop.value}: {exc}")
        cam.disconnect()
    print("\nDone. Camera settings restored to the original values.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
