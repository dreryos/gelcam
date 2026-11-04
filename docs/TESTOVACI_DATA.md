# Návod: nafocení testovacích dat pro GelCam

Testovací sady slouží k vývoji a ověření zpracovací pipeline (dark, flat, stacking, výběr kanálu, saturace, zarovnání) dřív, než aplikace umí ovládat foťák. Fotí se na kartu nebo přes digiCamControl, výsledkem jsou soubory CR2.

Celé focení zabere asi hodinu a zabere kolem 3 GB (jeden CR2 ze 100D má zhruba 25 MB).

---

## 1. Příprava

- **Gely:** ideálně dva.
  - **Gel A – běžný:** marker + několik PCR produktů, jak ho běžně fotíte.
  - **Gel B – ředicí řada** (velmi doporučeno): stejný produkt nebo marker v dvojnásobném ředění přes 6–8 jamek (např. 100 → 1,5 ng). Ukáže linearitu a o kolik stacking posune mez detekce.
- **Prázdný gel** stejné tloušťky a barvení, bez DNA (pro flat field), případně rovnoměrně svítící deska.
- Foťák na **pevném stativu nebo držáku**, který se během celého focení nehne.
- **Emisní filtr** před objektivem (oranžový pro EtBr/GelRed, žlutý pro SYBR) a zatemnění, pokud je máte. Pokud ne, foťte bez nich, ale zapište to.
- Nabitá baterie nebo síťový adaptér, prázdná karta.
- Bezpečnost: ochranný štít proti UV, rukavice při práci s EtBr; foťáku se během expozic nedotýkat.

---

## 2. Nastavení fotoaparátu (Canon EOS 100D)

Nastavení se během **všech sad nemění**, pokud není u sady uvedeno jinak.

| Nastavení | Hodnota | Proč |
| --- | --- | --- |
| Režim | **M** (manuál) | stejná expozice u všech snímků |
| Kvalita | **RAW** (RAW + JPEG L je v pořádku pro rychlý náhled) | pipeline pracuje s RAW |
| ISO | **100** | nejnižší šum; delší čas je lepší než vyšší ISO |
| Clona | **f/5,6–f/8**, pevně | ostrost a hloubka ostrosti; při slabém signálu f/4–5,6 |
| Čas | podle testovacího snímku (kap. 3), max. 30 s | |
| Ostření | v live view na **10× lupě** nad pruhem markeru, pak přepínač na objektivu na **MF** | ostření se mezi snímky nesmí změnit |
| Zoom objektivu | pevně (zapsat ohniskovou vzdálenost), ideálně přelepit páskou | flat platí jen pro stejné nastavení |
| Stabilizace (IS) | **vypnout** | na stativu může rozostřit |
| Redukce šumu dlouhé expozice | **vypnout** | jinak foťák sám odečítá vlastní dark, zdvojnásobí čas a zkreslí data |
| Redukce šumu vysokého ISO | vypnout | |
| Auto Lighting Optimizer | vypnout | |
| Priorita vysokých jasů (HTP) | vypnout | mění chování ISO |
| Korekce vinětace / aberace objektivu | vypnout | vinětaci řeší flat field |
| Vyvážení bílé | pevně (např. Denní světlo) | na RAW nemá vliv, ale JPEG náhledy budou konzistentní |
| Styl snímků | Neutrální | jen pro JPEG a live view |
| Automatické vypnutí | **Zakázat** | foťák se nesmí uspat uprostřed série |
| Spouštění | **samospoušť 2 s** nebo z PC (digiCamControl) | bez otřesů od ruky |
| Live view | během sérií **vypnutý** | čip se v live view ohřívá a roste tepelný šum |

Pokud menu nabízí **zámek zrcadla**, zapni ho (se samospouští 2 s), jinak foť přes live view nebo z PC.

---

## 3. Volba expozice

1. Zapni transiluminátor, vyfoť jeden testovací snímek gelu A.
2. Podívej se na histogram a blikající přepaly na displeji. Nejjasnější pruh (obvykle marker) má být zhruba ve **2/3 histogramu a nesmí blikat jako přepálený**.
3. Uprav čas a zopakuj. Histogram foťáku počítá z JPEG, takže je spíš konzervativní; v RAW je rezerva.
4. Pokud by správný čas vyšel přes 30 s, otevři clonu (f/4–5,6). ISO nech na 100.
5. Výsledný čas zapiš a **dál ho neměň** (kromě sad, kde je uvedeno jinak).

Mezi rozsvícením transiluminátoru a první expozicí počkej asi minutu, než se ustálí jas lampy.

---

## 4. Sady snímků

Foť v tomto pořadí. Darky vždy hned po světlých snímcích, aby měl čip stejnou teplotu.

| # | Sada | Počet | Jak | Složka |
| --- | --- | --- | --- | --- |
| 1 | **Světlé – gel A** | 16 | transiluminátor zapnutý, čas z kap. 3, nic se nehýbe | `lights/` |
| 2 | **Darky** | 16 | **hned po sadě 1**, stejný čas a ISO, transiluminátor vypnutý, krytka na objektivu, box zavřený | `darks/` |
| 3 | **Saturace** | 4 | gel A, čas 4× delší (nebo otevřenější clona), marker musí být přepálený | `saturation/` |
| 4 | **Posun** | 8 | gel A, mezi snímky gel posuň o kousek (≈ 0,5–1 mm, nebo ťukni do stolu); po 4. snímku větší posun ≈ 3 mm | `shift/` |
| 5 | **Světlé – gel B** (ředicí řada) | 16 | čas nastav podle nejsilnějšího pruhu gelu B (kap. 3) | `dilution/lights/` |
| 6 | **Darky pro gel B** | 16 | hned po sadě 5, stejný čas jako sada 5 | `dilution/darks/` |
| 7 | **Flaty** | 16 | prázdný gel (nebo svítící deska) **na stejném místě**, stejné ostření, clona, filtr a zoom; čas zvol tak, aby histogram byl **v polovině**, bez přepalů | `flats/` |
| 8 | **Darky pro flaty** | 16 | hned po sadě 7, stejný čas jako flaty, krytka | `flat_darks/` |
| 9 | **Bias** | 16 | nejkratší čas (1/4000 s), ISO 100, krytka | `bias/` |
| 10 | *(volitelné)* **ISO srovnání** | 2 × 8 | gel A při ISO 800 a čase 8× kratším | `iso800/` |
| 11 | *(volitelné)* **500D** | sady 1, 2, 7, 8 | totéž s EOS 500D (vlastní nastavení, zapsat zvlášť) | `500d/…` |

Minimum, bez kterého se vývoj neobejde: **sady 1, 2, 7, 8**. Sady 3 a 4 jsou pro testy saturace a zarovnání, sada 5–6 pro ověření linearity a meze detekce.

### Tipy k flatům

- Nejlepší flat pro fluorescenci je **prázdný gel se stejným barvivem** na transiluminátoru: zachytí nerovnoměrnost lampy i vinětaci.
- Bílá svítící deska (konverzní deska) zachytí jen vinětaci objektivu, ne nerovnoměrnost UV lampy. Je to druhá nejlepší volba.
- Flat **nesmí být přepálený** ani moc tmavý: cíl je kolem poloviny histogramu.
- Pokud se mezi focením gelu a flatů pohne foťák, ostření nebo zoom, flat je k ničemu – raději nafoť flaty znovu.

---

## 5. Struktura složek a záznam

Soubory zkopíruj z karty bez přejmenování do:

```
testdata/
  2026-11-XX_sada01/
    notes.md
    lights/
    darks/
    saturation/
    shift/
    dilution/
      lights/
      darks/
    flats/
    flat_darks/
    bias/
```

Do `notes.md` zapiš:

```
Datum a čas:
Fotoaparát: Canon EOS 100D (firmware:)
Objektiv a ohnisková vzdálenost:
Vzdálenost objektivu od gelu:
Clona / ISO:
Čas – lights: ... s, flats: ... s, gel B: ... s
Barvivo a koncentrace:
Transiluminátor (UV 302/365 nm, modrý):
Emisní filtr: ano/ne, typ:
Zatemnění: ano/ne
Gel A – obsah jamek:
Gel B – ředicí řada (množství v jamkách):
Teplota v místnosti (přibližně):
Poznámky / co se pokazilo:
```

Složka `testdata/` je v `.gitignore`, do repozitáře se nenahrává.

---

## 6. Rychlá kontrola po focení

- Počty souborů v každé složce sedí.
- Náhodně otevři jeden světlý snímek: je ostrý a marker není přepálený.
- Jeden dark je opravdu tmavý (ne zapomenutá zapnutá lampa nebo sundaná krytka).
- Flat je rovnoměrný a bez struktury gelu nebo nečistot.
- V EXIF všech snímků jedné sady je stejný čas, clona a ISO.
