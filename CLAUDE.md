# GelCam

Desktopová aplikace pro Windows na focení agarózových gelů (PCR) zrcadlovkou Canon EOS 100D přes USB. Live view, průvodce pořízením snímku a fyzikálně poctivé zpracování (stacking, dark, flat, výběr kanálu, binning) s lineárním 16bitovým exportem.

Celý plán, technické detaily a historie rozhodnutí: **`docs/GELCAM_PLAN.md`**. Před větší změnou si přečti příslušnou kapitolu.

## Hardware

- Kovová skříň, Canon EOS 100D zanořený shora, pevný oranžový filtr, UV lampa 70/100 % a bílé světlo.
- Zoom ručně měnitelný, **ostřicí kroužek nedosažitelný** → ostření jen AF (v aplikaci přes EDSDK: AF v live view + posun po krocích). Spoušť vždy bez AF.
- Zoom a úroveň UV jsou součást kalibrace a metadat. Dark = zhasnutá světla, zavřená skříň, zakrytý okulár.

## Stav

- Fáze: etapa 0 a 1b (ovládání 100D přes EDSDK) hotové a ověřené na foťáku, etapa 2 (pipeline) rozpracovaná: `processing/raw_io.py`, `channel.py`. Další krok `calib` (master dark/flat). Podrobnosti a naměřené hodnoty v `docs/GELCAM_PLAN.md`.
- Testovací RAW sady (světlé, dark, flat) jsou v `testdata/` (necommitují se).

## Stack

- Python 3.12 **x64**, správa prostředí `uv`
- PySide6 (GUI), numpy, rawpy, tifffile, opencv-python-headless, Pillow
- Canon EDSDK přes ctypes (`src/gelcam/camera/edsdk/`), DLL a hlavičky v `vendor/edsdk/`
- pytest, PyInstaller (onedir)

## Příkazy

- `uv sync` – instalace závislostí
- `uv run pytest` – testy
- `uv run python -m gelcam` – spuštění aplikace (`--mock` bez foťáku)
- `uv run python tools/check_edsdk_constants.py` – kontrola konstant EDSDK proti hlavičkám
- `uv run python tools/edsdk_smoke.py [--capture]` – diagnostika etapy 0 (Windows + 100D)

## Architektura v kostce

`ui/` → `acquisition/` → `camera/` (rozhraní `Camera`, implementace `MockCamera`, `EdsdkCamera`) a `processing/` → `storage/`. GUI ani řízení snímání nesmí volat EDSDK přímo; vše jde přes rozhraní `Camera`.

## Pravidla, která neporušovat

1. **Integrita dat:** původní RAW se nikdy nemění. `result.tif` obsahuje jen lineární operace na celém obrazu. Jas, kontrast, gamma a inverze ovlivňují jen náhled. Každý krok zpracování se zapisuje do `metadata.json`.
2. **Žádný AI denoising.** Klasický denoise jen volitelně a jako samostatný soubor.
3. **Pracovat s RAW, ne s JPEG.** Výběr kanálu z CFA mozaiky bez demozaikování (EtBr/GelRed → R, SYBR → G).
4. **Hodnoty do foťáku nastavovat jen ze seznamu povolených hodnot, který foťák vrátí.** EDSDK nekontroluje platnost hodnot a špatné nastavení může foťák zablokovat (chyba 99).
5. **EDSDK jen v jednom vlákně s Windows message loop.** GUI komunikuje přes frontu nebo Qt signály.
6. **Bez administrátorských práv:** nic nezapisovat do Program Files ani registru; nastavení do `%APPDATA%\GelCam`. Žádné závislosti, které vyžadují instalaci ovladačů.
7. **Licence Canon:** obsah `vendor/edsdk/` ani `testdata/` nikdy necommitovat.
8. Kód musí jít vyvíjet a testovat bez připojeného foťáku (MockCamera, syntetická data v `src/gelcam/testing/synthetic.py`).

## Konvence

- Kód a identifikátory anglicky, rozhraní aplikace a dokumentace česky.
- Typové anotace, malé čisté funkce v `processing/` (numpy pole dovnitř i ven), testy ke každému kroku pipeline.
- Nové poznatky a rozhodnutí doplňovat do `docs/GELCAM_PLAN.md`.
