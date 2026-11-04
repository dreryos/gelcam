"""Etapa 0: ověření komunikace s Canon EOS 100D přes EDSDK.

Použití (Windows, foťák zapnutý, připojený USB, režim M, kvalita RAW,
EOS Utility i digiCamControl zavřené):

    uv run python tools/edsdk_smoke.py              # jen čtení + jeden snímek live view
    uv run python tools/edsdk_smoke.py --focus      # navíc AF a posun ostření v live view
    uv run python tools/edsdk_smoke.py --capture    # navíc vyfotí a stáhne jeden RAW

Skript do foťáku nezapisuje žádné nastavení expozice. Výsledky se ukládají
do testdata/edsdk_smoke/.
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
    ap.add_argument("--capture", action="store_true", help="vyfotit a stáhnout jeden snímek")
    ap.add_argument("--focus", action="store_true", help="vyzkoušet AF a posun ostření")
    ap.add_argument("--vendor", type=Path, default=None, help="složka s EDSDK (výchozí vendor/edsdk)")
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
            print(f"CHYBA {name}: {exc}")
            traceback.print_exc()

    step("Připojení")
    try:
        info = cam.connect()
    except Exception as exc:  # noqa: BLE001
        print(f"Připojení selhalo: {exc}")
        traceback.print_exc()
        return 1
    print(f"Model: {info.model}  port: {info.port}  sériové č.: {info.serial or '-'}")
    for w in cam.warnings:
        print("UPOZORNĚNÍ:", w)

    try:
        step("Čtení vlastností")
        run("baterie", lambda: f"{cam.get(Prop.BATTERY)}")
        run("režim AE", lambda: f"{cam.get(Prop.AE_MODE)} (3 = M)")
        run("ISO", lambda: values.iso_label(int(cam.get(Prop.ISO))))
        run("čas", lambda: values.tv_label(int(cam.get(Prop.TV))))
        run("clona", lambda: values.av_label(int(cam.get(Prop.AV))))
        run("kvalita obrazu", lambda: values.quality_label(int(cam.get(Prop.IMAGE_QUALITY))))

        step("Povolené hodnoty")
        run("ISO", lambda: ", ".join(values.iso_label(v) for v in cam.allowed_values(Prop.ISO)))
        run("čas", lambda: ", ".join(values.tv_label(v) for v in cam.allowed_values(Prop.TV)))
        run("clona", lambda: ", ".join(values.av_label(v) for v in cam.allowed_values(Prop.AV)))
        run("kvalita obrazu", lambda: ", ".join(
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
                raise RuntimeError("žádný snímek live view do 5 s")
            from PIL import Image

            Image.fromarray(frame).save(OUT / "liveview.jpg")
            t0 = time.perf_counter()
            n = sum(cam.live_view_frame() is not None for _ in range(20))
            fps = n / (time.perf_counter() - t0)
            return f"{frame.shape[1]}×{frame.shape[0]}, ~{fps:.1f} fps, uloženo liveview.jpg"

        run("snímek live view", lv_frame)

        if args.focus:
            step("Ostření")
            run("lupa 5×", lambda: cam.set_live_view_zoom(5))
            run("autofokus", lambda: cam.autofocus())
            run("krok Near1", lambda: cam.drive_focus(FocusStep.NEAR_1))
            run("krok Far1", lambda: cam.drive_focus(FocusStep.FAR_1))
            run("lupa 1×", lambda: cam.set_live_view_zoom(1))

        run("vypnutí live view", lambda: cam.stop_live_view())

        if args.capture:
            step("Focení")
            run("kvalita RAW", lambda: "změněna na " + hex(q) if (q := ensure_raw_quality(cam)) else "už RAW")
            run("snímek + stažení", lambda: str(cam.capture(OUT)))
    finally:
        cam.disconnect()

    step("Souhrn")
    ok = sum(1 for _, good, _ in results if good)
    print(f"{ok}/{len(results)} kroků v pořádku")
    report = OUT / "report.txt"
    report.write_text(
        f"Model: {info.model}\n" + "\n".join(f"{'OK' if g else 'CHYBA'}\t{n}\t{d}" for n, g, d in results) + "\n",
        encoding="utf-8",
    )
    print(f"Záznam: {report}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
