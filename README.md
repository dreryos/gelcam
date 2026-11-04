# GelCam

Aplikace pro Windows na focení agarózových gelů zrcadlovkou Canon EOS 100D přes USB: live view, průvodce pořízením snímku a fyzikálně poctivé zpracování (stacking, dark frame, flat field, výběr barevného kanálu, binning) s lineárním 16bitovým exportem pro kvantifikaci.

Stav: začátek vývoje – rozhraní kamery, simulace, vrstva Canon EDSDK a základní okno (připojení, live view, ostření, expozice, snímek).

## Spuštění

```
uv sync
uv run python -m gelcam --mock      # bez foťáku (simulace)
uv run python -m gelcam             # Canon EOS 100D přes EDSDK (Windows)
uv run pytest                       # testy
```

Pro skutečný foťák zkopírujte 64bitové DLL z Canon EDSDK do `vendor/edsdk/Dll/` a hlavičky do `vendor/edsdk/Header/`, pak spusťte `uv run python tools/check_edsdk_constants.py` a `uv run python tools/edsdk_smoke.py`.

- Plán, architektura a historie rozhodnutí: [docs/GELCAM_PLAN.md](docs/GELCAM_PLAN.md)
- Kontext pro Claude Code: [CLAUDE.md](CLAUDE.md)
- Návod na nafocení testovacích dat: [docs/TESTOVACI_DATA.md](docs/TESTOVACI_DATA.md)

Canon EDSDK není součástí repozitáře; získejte ho přes Canon Developer Programme a vložte do `vendor/edsdk/`.
