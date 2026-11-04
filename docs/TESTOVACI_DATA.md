# Návod: nafocení testovacích dat pro GelCam

Testovací sady slouží k vývoji a ověření zpracovací pipeline (dark, flat, stacking, výběr kanálu, saturace, zarovnání) dřív, než aplikace umí ovládat foťák. Fotí se na kartu nebo přes digiCamControl, výsledkem jsou soubory CR2.

Návod počítá s naší sestavou: **kovová skříň, Canon EOS 100D zanořený shora, ručně měnitelný zoom, nedosažitelný ostřicí kroužek, UV lampa 70/100 %, bílé světlo, pevný oranžový filtr.**

Focení zabere asi hodinu a kolem 4 GB (jeden CR2 ze 100D má zhruba 25 MB).

---

## 1. Příprava

- **Gely:** ideálně dva.
  - **Gel A – běžný:** marker + několik PCR produktů, jak ho běžně fotíte.
  - **Gel B – ředicí řada** (velmi doporučeno): stejný produkt nebo marker v dvojnásobném ředění přes 6–8 jamek (např. 100 → 1,5 ng). Ukáže linearitu a o kolik stacking posune mez detekce.
- **Prázdný gel** stejné tloušťky a barvení, bez DNA (pro flat field). Měl by pokrýt celou plochu, kterou foťák vidí.
- Foťák napájený **síťovým adaptérem (ACK-E15)** nebo plně nabitou baterií, prázdná karta.
- **Zakryj okulár hledáčku** (krytka na řemenu, nebo neprůhledná páska). Okulár míří ven ze skříně a při dlouhé expozici jím může prosvítat světlo z místnosti.
- Bezpečnost: rukavice při práci s EtBr, skříň při zapnutém UV zavřená.

---

## 2. Nastavení fotoaparátu (Canon EOS 100D)

Nastavení se během **všech sad nemění**, pokud není u sady uvedeno jinak.

| Nastavení | Hodnota | Proč |
| --- | --- | --- |
| Režim | **M** (manuál) | stejná expozice u všech snímků |
| Kvalita | **RAW** (RAW + JPEG L je v pořádku pro rychlý náhled) | pipeline pracuje s RAW |
| ISO | **100** | nejnižší šum; delší čas je lepší než vyšší ISO |
| Clona | **f/5,6–f/8**, pevně | ostrost a hloubka ostrosti; při slabém signálu f/4–5,6 |
| Čas | podle testovacího snímku (kap. 4), max. 30 s | |
| Zoom | jedna poloha pro všechny sady, **označit ji na objektivu** (fix, páska) a zapsat ohniskovou vzdálenost | flat platí jen pro stejný zoom; změna zoomu posune i ostření |
| Režim AF | **One-Shot**, v live view **FlexiZone-Single** | jeden bod, který umístíš na pruh |
| Ostření při spouštění | přesunout AF na tlačítko * (uživatelské funkce → *Tlačítko spouště / blokování AE* → varianta s AF na tlačítku \*) | aby foťák při spuštění znovu neostřil podle slabé fluorescence |
| Stabilizace (IS) | **vypnout** | foťák je pevně uchycený |
| Redukce šumu dlouhé expozice | **vypnout** | jinak foťák sám odečítá vlastní dark, zdvojnásobí čas a zkreslí data |
| Redukce šumu vysokého ISO | vypnout | |
| Auto Lighting Optimizer | vypnout | |
| Priorita vysokých jasů (HTP / D+) | vypnout | mění chování ISO |
| Korekce vinětace / aberace objektivu | vypnout | vinětaci řeší flat field |
| Vyvážení bílé | pevně (např. Denní světlo) | na RAW nemá vliv, JPEG náhledy budou konzistentní |
| Styl snímků | Neutrální | jen pro JPEG a live view |
| Úspora energie | **nejdelší dostupný čas** (15 min), případně Zakázat | foťák se nesmí uspat uprostřed série; po probuzení zkontroluj ostření |
| Spouštění | **samospoušť 2 s** nebo z PC (digiCamControl) | bez otřesů od ruky |
| Live view | jen na ostření a kontrolu; **během sérií vypnutý** | čip se v live view ohřívá a roste tepelný šum |

Názvy položek menu se mohou mírně lišit podle jazyka a verze firmwaru.

---

## 3. Ostření (ostřicí kroužek není dosažitelný)

1. Zapni **bílé světlo**, polož gel A na místo a zavři skříň.
2. Nastav zoom na označenou polohu.
3. Zapni live view, posuň bod AF (FlexiZone-Single, dotykem na displeji) na **ostrý okraj pruhu markeru nebo okraj jamek**.
4. Zaostři (tlačítko * nebo polovičním stiskem, podle nastavení).
5. Zkontroluj na **10× lupě**. Když to nesedí, zaostři znovu na jiný kontrastní detail (okraj gelu, text na podložce ve stejné rovině).
6. Vypni live view. **Dál už nic neostřuj** a neměň zoom.
7. Přepni na UV. Ostření se při přepnutí světla nemění.

Když se foťák mezi sadami uspí nebo vypne, ostření před další sadou zkontroluj v live view (u některých objektivů se po vypnutí může posunout).

---

## 4. Volba expozice

1. Přepni na **UV 100 %**, počkej asi minutu, než se jas lampy ustálí.
2. Vyfoť testovací snímek gelu A.
3. Podívej se na histogram a blikající přepaly. Nejjasnější pruh (obvykle marker) má být zhruba ve **2/3 histogramu a nesmí blikat jako přepálený**. Histogram foťáku počítá z JPEG, takže je spíš konzervativní; v RAW je rezerva.
4. Uprav čas a zopakuj. Pokud by správný čas vyšel přes 30 s, otevři clonu (f/4–5,6). ISO nech na 100.
5. Výsledný čas zapiš a **dál ho neměň** (kromě sad, kde je uvedeno jinak).

---

## 5. Sady snímků

Foť v tomto pořadí. Darky vždy hned po světlých snímcích, aby měl čip stejnou teplotu.
**Dark = zhasnuté UV i bílé světlo, zavřená skříň, zakrytý okulár** (krytka na objektiv není potřeba ani možná).

| # | Sada | Počet | Jak | Složka |
| --- | --- | --- | --- | --- |
| 1 | **Bílé světlo – gel A** | 2 | bílé světlo, krátký čas podle histogramu; dokumentace polohy gelu | `white/` |
| 2 | **Světlé – gel A, UV 100 %** | 16 | čas z kap. 4, nic se nehýbe | `lights/` |
| 3 | **Darky** | 16 | **hned po sadě 2**, stejný čas a ISO, světla zhasnutá | `darks/` |
| 4 | **Světlé – gel A, UV 70 %** | 8 | stejný čas jako sada 2 (ukáže poměr úrovní lampy) | `uv70/` |
| 5 | **Saturace** | 4 | gel A, UV 100 %, čas 4× delší (nebo otevřenější clona), marker musí být přepálený | `saturation/` |
| 6 | **Posun** | 8 | gel A, mezi snímky gel posuň o kousek (≈ 0,5–1 mm); po 4. snímku větší posun ≈ 3 mm | `shift/` |
| 7 | **Světlé – gel B** (ředicí řada) | 16 | UV 100 %, čas podle nejsilnějšího pruhu gelu B (kap. 4) | `dilution/lights/` |
| 8 | **Darky pro gel B** | 16 | hned po sadě 7, stejný čas jako sada 7 | `dilution/darks/` |
| 9 | **Flaty, UV 100 %** | 16 | prázdný gel **na stejném místě**, stejný zoom, ostření a clona; čas tak, aby histogram byl **v polovině**, bez přepalů | `flats/` |
| 10 | **Darky pro flaty** | 16 | hned po sadě 9, stejný čas jako flaty | `flat_darks/` |
| 11 | **Flaty, UV 70 %** | 8 | jako sada 9 při UV 70 %, vlastní čas | `flats_uv70/` |
| 12 | **Bias** | 16 | nejkratší čas (1/4000 s), ISO 100, světla zhasnutá | `bias/` |
| 13 | *(volitelné)* **ISO srovnání** | 8 | gel A, UV 100 %, ISO 800 a čas 8× kratší | `iso800/` |
| 14 | *(volitelné)* **500D** | sady 2, 3, 9, 10 | totéž s EOS 500D (vlastní nastavení, zapsat zvlášť) | `500d/…` |

Minimum, bez kterého se vývoj neobejde: **sady 2, 3, 9, 10**. Sady 5 a 6 jsou pro testy saturace a zarovnání, sady 7–8 pro linearitu a mez detekce, sady 4 a 11 pro rozdíl mezi úrovněmi UV.

Pokud používáte i **SYBR** (nebo jiné zelené barvivo), nafoť sady 2, 3, 9 a 10 i s gelem obarveným SYBR. Oranžový filtr velkou část jeho emise odřízne a z dat zjistíme, jestli je lepší R, nebo G kanál.

### Tipy k flatům

- Flat se dělá **prázdným gelem se stejným barvivem** při stejné úrovni UV: zachytí nerovnoměrnost lampy i vinětaci objektivu.
- **Bílé světlo jako flat nepoužívej:** má jiné spektrum i rozložení než UV.
- Flat **nesmí být přepálený** ani moc tmavý: cíl je kolem poloviny histogramu.
- Pokud se mezi focením gelu a flatů změní zoom nebo ostření, flat je k ničemu – raději nafoť flaty znovu.

---

## 6. Struktura složek a záznam

Soubory zkopíruj z karty bez přejmenování do:

```
testdata/
  2026-11-XX_sada01/
    notes.md
    white/
    lights/
    darks/
    uv70/
    saturation/
    shift/
    dilution/
      lights/
      darks/
    flats/
    flat_darks/
    flats_uv70/
    bias/
```

Do `notes.md` zapiš:

```
Datum a čas:
Fotoaparát: Canon EOS 100D (firmware:)
Objektiv (model) a ohnisková vzdálenost (poloha zoomu):
Clona / ISO:
Čas – lights: ... s, uv70: ... s, gel B: ... s, flats: ... s, flats_uv70: ... s
Barvivo a koncentrace:
UV lampa – vlnová délka (302/312/365 nm, pokud je známá):
Bílé světlo – zespodu, nebo shora:
Oranžový filtr – typ, pokud je znám:
Okulár zakrytý: ano/ne
Gel A – obsah jamek:
Gel B – ředicí řada (množství v jamkách):
Teplota v místnosti (přibližně):
Poznámky / co se pokazilo:
```

Složka `testdata/` je v `.gitignore`, do repozitáře se nenahrává.

---

## 7. Rychlá kontrola po focení

- Počty souborů v každé složce sedí.
- Náhodně otevři jeden světlý snímek: je ostrý a marker není přepálený.
- Jeden dark je opravdu tmavý (žádné zapomenuté světlo ani prosvítání okulárem).
- Flat je rovnoměrný a bez struktury gelu nebo nečistot.
- V EXIF všech snímků jedné sady je stejný čas, clona, ISO a ohnisková vzdálenost.
