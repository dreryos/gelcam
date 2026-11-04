"""Pořídí sérii RAW snímků pro kalibraci přes EdsdkCamera.

    uv run python tools/capture_series.py dark --tv 8 --tv 30 --n 16
    uv run python tools/capture_series.py bias --n 16
    uv run python tools/capture_series.py flat --tv 1/60 --n 16 --name bile
    uv run python tools/capture_series.py ladder --tv 1/4000 --tv 1/2000 ... --n 2

dark, bias: světla zhasnutá, skříň zavřená, okulár zakrytý; první snímek se
zkontroluje na světelný únik. flat, ladder: rozsvícená rovnoměrná plocha,
`ladder` je řada časů (linearita, saturace, zisk), `flat` jeden čas, `scene` nehybná scéna (stacking), `--note` do metadat.
Výstup: testdata/calib/<den>_<druh>_<čas>_iso<ISO>/ s CR2 a metadata.json.
Nastavení foťáku (ISO, čas, clona) se po skončení vrátí na původní hodnoty.
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
LEAK_LIMIT_ADU = 15.0  # průměr nad black levelem při ISO 100; tma je řádově jednotky


def find_code(cam, prop: Prop, label_fn, wanted: str) -> int:
    for code in cam.allowed_values(prop):
        if label_fn(code) == wanted:
            return code
    raise SystemExit(f"Foťák nenabízí {wanted!r} pro {prop.value}.")


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
    ap.add_argument("--tv", action="append", default=[], help='čas, např. 8 nebo 30 (v s); u bias se ignoruje')
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--iso", type=int, default=100)
    ap.add_argument("--name", default="")
    ap.add_argument("--note", default="", help="popis scény/osvětlení do metadat, např. 'UV 100 %%'")
    args = ap.parse_args()

    tv_labels = ['1/4000'] if args.kind == "bias" else [f'{t}"' if "/" not in t else t for t in args.tv]
    if not tv_labels:
        raise SystemExit("Zadejte aspoň jeden --tv (u darků).")

    cam = EdsdkCamera()
    info = cam.connect()
    print(f"Připojeno: {info.model}")
    for w in cam.warnings:
        print("UPOZORNĚNÍ:", w)
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
                    raise SystemExit(f"{dest} už existuje, nepřepisuji.")
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
                    print(f"  {i:2d}/{args.n} {dest.name} G střed {centre:8.1f} ADU, rohy/střed {corner / centre:.2f}, "
                          f"saturováno {sat * 100:.2f} % ({durations[-1]:.1f} s)")
                    continue
                if i == 1:
                    st = stats(dest)
                    print(f"  1. snímek: průměr nad black levelem R {st['R']['mean']:.2f}, G {st['G']['mean']:.2f}, "
                          f"B {st['B']['mean']:.2f} ADU; trvání {durations[0]:.1f} s")
                    if args.kind == "dark" and max(st[c]["mean"] for c in "RGB") > LEAK_LIMIT_ADU:
                        print("  CHYBA: světelný únik (snímek není tmavý). Zhasněte světla, zavřete skříň, zakryjte okulár.")
                        return 2
                    if tv_s and tv_s >= 1 and durations[0] > 1.8 * tv_s + 3:
                        print("  UPOZORNĚNÍ: snímek trval skoro dvojnásobek času. Je zapnutá redukce šumu při dlouhé "
                              "expozici? Vypněte ji v menu foťáku, jinak darky nejsou surová data.")
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
                "note": ("dark/bias: světla zhasnutá, skříň zavřená, okulár zakrytý" if args.kind in ("dark", "bias")
                         else "rozsvícená scéna; zoom a ostření beze změny") + (f" | {args.note}" if args.note else ""),
            }
            (out / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        code = 0
    finally:
        for prop, val in original.items():
            try:
                cam.set(prop, val)
            except Exception as exc:  # noqa: BLE001
                print(f"Nepodařilo se vrátit {prop.value}: {exc}")
        cam.disconnect()
    print("\nHotovo. Nastavení foťáku vráceno na původní hodnoty.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
