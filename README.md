# GelCam

Aplikace pro Windows na focení agarózových gelů zrcadlovkou Canon EOS 100D přes USB: live view, průvodce pořízením snímku a fyzikálně poctivé zpracování (stacking, dark frame, flat field, výběr barevného kanálu, binning) s lineárním 16bitovým exportem pro kvantifikaci.

Stav: ovládání foťáku přes EDSDK ověřeno na 100D (live view, AF, RAW, obnovení spojení); pipeline zpracování je rozpracovaná (načtení RAW, výběr kanálu).

## Spuštění

```
uv sync
uv run python -m gelcam --mock      # bez foťáku (simulace)
uv run python -m gelcam             # Canon EOS 100D přes EDSDK (Windows)
uv run pytest                       # testy
```

Pro skutečný foťák zkopírujte 64bitové DLL z Canon EDSDK do `vendor/edsdk/Dll/` a hlavičky do `vendor/edsdk/Header/`, pak spusťte `uv run python tools/check_edsdk_constants.py` a `uv run python tools/edsdk_smoke.py`.

## Nastavení na jiném počítači (Windows)

1. Nainstalujte Git a `uv` (bez administrátora stačí `winget install astral-sh.uv`, nebo viz https://docs.astral.sh/uv/).
2. `git clone https://github.com/dreryos/gelcam` a v adresáři `uv sync` (stáhne Python 3.12 x64 a závislosti).
3. `uv run pytest` – testy běží bez foťáku (simulace). Testy nad skutečnými RAW se bez složky `testdata/` přeskočí.
4. **Canon EDSDK** (jen pro práci s foťákem): stáhněte ho z Canon Developer Programme (testováno s verzí 13.21.10, `EDSDKv132110W`), zkopírujte 64bitové `EDSDK_64/Dll/*.dll` do `vendor/edsdk/Dll/` a `EDSDK/Header/*.h` do `vendor/edsdk/Header/`, pak `uv run python tools/check_edsdk_constants.py` a `uv run python tools/edsdk_smoke.py`. Složka `vendor/` se nikdy necommituje (licence Canon).
5. Zavřete EOS Utility, digiCamControl a podobné programy, než spustíte aplikaci s foťákem.
6. **Testovací snímky** (`testdata/`, CR2 z 100D, asi 2,6 GB) nejsou v gitu; viz dohodnutý způsob sdílení v `docs/GELCAM_PLAN.md`. Bez nich jde vyvíjet nad syntetickými daty (`src/gelcam/testing/synthetic.py`) a `MockCamera`.

- Plán, architektura a historie rozhodnutí: [docs/GELCAM_PLAN.md](docs/GELCAM_PLAN.md)
- Kontext pro Claude Code: [CLAUDE.md](CLAUDE.md)
- Návod na nafocení testovacích dat: [docs/TESTOVACI_DATA.md](docs/TESTOVACI_DATA.md)

Canon EDSDK není součástí repozitáře; získejte ho přes Canon Developer Programme a vložte do `vendor/edsdk/`.
