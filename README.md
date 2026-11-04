# GelCam

Aplikace pro Windows na focení agarózových gelů zrcadlovkou Canon EOS 100D přes USB: live view, průvodce pořízením snímku a fyzikálně poctivé zpracování (stacking, dark frame, flat field, výběr barevného kanálu, binning) s lineárním 16bitovým exportem pro kvantifikaci.

Stav: plánování / začátek vývoje.

- Plán, architektura a historie rozhodnutí: [docs/GELCAM_PLAN.md](docs/GELCAM_PLAN.md)
- Kontext pro Claude Code: [CLAUDE.md](CLAUDE.md)
- Návod na nafocení testovacích dat: [docs/TESTOVACI_DATA.md](docs/TESTOVACI_DATA.md)

Canon EDSDK není součástí repozitáře; získejte ho přes Canon Developer Programme a vložte do `vendor/edsdk/`.
