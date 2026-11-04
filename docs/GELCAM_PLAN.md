# GelCam – plán, poznámky a historie

Kompletní kontext pro vývoj aplikace GelCam. Vznikl z konverzace 29. 10. – 4. 11. 2026. Stručná verze pro Claude Code je v `CLAUDE.md` v kořeni repozitáře.

---

## 1. O co jde

Laboratoř fotí agarózové gely z PCR zrcadlovkou **Canon EOS 100D** (pro testy kompatibility je k dispozici i **EOS 500D**). Oficiální EOS Utility 2 na Windows padá hned při spuštění a dostupné alternativy (digiCamControl, qDslrDashboard, Lightroom…) buď nemají workflow pro gely, nebo jsou placené či složité.

**GelCam** je desktopová aplikace pro Windows, která:

- ovládá 100D přes USB (Canon EDSDK),
- má live view s lupou pro ostření a histogramem,
- provede obsluhu průvodcem k co nejkvalitnějšímu snímku gelu,
- zlepšuje kvalitu fyzikálně poctivými metodami: průměrování snímků (stacking), odečet dark frame, flat-field korekce, výběr barevného kanálu, binning,
- exportuje lineární 16bitový TIFF vhodný ke kvantifikaci a archivuje původní RAW,
- běží jako přenosná složka bez administrátorských práv.

---

## 2. Zkrácená historie konverzace

1. **EOS Utility 2 padá na Windows** (100D, pád hned při spuštění, ještě bez foťáku). Pravděpodobné příčiny: chybějící/rozbitý .NET Framework 3.5 nebo poškozený uživatelský config (`%LocalAppData%\Canon_Inc`). Doporučená čistá reinstalace EU2 (2.14.x) ze stránky podpory 100D. EU3 tenhle model nepodporuje.
2. **Open source tethering na Windows:** prakticky jen **digiCamControl** (MIT, C#, pod kapotou Canon EDSDK, podporuje 100D). Zdarma, ale ne open source: **qDslrDashboard**. Ostatní open source nástroje (gphoto2, Entangle, darktable tethering) běží na Linuxu/macOS, na Windows jen přes WSL2 + usbipd (bastl). Placené: Smart Shooter 4, Breeze DSLR Remote Pro, Helicon Remote, Lightroom Classic, Capture One, ON1.
3. **Úpravy kontrastu a jasu při tetheringu:** buď Picture Style ve foťáku (ovlivní jen JPEG a live view), nebo úpravy RAW po snímku (Lightroom, Capture One, darktable). Pro gely se ukázalo, že důležitější je kvalita samotných dat než kosmetické úpravy.
4. **Rozhodnutí napsat vlastní aplikaci.** Varianty backendu: (a) nadstavba nad digiCamControl (webserver/CLI), (b) **přímo Canon EDSDK – zvoleno**, (c) libgphoto2 přes MSYS2 – zamítnuto (vyžaduje výměnu USB ovladače přes Zadig, rozbije EOS Utility i digiCamControl).
5. **digiCamControl používá oficiální EDSDK** (`EDSDK.dll`, `EdsImage.dll`). Jeho zdrojový kód (C#, GitHub) je dobrá referenční implementace (live view, události, message loop).
6. **100D vs 500D:** stejný základ EDSDK (expozice, spoušť, stažení, live view). 500D je starší (DIGIC 4, pomalé ostření v live view) a nejnovější verze EDSDK ho nemusí podporovat. Pravidlo: povolené hodnoty vždy číst z foťáku za běhu. Vývojová platforma 100D, 500D pro test kompatibility.
7. **Techniky pro lepší snímky gelů** (jádro aplikace): stacking (šum klesá s √N), dark frame, flat field, nízké ISO a delší čas, RAW místo JPEG (lineární data), výběr kanálu podle barviva (EtBr/GelRed → R, SYBR → G), binning 2×2, indikace saturace z RAW, 16bitový TIFF a metadata. **AI denoising nepoužívat** (může potlačit slabé pruhy nebo vytvořit strukturu, která tam není; problém pro kvantifikaci i pravidla časopisů). Hardware pomůže víc než software: emisní filtr (oranžový pro EtBr, žlutý pro SYBR) a zatemnění.
8. **Vznikl plán aplikace** (dokument „GelCam – plán aplikace“ na claude.ai; obsah je převzatý do tohoto souboru).
9. **Vývoj potřebuje** Windows PC a samotný foťák jen pro etapu 0 a integrační testy. EDSDK existuje i pro macOS, ale finální ověření musí proběhnout na Windows. Windows ve VM na Apple Silicon pro test SDK nepoužívat.
10. **Nasazení bez administrátora:** ano – PyInstaller (onedir), vestavěný ovladač WPD/PTP, přibalený VC++ runtime, nastavení v `%APPDATA%`. Rizika: AppLocker/zásady IT, hláška SmartScreen.
11. **Náhrada zrcadlovky** (do budoucna): monochromatická astro kamera je pro gely lepší (bez Bayerovy masky, chlazení, elektronická závěrka). Viz kapitola 12.
12. **Ostření přes EDSDK:** jen v live view a relativně po krocích (`kEdsCameraCommand_DriveLensEvf`, Near/Far 1–3). Objektiv musí být v poloze AF, absolutní pozice nejde zjistit. Původně plánováno až do v2.
13. **Podobné projekty:** hotový ekvivalent neexistuje. Užitečné: **N.I.N.A.** (open source astro capture, Windows, nativní Canon/ZWO/QHY) + **Siril** (open source kalibrace a stacking). Python wrappery EDSDK: `edsdk-python` (Jiloc), `pyedsdk` (PyPI). Gelové projekty jsou hlavně hardwarové (Raspberry Pi, openIVIS) bez kalibrace a stackingu.
14. **Nemusí se čekat na schválení EDSDK.** Pipeline, rozhraní kamery, MockCamera, GUI a průvodce jdou vyvíjet hned nad testovacími daty. Windows je potřeba až pro EDSDK, balení a test nasazení.
15. **Upřesněná sestava (4. 11.):** kovová skříň s foťákem shora, ostřicí kroužek nedosažitelný (ostření jen AF → softwarové ostření patří do v1), ručně měnitelný zoom, UV 70/100 % a bílé světlo, pevný oranžový filtr. Návod na testovací data: `docs/TESTOVACI_DATA.md`.

---

## 3. Hardware a prostředí

### Skutečná sestava (upřesněno 4. 11. 2026)

- **Kovová skříň** (temná komora), fotoaparát je **zanořený shora** objektivem dolů.
- **Zoom** na objektivu jde ručně měnit, **ostřicí kroužek není dosažitelný** → ostří se výhradně autofokusem (z foťáku nebo z aplikace přes EDSDK).
- **Osvětlení:** UV lampa se dvěma úrovněmi (**70 % a 100 %**) a **bílé světlo**, přepínatelné.
- **Emisní filtr:** pevný **oranžový** filtr před objektivem.

### Fotoaparát Canon EOS 100D – parametry důležité pro GelCam (ze specifikace Canon)

| Parametr | Hodnota | Dopad |
| --- | --- | --- |
| Snímač | CMOS APS-C 22,3 × 14,9 mm, 18 Mpx, Bayer (primární barvy) | výběr kanálu z mozaiky |
| RAW | 14bit CR2, 5184 × 3456 px | jeden kanál (R) = 2592 × 1728 px |
| Časy | 30 s – 1/4000 s, Bulb | nad 30 s jen Bulb (v1 se mu vyhnout, raději víc snímků) |
| ISO | 100–12800 (rozšíření H 25600) | pro gely ISO 100 |
| Závěrka | štěrbinová s elektronickou první lamelou, tiché snímání | v live view méně otřesů |
| Live view | Hybrid CMOS AF II, FlexiZone-Single, lupa 5×/10×, histogram, mřížka | ostření a kontrola z aplikace |
| Rozhraní | USB 2.0 Hi-Speed (mini-USB) | stažení RAW ~1–2 s |
| Napájení | LP-E12; síťová sada **ACK-E15** | v boxu vždy síťový adaptér |
| Úspora energie | vypnutí po 30 s – 15 min | aplikace musí prodlužovat (EDSDK `ExtendShutDownTimer`) nebo nastavit nejdelší |
| Hledáček | závěrka okuláru jen na řemenu | okulár míří ven ze skříně → přelepit/zakrýt (průnik světla při dlouhých expozicích) |

### Prostředí

| Prvek | Požadavek | Poznámka |
| --- | --- | --- |
| Fotoaparát | Canon EOS 100D, režim M, RAW (CR2) | 500D pro test kompatibility; mini-USB kabel |
| Napájení | síťový adaptér ACK-E15 | live view a série baterii rychle vybijí |
| Karta | karta ve foťáku, nebo v menu zapnout „Spoušť bez karty“ | jinak foťák odmítne exponovat |
| Uchycení | pevně ve skříni | flat field platí jen při stejné geometrii, zoomu a ostření |
| Zatemnění | kovová skříň; zakrytý okulár | |
| Emisní filtr | pevný oranžový | ideální pro EtBr/GelRed; pro SYBR (emise ~520 nm) ho oranžový filtr velkou část odřízne – ověřit na datech |
| PC | Windows 10/11 x64, USB 2.0+ | |
| SDK | Canon EDSDK (registrace v Canon Developer Programme, schválení trvá několik dní) | verze, která podporuje 100D (a ideálně i 500D) |

### Důsledky sestavy pro aplikaci

- **Ostření musí umět aplikace už ve v1:** spuštění AF v live view (`kEdsCameraCommand_DoEvfAf`, FlexiZone-Single na pruhu markeru) a jemné doladění po krocích (`DriveLensEvf`) podle míry ostrosti. Ostří se nejlépe **při bílém světle** (vysoký kontrast), pak se přepne na UV.
- **Spoušť bez AF:** při focení nesmí foťák znovu zaostřit (EDSDK spoušť s variantou NonAF; při ručním focení přesunout AF na tlačítko * v uživatelských funkcích).
- **Ostření se ověřuje na začátku každé session** a po každé změně zoomu (u zoomového objektivu se při změně ohniska posouvá i ostření; u STM objektivů může ostření po vypnutí foťáku ujet).
- **Zoom je součást kalibrace:** flat platí jen pro danou polohu zoomu. Doporučení: zvolit jednu polohu, označit ji na objektivu a změnu zoomu brát jako novou kalibraci.
- **Úroveň UV (70/100 %) je součást profilu a metadat;** flaty se pořizují pro používanou úroveň.
- **Bílé světlo** slouží k ostření, zarovnání gelu a volitelnému dokumentačnímu snímku (pozice jamek). Jako flat pro fluorescenci se nepoužívá (jiné spektrum i rozložení).
- **Darky bez krytky:** objektiv je ve skříni, takže dark = zhasnuté světlo, zavřená skříň, zakrytý okulár.
- **Výběr kanálu se ověří na datech:** u EtBr za oranžovým filtrem R; pro SYBR změřit SNR v R a G kanálu a podle toho nastavit profil.

---

## 4. Architektura

Pět vrstev. Veškerá komunikace s foťákem jde přes jedno rozhraní, takže lze foťák nahradit simulací a později i mono kamerou.

```
Rozhraní (PySide6)        hlavní obrazovka, průvodce, profily
        │
Řízení snímání            live view smyčka, série, kalibrace, návrh expozice
        │                         │
Rozhraní kamery            Zpracování
  EdsdkCamera (EDSDK)        rawpy + numpy: dark, flat, stacking,
  MockCamera (soubory)       výběr kanálu, binning, export TIFF
  [AsiCamera – budoucnost]        │
        │                   Úložiště
Fotoaparát přes USB          složka gelu, knihovna kalibrací, profily
```

### Technologie

- Python 3.12 **x64**, GUI v **PySide6** (Qt 6).
- Canon EDSDK přes `ctypes` (vlastní tenký wrapper), případně `edsdk-python` / `pyedsdk` jako inspirace nebo základ.
- `rawpy` (LibRaw) – čtení CR2, `numpy` – výpočty, `tifffile` – 16bitový export, `opencv-python-headless` – zarovnání (fázová korelace), `Pillow` – náhledy.
- `pytest` – testy, `PyInstaller` – balení (onedir).
- Správa prostředí: `uv` (instalace bez administrátora), případně venv + pip.
- Alternativa, která zůstává otevřená: C#/.NET (blíž k digiCamControl), ale bez rawpy/numpy.

### Navržená struktura repozitáře

```
gelcam/
  CLAUDE.md
  pyproject.toml
  docs/GELCAM_PLAN.md
  src/gelcam/
    camera/
      base.py            # Protocol Camera + datové typy
      mock.py            # MockCamera – přehrává soubory z testovací sady
      edsdk/             # EdsdkCamera, ctypes binding, vlákno s message loop
    acquisition/
      live_view.py       # smyčka EVF snímků
      series.py          # série N snímků, průběžné stahování, obnovení
      exposure.py        # návrh expozice z testovacího RAW
      calibration.py     # pořízení darků a flatů
    processing/
      raw_io.py          # načtení CR2, black/white level, CFA vzor
      channel.py         # výběr kanálu z mozaiky bez demozaikování
      calib.py           # master dark (medián), master flat, aplikace
      align.py           # detekce posunu, zarovnání
      stack.py           # průměr se sigma clipping
      binning.py
      export.py          # TIFF + preview PNG + metadata.json
      pipeline.py        # spojení kroků, zápis historie zpracování
    storage/
      layout.py          # struktura složky gelu
      metadata.py
      profiles.py        # profily barviv (TOML)
    ui/
      main_window.py
      wizard/            # 7 kroků průvodce
  profiles/              # etbr.toml, gelred.toml, sybr.toml
  tests/
    synthetic.py         # generátor syntetických gelů se známým signálem a šumem
    test_*.py
  vendor/edsdk/          # DLL a hlavičky Canon – NECOMMITOVAT (.gitignore)
  testdata/              # nafocené sady – NECOMMITOVAT
```

### Rozhraní kamery (návrh)

```python
from typing import Protocol
from pathlib import Path
import numpy as np

class Camera(Protocol):
    def connect(self) -> "CameraInfo": ...            # model, sériové č., stav napájení
    def disconnect(self) -> None: ...
    def allowed_values(self, prop: "Prop") -> list: ...  # VŽDY číst z foťáku
    def get(self, prop: "Prop"): ...
    def set(self, prop: "Prop", value) -> None: ...   # jen hodnoty z allowed_values()
    def start_live_view(self) -> None: ...
    def live_view_frame(self) -> np.ndarray: ...      # dekódovaný JPEG z EVF
    def set_live_view_zoom(self, factor: int, x: int, y: int) -> None: ...
    def stop_live_view(self) -> None: ...
    def capture(self, dest_dir: Path) -> Path: ...    # vyfotí bez AF a stáhne RAW
    def drive_focus(self, step: int) -> None: ...     # -3..+3, jen v live view (v2)
```

`Prop` je výčet: `ISO`, `TV` (čas), `AV` (clona), `IMAGE_QUALITY`, `AE_MODE`… EDSDK kódy hodnot (např. ISO 100 = `0x48`) převádí jen vrstva `camera/edsdk/`.

---

## 5. Funkce

### Hlavní obrazovka

- **Připojení:** detekce foťáku, model, stav napájení, srozumitelné chyby, automatické obnovení po uspání nebo odpojení.
- **Live view:** stream JPEG z EVF, lupa 5×/10× pro ruční ostření, mřížka, invertované zobrazení.
- **Histogram a saturace:** živý histogram vybraného kanálu a zvýraznění přepalů. Z live view jde jen o odhad, přesně se měří na RAW.
- **Expozice:** čas, clona, ISO; povolené hodnoty se načítají z foťáku. Bulb (> 30 s) až když bude potřeba.
- **Jednotlivý snímek:** rychlé vyfocení bez zpracování.

### Průvodce (7 kroků)

1. **Profil a popis gelu:** barvivo (EtBr, GelRed, SYBR…), úroveň UV (70/100 %), název, poznámka. Profil určí kanál a výchozí expozici.
2. **Kontrola scény:** bílé světlo, live view s mřížkou; checklist (zavřená skříň, zakrytý okulár, gel uprostřed, zoom na označené poloze).
3. **Ostření:** při bílém světle AF v live view na pruh markeru, pak jemné doladění po krocích podle míry ostrosti; obsluha potvrdí na 10× lupě. Potom přepnout na UV (zvolená úroveň 70/100 %).
4. **Testovací expozice:** jeden RAW; aplikace změří nejjasnější oblast ve vybraném kanálu a navrhne čas, aby byla na 70–80 % rozsahu bez saturace. Nad limit (např. 30 s) radši víc snímků.
5. **Kalibrace:** dark frames automaticky (zhasnuté světlo, zavřená skříň, stejný čas a ISO). Flat field jednou za čas pro dané uspořádání; upozornění, když je starší než limit.
6. **Série:** N snímků (výchozí 8, volba 4–32), průběh, odhad zisku SNR (√N), kontrola saturace a posunu.
7. **Kontrola a export:** výsledek vedle jednoho snímku pro srovnání šumu, mapa saturace, inverze; export jedním tlačítkem.

### Profily barviv (výchozí)

| Barvivo | Kanál | Filtr |
| --- | --- | --- |
| EtBr | R | oranžový |
| GelRed | R | oranžový |
| SYBR Safe / SYBR Green / Midori Green | G (oba G pixely) | žlutý / jantarový |

---

## 6. Zpracovací pipeline

Všechny kroky až po výsledek jsou lineární a pracují s nedemozaikovanými daty RAW.

```
Světlé RAW ×N → − master dark → ÷ normalizovaný flat → výběr kanálu
  → zarovnání (jen při posunu > 0,5 px) → průměr se sigma clipping
  → binning 2×2 (volitelný) → result.tif (16 bit, lineární)
                                  ╰┄→ volitelný denoise → samostatný soubor
```

Vzorec:

```
R = mean_σ( (L_i − D) / F̂ ),    F̂ = (F − D_F) / mean(F − D_F)
```

- `L_i` světlé snímky, `D` master dark (medián 8–16 darků se stejným časem, ISO a podobnou teplotou), `F` master flat, `D_F` dark pro flat (nebo bias).
- **Black level:** dark obsahuje i black level, takže `L − D` ho odstraní. U flatu je potřeba odečíst `D_F` (nebo aspoň black level z `raw.black_level_per_channel`), jinak bude normalizace zkreslená.
- **Saturace:** pixely ≥ `raw.white_level` (nebo blízko) označit už ve světlých snímcích, před odečtem; saturovaný pruh nejde kvantifikovat.
- **Výběr kanálu:** `raw.raw_image_visible` + `raw.raw_colors_visible` (indexy barev CFA). Pro R vzít R pixely, pro G oba G pixely (zprůměrovat 2×2 buňku → poloviční rozlišení). Žádná interpolace.
- **Sigma clipping:** například 3σ přes osu snímků, iterativně; odstraní záblesky, kosmické paprsky a jednorázové posuny.
- **Zarovnání:** `cv2.phaseCorrelate` na kanálu; pod 0,5 px se nepřevzorkovává.
- **Denoising:** medián nebo non-local means, výchozí stav vypnuto, vždy jen jako samostatný soubor. **Žádný AI denoising.**

### Kontrola správnosti (testy)

Syntetický gel: pozadí + Gaussovské pruhy se známou intenzitou + Poissonův šum + čtecí šum + hot pixely + vinětace. Test ověří, že:

- šum pozadí po stackingu N snímků klesne zhruba √N×,
- poměr intenzit pruhů zůstane zachován (linearita) v toleranci,
- hot pixely zmizí po odečtu darku,
- vinětace zmizí po flat-field korekci.

---

## 7. Integrita dat, ukládání a export

**Pravidla**

- Původní RAW se nikdy nemění.
- Kvantifikační výstup obsahuje jen lineární operace aplikované na celý obraz (odečet, dělení flatem, průměr, binning).
- Jas, kontrast, gamma a inverze mění jen náhled, nikdy data v TIFF.
- Každý krok zpracování se zapisuje do `metadata.json`.

**Struktura složky gelu**

```
2026-10-29_PCR-kontrola-primeru/
  raw/            původní CR2 (světlé snímky)
  calib/          dark frames, odkaz na použitý flat
  result.tif      16bit, lineární, jeden kanál
  preview.png     8bit náhled s nastaveným zobrazením
  metadata.json   expozice, ISO, počet snímků, profil, kroky zpracování, verze aplikace
```

- Flaty se ukládají zvlášť v knihovně kalibrací (datum, popis uspořádání).
- Kořenová složka je nastavitelná (lokálně nebo síťový disk).

---

## 8. Nasazení bez administrátora

- **Balíček:** PyInstaller **onedir** (ne onefile – častější falešné poplachy antiviru). Obsahuje Python, PySide6, numpy, rawpy a EDSDK DLL.
- **Ovladač foťáku:** není potřeba; Windows použije vestavěný WPD/PTP a EDSDK jde přes něj.
- **Visual C++ runtime:** přibalit potřebné DLL do složky aplikace.
- **Nastavení a profily:** ve složce aplikace nebo `%APPDATA%\GelCam`, nikdy v Program Files.
- **První spuštění:** SmartScreen „Neznámý vydavatel“ jde jednorázově potvrdit.
- **Test:** čistý uživatelský účet bez administrátora a PC bez VC++ runtime.
- **Zjistit předem:** jestli IT nebrání spouštění nepodepsaných aplikací z uživatelských složek nebo USB (AppLocker, GPO).

---

## 9. Technická rizika

| Riziko | Řešení |
| --- | --- |
| EDSDK události vyžadují Windows message loop ve správném vlákně | veškerá komunikace s foťákem v jednom dedikovaném vlákně s message pumpou (nebo v hlavním Qt vlákně), GUI s ním mluví přes frontu/signály; inspirace v digiCamControl |
| EDSDK nekontroluje platnost nastavovaných hodnot – špatná hodnota může foťák zablokovat (chyba 99; hlášen případ poškozeného 50D) | nastavovat **jen** hodnoty z `allowed_values()`, nesahat na nastavení mimo nutný rozsah, testovat opatrně |
| Nejnovější EDSDK nemusí podporovat 100D/500D | ověřit v etapě 0; použít verzi, se kterou fotoaparáty fungují v digiCamControl |
| Licence EDSDK | DLL ani hlavičky necommitovat do gitu; ověřit podmínky při registraci |
| 32/64 bit | 64bitový Python + 64bitové EDSDK, kontrola při startu |
| Uspání foťáku / vybití baterie během série | vypnout auto power off, síťový adaptér, obnovení série od posledního staženého snímku |
| Ohřev čipu při live view | před sérií live view vypnout, darky pořizovat hned po sérii |
| Posun gelu nebo foťáku během série | detekce posunu, zarovnání nebo varování |
| EOS Utility nebo digiCamControl drží foťák | při startu kontrola, srozumitelná hláška „zavřete jinou aplikaci, která používá foťák“ |
| Opotřebení závěrky | rozumné výchozí N, počítadlo snímků |
| Ostřicí kroužek nedosažitelný, AF u slabé fluorescence selhává | ostřit při bílém světle, softwarové doladění po krocích, spoušť bez AF, kontrola ostrosti na začátku session |
| Ostření ujede po změně zoomu nebo po vypnutí foťáku | po každé změně zoomu a na začátku session přeostřit; zoom držet na označené poloze |
| Světlo okulárem při dlouhé expozici | zakrýt okulár; upozornění v průvodci |

---

## 10. Etapy vývoje

Celkem zhruba 4–6 týdnů soustředěné práce; odhady jsou orientační. Etapy 2 a 1 (nad MockCamera) jdou dělat ještě před schválením EDSDK.

| Etapa | Obsah | Hotovo, když | Odhad |
| --- | --- | --- | --- |
| P. Příprava | repo, `uv`, struktura, CI testy; nafocení testovacích sad přes digiCamControl; žádost o EDSDK | repo běží, testovací data jsou k dispozici | 1 den |
| 2. Pipeline | `processing/` + CLI nad uloženými RAW, syntetické testy | syntetický test potvrdí zisk SNR ≈ √N a linearitu | 3–5 dní |
| 1a. GUI nad simulací | rozhraní `Camera`, `MockCamera`, hlavní okno, live view, histogram | GUI běží bez foťáku | 3–4 dny |
| 0. Ověření EDSDK | skript: připojení, čtení povolených hodnot, nastavení času a ISO, vyfocení, stažení RAW, jeden snímek live view | funguje se 100D (a 500D) | 1–2 dny |
| 1b. EdsdkCamera | implementace rozhraní nad EDSDK, vlákno s message loop, obnovení spojení, prodlužování časovače vypnutí, **AF v live view a posun ostření po krocích** | hlavní obrazovka funguje se skutečným 100D a umí zaostřit | 4–6 dní |
| 3. Průvodce | 7 kroků, návrh expozice, automatické darky, série | obsluha bez instrukcí pořídí zpracovaný snímek | 5 dní |
| 4. Profily a export | profily barviv, knihovna flatů, metadata, struktura složek | výstup projde pravidly integrity | 3–5 dní |
| 5. Pilot | testy na skutečných gelech, PyInstaller balíček, test bez admina | týden provozu bez blokující chyby | 1–2 týdny průběžně |

### Testovací data k nafocení hned (přes digiCamControl, RAW)

- 16 světlých snímků jednoho gelu (stejný čas, ISO 100–200, live view vypnutý),
- 16 darků se stejným časem a ISO (transiluminátor vypnutý, nebo krytka),
- 8 flatů (rovnoměrně svítící deska nebo prázdný gel s barvivem, ve stejné geometrii) + 8 darků pro flaty,
- 1 sada s úmyslně přepáleným markerem (test detekce saturace),
- volitelně 1 sada s malým posunem gelu (test zarovnání),
- zapsat si barvivo, filtr, čas, ISO, clonu, objektiv a vzdálenost.

---

## 11. Otevřené otázky

- [x] Sestava: kovová skříň, foťák shora, UV 70/100 % + bílé světlo, pevný oranžový filtr, ostření jen AF.
- [ ] Jaká barviva se používají? (Při SYBR ověřit, kolik signálu projde oranžovým filtrem.)
- [ ] Jaký objektiv (model, STM?) a v jaké poloze zoomu se fotí?
- [ ] Vlnová délka UV (302/312/365 nm) a odkud svítí bílé světlo (zespodu přes konverzní desku, nebo shora)?
- [ ] Jaké jsou parametry oranžového filtru (typ, hrana propustnosti)?
- [ ] Kdo bude aplikaci obsluhovat, jazyk rozhraní?
- [ ] Kam ukládat výsledky (lokálně, síťový disk, elektronický laboratorní deník)?
- [ ] Jedno PC, nebo víc stanic?
- [ ] Python + PySide6 (výchozí), nebo C#?
- [ ] Patří do v1 jednoduchá kvantifikace pruhů, nebo zůstane ve Fiji?
- [ ] Spravuje laboratorní PC IT? Nebrání spouštění nepodepsaných aplikací?

---

## 12. Do budoucna

### Monochromatická kamera místo zrcadlovky

Výhody pro gely: bez Bayerovy masky (všechny pixely sbírají emisi barviva), chlazení (stabilní, opakovatelné darky), elektronická závěrka, jednoduché SDK s Python wrapperem. Nevýhoda: obvykle potřebuje nainstalovaný USB ovladač (jednorázově administrátor). Architektura GelCam to unese – stačí nová implementace `Camera` (např. `AsiCamera` přes `zwoasi`); pipeline se zjednoduší (data jsou rovnou mono a lineární).

Ceny zjištěné 30. 10. 2026 (evropští prodejci, s DPH, orientační):

| Model | Typ | Cena |
| --- | --- | --- |
| ZWO ASI678MM | mono, nechlazená, IMX678, 8,3 MP, 12 bit | ~380–425 € |
| ZWO ASI533MM Pro | mono, chlazená, IMX533 1" 3008×3008, zero amp glow; potřebuje zdroj 12 V / 3 A | ~1 285–1 350 € |
| QHY533M | mono, chlazená, IMX533 | ~1 199 € v akci, běžně ~1 450 € |
| Player One Ares-M Pro | mono, chlazená, IMX533 | ~1 409 € |
| Basler ace 2 a2A2600-64umBAS | průmyslová mono, 5,6 MP, napájení z USB, C-mount, SDK pypylon | ~569 $ (USA) |

Doporučení: ASI533MM Pro nebo QHY533M; levný test přínosu mono kamery: ASI678MM. K tomu objektiv (C-mount nebo adaptér Canon EF) a u chlazených zdroj 12 V.

### Softwarový autofokus (přesunuto do v1)

Live view s lupou na pruh markeru → kroky `DriveLensEvf` (Near/Far 1–3) → míra ostrosti (rozptyl Laplaciánu) → hledání maxima hrubě, pak jemně. Objektiv musí být v AF; při focení použít spoušť bez AF. Kvůli nedosažitelnému ostřicímu kroužku je to ve v1 jediný způsob ostření (viz kap. 3).

### Rychlé ověření bez programování

Série přes digiCamControl nebo N.I.N.A. → kalibrace a stacking v Sirilu (zarovnání vypnout, export lineárně). Ukáže reálný zisk na vašich gelech.

---

## 13. Odkazy

- Canon Developer Programme (EDSDK): registrace přes web Canon (Canon Developer Community / Developer Programme pro Evropu).
- digiCamControl (referenční implementace EDSDK v C#): https://github.com/dukus/digiCamControl
- edsdk-python (Jiloc): https://github.com/Jiloc/edsdk-python
- pyedsdk (PyPI): https://pypi.org/project/pyedsdk/
- edsdk4j (varování k chybě 99): https://github.com/WolfgangFahl/edsdk4j
- Siril: https://siril.org
- N.I.N.A.: https://nighttime-imaging.eu
- rawpy: https://pypi.org/project/rawpy/
- openIVIS (PLoS ONE 2024): https://doi.org/10.1371/journal.pone.0299875

---

## 14. Úvodní prompt pro první session v Claude Code

> Přečti si `CLAUDE.md` a `docs/GELCAM_PLAN.md`. Začínáme etapou „P. Příprava“ a „2. Pipeline“. Založ projekt přes `uv` (Python 3.12 x64) se strukturou z kapitoly 4, `.gitignore` pro `vendor/edsdk/` a `testdata/`, a napiš generátor syntetických gelů (`tests/synthetic.py`) a první testy pro stacking a dark frame. Testovací RAW sady jsou ve složce `testdata/`. Ptej se, když narazíš na nejasnost v plánu.
