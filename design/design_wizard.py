
"""Mockup sedmikrokového průvodce GelCam ve FigCraftu.

Spuštění v `repl`:
    ns = {}
    exec(open("design_wizard.py", encoding="utf-8").read(), ns)
    frames = ns["build_all"](host.mcp)

Návrh je skriptovaný schválně: změna stylu je úprava jedné konstanty a přestavba
celé sady, ne překreslování sedmi obrazovek.
"""

W, H = 960, 640
GAP = 80

BG, PANEL, LINE = "#F2F2F2", "#FFFFFF", "#D8D8D8"
INK, DIM, ACC, MUTEBG = "#1A1A1A", "#6B6B6B", "#2563D9", "#FAFAFA"
OK, WARN, BAD = "#177A45", "#9E5100", "#C0392B"
# Contrast checked 10 Nov 2026: OK, ACC, WARN, BAD, DIM >= 4.5:1 on BG, PANEL and the
# selected tint #E7EEFB; captions inside the dark preview use PV_INK (6.9:1 on DARK).
PV_INK = "#9E9E9E"
NOTE_BG, NOTE_LINE, NOTE_INK = "#FFF8E6", "#E8D6A8", "#6B5518"
DARK = "#141414"
TRANS = "#00000000"

# ------------------------------------------------------------------ jazyky
# Rozhraní je anglicky; čeština zůstává jako druhý jazyk. V aplikaci tomu bude
# odpovídat Qt tr() + .ts/.qm, tady je to prostá tabulka, aby šel mockup
# postavit v obou jazycích (build_all(mcp, lang="cs")).

STRINGS = {
 "en": {
  "title": "New gel image", "step_of": "Step {i} of 7",
  "steps": ["Profile and description", "Scene check", "Focus", "Test exposure",
            "Calibration", "Image series", "Review and export"],
  "cancel": "Cancel", "back": "Back", "continue": "Continue", "export": "Export",

  "dye": "Dye", "uv_level": "UV level", "gel_name": "Gel name", "note": "Note",
  "gel_name_val": "2026-11-10_PCR-primer-check",
  "note_ph": "optional description of samples and ladder",
  "profile_hint": "Channel R  ·  orange filter  ·  default 4 s, ISO 100, f/8",
  "s1_note1": "The profile sets the colour channel and the default exposure.",
  "s1_note2": "Changing the zoom or the UV level means a new calibration — a flat field "
              "is valid for one arrangement only.",

  "preview_white": "white light · grid", "lighting": "Lighting",
  "white_light": "White light", "uv70": "UV 70 %", "lights_off": "Lights off",
  "lighting_now": "Which light is on?",
  "lighting_manual": "switch it by hand on the cabinet, then tell the app — "
                     "the UV level decides which flat field applies",
  "mag10": "camera magnifier 10× · navigator shows the position",
  "checklist": "Before you continue",
  "chk_cabinet": "Cabinet is closed",
  "chk_gel": "Gel is centred and fully in frame",
  "chk_eyepiece": "Viewfinder eyepiece is covered",
  "chk_eyepiece_h": "otherwise room light leaks in during long exposures",
  "chk_zoom": "Zoom is at the marked position",
  "chk_zoom_h": "a flat field is valid for one position only",
  "s2_warn": "Zoom is not at the marked position — you can continue, but the flat field "
             "must be taken again.",

  "sharpness": "Sharpness", "sharp_val": "53.1",
  "sharp_hint": "variance of Laplacian in the magnifier · 5.5 before AF",
  "focus": "Focus", "run_af": "Run autofocus", "fine_steps": "Fine steps",
  "magnifier": "Magnifier",
  "s3_note1": "Focus under white light, then switch to UV 70 %. The shutter never refocuses.",
  "s3_note2": "Refocus after every zoom change and at the start of each session.",

  "test_raw": "test RAW · channel R",
  "brightest": "Brightest region", "brightest_val": "9,420 ADU",
  "of_range": "Of range", "of_range_val": "69 %",
  "saturated": "Saturated", "sat_val": "0.00 %",
  "exp_proposal": "Exposure proposal", "exp_change": "4 s  →  5 s",
  "exp_hint": "ISO 100 · f/8 · target 70–80 % of range without saturation",
  "take_test": "Take test frame", "apply_proposal": "Apply proposal",
  "s4_note": "Exposure is not extended beyond 30 s — take more frames instead.",

  "darks": "Dark frames", "darks_val": "16 × 5 s · ISO 100",
  "darks_h1": "Taken automatically right after the series, with the lights off.",
  "darks_h2": "Same exposure time and ISO as the light frames — otherwise warm pixels remain.",
  "automatic": "Automatic", "use_stored": "Use stored",
  "flat": "Flat field", "flat_val": "UV 70 % · zoom \u201cA\u201d · 8 s",
  "flat_age": "taken 46 days ago",
  "flat_src": "From the calibration library · 16 frames + 8 s darks",
  "take_new": "Take new", "pick_lib": "Pick from library",
  "s5_warn1": "The flat field is older than 30 days. It is valid only for the same geometry, "
              "zoom and UV level —",
  "s5_warn2": "if any of those changed since, take a new one.",
  "applied": "What will be applied",
  "formula": "light frames − master dark (median of 16)  ÷  normalised flat (flat − flat dark)",

  "series": "Series", "frame_count": "Frame count",
  "series_hint": "Background noise falls with √N — 8 frames means roughly 2.8× better "
                 "signal-to-noise.",
  "progress": "Progress", "progress_val": "5 / 8", "time_left": "about 21 s left",
  "sat2_val": "0.02 %", "drift": "Drift from first frame", "drift_val": "0.3 px",
  "snr_gain": "Estimated SNR gain", "snr_val": "×2.8",
  "exposure": "Exposure", "exposure_val": "5 s · ISO 100 · f/8",
  "s6_note1": "Live view stays off during the series so the sensor does not warm up.",
  "s6_note2": "Darks are taken right after the last exposure, with the camera in the same state.",

  "one_frame": "1 frame", "stack8": "Stack of 8",
  "noise1": "background noise 7.3 ADU", "noise8": "background noise 2.6 ADU",
  "invert": "Invert", "sat_map": "Saturation map",
  "preview_only": "affects the preview only; result.tif stays linear",
  "export_title": "Export", "export_dir": "2026-11-10_PCR-primer-check/",
  "export_files": "result.tif  ·  16-bit, linear, channel R, 2604 × 1738     preview.png     "
                  "metadata.json     raw/ 8× CR2     calib/ 16× dark",
 },
 "cs": {
  "title": "Nový snímek gelu", "step_of": "Krok {i} ze 7",
  "steps": ["Profil a popis gelu", "Kontrola scény", "Ostření", "Testovací expozice",
            "Kalibrace", "Série snímků", "Kontrola a export"],
  "cancel": "Zrušit", "back": "Zpět", "continue": "Pokračovat", "export": "Exportovat",

  "dye": "Barvivo", "uv_level": "Úroveň UV", "gel_name": "Název gelu", "note": "Poznámka",
  "gel_name_val": "2026-11-10_PCR-kontrola-primeru",
  "note_ph": "volitelný popis vzorků a markeru",
  "profile_hint": "Kanál R  ·  oranžový filtr  ·  výchozí 4 s, ISO 100, f/8",
  "s1_note1": "Profil určuje barevný kanál a výchozí expozici.",
  "s1_note2": "Změna zoomu nebo úrovně UV znamená novou kalibraci — flat field platí jen "
              "pro jedno uspořádání.",

  "preview_white": "bílé světlo · mřížka", "lighting": "Osvětlení",
  "white_light": "Bílé světlo", "uv70": "UV 70 %", "lights_off": "Zhasnout",
  "lighting_now": "Které světlo svítí?",
  "lighting_manual": "přepni ho ručně na skříni a pak to řekni aplikaci — "
                     "úroveň UV rozhoduje, který flat field platí",
  "mag10": "lupa foťáku 10× · navigátor ukazuje polohu",
  "checklist": "Než budeš pokračovat",
  "chk_cabinet": "Skříň je zavřená",
  "chk_gel": "Gel je uprostřed a celý v záběru",
  "chk_eyepiece": "Okulár hledáčku je zakrytý",
  "chk_eyepiece_h": "jinak jím prosvítá světlo z místnosti",
  "chk_zoom": "Zoom je na označené poloze",
  "chk_zoom_h": "flat platí jen pro jednu polohu",
  "s2_warn": "Zoom není na označené poloze — pokračovat jde, ale flat field se musí "
             "pořídit znovu.",

  "sharpness": "Ostrost", "sharp_val": "53,1",
  "sharp_hint": "rozptyl Laplaciánu v lupě · před AF 5,5",
  "focus": "Ostření", "run_af": "Spustit autofokus", "fine_steps": "Doladění po krocích",
  "magnifier": "Lupa",
  "s3_note1": "Ostři při bílém světle, pak přepni na UV 70 %. Spoušť nikdy neostří znovu.",
  "s3_note2": "Po každé změně zoomu a na začátku session se ostří znovu.",

  "test_raw": "testovací RAW · kanál R",
  "brightest": "Nejjasnější oblast", "brightest_val": "9 420 ADU",
  "of_range": "Z rozsahu", "of_range_val": "69 %",
  "saturated": "Saturováno", "sat_val": "0,00 %",
  "exp_proposal": "Návrh expozice", "exp_change": "4 s  →  5 s",
  "exp_hint": "ISO 100 · f/8 · cíl 70–80 % rozsahu bez saturace",
  "take_test": "Vyfotit testovací snímek", "apply_proposal": "Použít návrh",
  "s4_note": "Nad 30 s se expozice neprodlužuje — raději víc snímků v sérii.",

  "darks": "Dark frames", "darks_val": "16 × 5 s · ISO 100",
  "darks_h1": "Pořídí se automaticky hned po sérii, se zhasnutým světlem.",
  "darks_h2": "Stejný čas i ISO jako světlé snímky — teplé pixely jinak nezmizí.",
  "automatic": "Automaticky", "use_stored": "Použít uložené",
  "flat": "Flat field", "flat_val": "UV 70 % · zoom \u201eA\u201c · 8 s",
  "flat_age": "pořízen před 46 dny",
  "flat_src": "Z knihovny kalibrací · 16 snímků + darky 8 s",
  "take_new": "Pořídit nový", "pick_lib": "Vybrat z knihovny",
  "s5_warn1": "Flat field je starší než 30 dní. Platí jen pro stejnou geometrii, zoom "
              "a úroveň UV —",
  "s5_warn2": "pokud se od té doby něco z toho změnilo, pořiď nový.",
  "applied": "Co se použije",
  "formula": "světlé snímky − master dark (medián 16)  ÷  normalizovaný flat (flat − dark flatu)",

  "series": "Série", "frame_count": "Počet snímků",
  "series_hint": "Šum pozadí klesá s √N — 8 snímků znamená zhruba 2,8× lepší poměr "
                 "signál/šum.",
  "progress": "Průběh", "progress_val": "5 / 8", "time_left": "zbývá asi 21 s",
  "sat2_val": "0,02 %", "drift": "Posun proti prvnímu", "drift_val": "0,3 px",
  "snr_gain": "Odhad zisku SNR", "snr_val": "×2,8",
  "exposure": "Expozice", "exposure_val": "5 s · ISO 100 · f/8",
  "s6_note1": "Live view je po dobu série vypnutý, aby se nehřál čip.",
  "s6_note2": "Darky se pořídí hned po poslední expozici, ve stejném stavu foťáku.",

  "one_frame": "1 snímek", "stack8": "Stack 8 snímků",
  "noise1": "šum pozadí 7,3 ADU", "noise8": "šum pozadí 2,6 ADU",
  "invert": "Inverze", "sat_map": "Mapa saturace",
  "preview_only": "mění jen náhled, data v result.tif zůstávají lineární",
  "export_title": "Export", "export_dir": "2026-11-10_PCR-kontrola-primeru/",
  "export_files": "result.tif  ·  16 bit, lineární, kanál R, 2604 × 1738     preview.png     "
                  "metadata.json     raw/ 8× CR2     calib/ 16× dark",
 },
}


KROKY = ["Profil a popis gelu", "Kontrola scény", "Ostření", "Testovací expozice",
         "Kalibrace", "Série snímků", "Kontrola a export"]


def make_N(mcp, server="figcraft"):
    def N(type, parent=None, **kw):
        if parent is not None:
            kw["parent"] = parent
        if type == "frame" and "fills" not in kw.get("props", {}):
            kw.setdefault("props", {}).setdefault("fill", TRANS)
        r = mcp(server, "create_node", type=type, **kw)
        return r["id"] if isinstance(r, dict) and "id" in r else r
    return N


# ---------------------------------------------------------------- stavební prvky

def row(N, parent, gap=10, align="center", fill=TRANS, **props):
    p = {"layout": "horizontal", "gap": gap, "crossAlign": align,
         "sizingH": "hug", "sizingV": "hug", "fill": fill}
    p.update(props)
    return N("frame", parent, props=p)


def col(N, parent, gap=10, fill=TRANS, **props):
    p = {"layout": "vertical", "gap": gap, "sizingH": "hug", "sizingV": "hug", "fill": fill}
    p.update(props)
    return N("frame", parent, props=p)


def text(N, parent, s, size=13, fill=INK, width=None, wrap=False, **props):
    p = {"fontSize": size, "fill": fill}
    if wrap:                      # text sám nezalamuje, musí dostat šířku rodiče
        p["sizingH"] = "fill"
    p.update(props)
    kw = {"props": p}
    if width:
        kw["width"] = width
    return N("text", parent, text=s, **kw)


def panel(N, parent, title=None, gap=10, **props):
    p = {"fill": PANEL, "stroke": LINE, "strokeWeight": 1, "cornerRadius": 6,
         "layout": "vertical", "gap": gap, "padding": 16,
         "sizingH": "fill", "sizingV": "hug"}
    p.update(props)
    f = N("frame", parent, props=p)
    if title:
        text(N, f, title, 13, INK, fontStyle="Bold")
    return f


def note(N, parent, lines, kind="info"):
    bg, ln, ink = {"info": (NOTE_BG, NOTE_LINE, NOTE_INK),
                   "err": ("#FDECEA", "#F0C0BA", "#8C2A1E")}[kind]
    f = N("frame", parent, props={"fill": bg, "stroke": ln, "strokeWeight": 1,
          "cornerRadius": 5, "layout": "vertical", "gap": 5, "padding": 14,
          "sizingH": "fill", "sizingV": "hug"})
    for s in lines:
        text(N, f, s, 12.5, ink, wrap=True)
    return f


def button(N, parent, label, kind="normal"):
    fill = {"normal": PANEL, "primary": ACC, "ghost": TRANS}[kind]
    f = N("frame", parent, props={
        "fill": fill, "stroke": "#BFBFBF" if kind == "normal" else TRANS,
        "strokeWeight": 1, "cornerRadius": 4, "layout": "horizontal",
        "padding": [8, 18, 8, 18], "sizingH": "hug", "sizingV": "hug"})
    text(N, f, label, 13,
         "#FFFFFF" if kind == "primary" else ("#A8A8A8" if kind == "ghost" else INK))
    return f


def small_button(N, parent, label, on=False):
    f = N("frame", parent, props={
        "fill": "#E7EEFB" if on else PANEL, "stroke": ACC if on else "#BFBFBF",
        "strokeWeight": 1, "cornerRadius": 4, "layout": "horizontal",
        "padding": [5, 11, 5, 11], "sizingH": "hug", "sizingV": "hug"})
    text(N, f, label, 12, ACC if on else INK)
    return f


def dropdown(N, parent, label, width=240):
    f = N("frame", parent, width=width, props={
        "fill": PANEL, "stroke": "#BFBFBF", "strokeWeight": 1, "cornerRadius": 4,
        "layout": "horizontal", "padding": [7, 10, 7, 10], "gap": 8,
        "mainAlign": "spaceBetween", "crossAlign": "center",
        "sizingH": "fixed", "sizingV": "hug"})
    text(N, f, label, 13, INK)
    text(N, f, "▾", 11, DIM)
    return f


def textfield(N, parent, s, width=380, dim=False):
    f = N("frame", parent, width=width, props={
        "fill": PANEL, "stroke": "#BFBFBF", "strokeWeight": 1, "cornerRadius": 4,
        "layout": "horizontal", "padding": [7, 10, 7, 10],
        "sizingH": "fixed", "sizingV": "hug"})
    text(N, f, s, 13, DIM if dim else INK)
    return f


def radio(N, parent, label, on):
    f = row(N, parent, gap=7)
    N("ellipse", f, width=13, height=13,
      props={"fill": PANEL, "stroke": ACC if on else "#9A9A9A", "strokeWeight": 5 if on else 1,
             "strokeAlign": "inside"})   # selected = thick ring, readable without colour
    text(N, f, label, 13)
    return f


def checkbox(N, parent, label, on, hint=None):
    f = row(N, parent, gap=9, align="min")
    box = N("rectangle", f, width=14, height=14, props={
        "fill": ACC if on else PANEL, "stroke": ACC if on else "#9A9A9A",
        "strokeWeight": 1, "cornerRadius": 3})
    c = col(N, f, gap=2)
    text(N, c, label, 13)
    if hint:
        text(N, c, hint, 11.5, DIM)
    return f


def field_row(N, parent, label, build_ctl, label_w=110):
    r = N("frame", parent, props={"layout": "horizontal", "gap": 14, "sizingH": "fill",
                                  "sizingV": "hug", "crossAlign": "center", "fill": TRANS})
    text(N, r, label, 13, INK, width=label_w)
    build_ctl(r)
    return r


def stat(N, parent, label, value, color=INK):
    c = col(N, parent, gap=3)
    text(N, c, label, 11.5, DIM)
    text(N, c, value, 15, color)
    return c


def preview(N, parent, w, h, label="živý náhled", radius=4):
    f = N("frame", parent, width=w, height=h, props={
        "fill": DARK, "cornerRadius": radius, "sizingH": "fixed", "sizingV": "fixed",
        "clip": True})
    text(N, f, label, 12, PV_INK)
    return f


def grid_lines(N, parent, w, h, step_x, step_y, color="#FFFFFF", opacity=0.16):
    x = step_x
    while x < w:
        N("rectangle", parent, x=x, y=0, width=1, height=h,
          props={"fill": color, "opacity": opacity})
        x += step_x
    y = step_y
    while y < h:
        N("rectangle", parent, x=0, y=y, width=w, height=1,
          props={"fill": color, "opacity": opacity})
        y += step_y


def band(N, parent, x, y, w, h, color="#D8A0A0", opacity=1.0, radius=2):
    return N("rectangle", parent, x=x, y=y, width=w, height=h,
             props={"fill": color, "opacity": opacity, "cornerRadius": radius})


def histogram(N, parent, w=300, h=86, clipped=False):
    f = N("frame", parent, width=w, height=h, props={
        "fill": "#1C1C1C", "cornerRadius": 4, "layout": "horizontal", "gap": 1,
        "padding": [8, 8, 8, 8], "crossAlign": "max", "sizingH": "fixed", "sizingV": "fixed"})
    import math
    n = 44
    for i in range(n):
        t = i / (n - 1)
        v = math.exp(-((t - 0.18) ** 2) / 0.012) * 0.95 + math.exp(-((t - 0.62) ** 2) / 0.02) * 0.38
        v = max(v, 0.03)
        hh = max(2, v * (h - 20))
        c = BAD if (clipped and i >= n - 2) else "#8FB4F2"
        N("rectangle", f, width=5, height=hh, props={"fill": c, "cornerRadius": 1})
    return f


def progress(N, parent, frac, w=420, h=8):
    f = N("frame", parent, width=w, height=h, props={
        "fill": "#E0E0E0", "cornerRadius": 4, "sizingH": "fixed", "sizingV": "fixed",
        "clip": True})
    N("rectangle", f, x=0, y=0, width=int(w * frac), height=h, props={"fill": ACC, "cornerRadius": 4})
    return f


# ---------------------------------------------------------------- rámec průvodce

def shell(N, T, idx, x, y, primary_key="continue"):
    rootf = N("frame", name=f"W{idx} · {T['steps'][idx - 1]}", x=x, y=y, width=W, height=H,
              props={"fill": BG, "layout": "vertical", "gap": 0, "padding": 0, "clip": True})

    hdr = N("frame", rootf, name="Header", props={
        "fill": PANEL, "layout": "horizontal", "padding": [14, 20, 14, 20], "gap": 12,
        "sizingH": "fill", "sizingV": "hug", "mainAlign": "spaceBetween", "crossAlign": "center"})
    text(N, hdr, T["title"], 18)
    text(N, hdr, T["step_of"].format(i=idx), 13, DIM)
    N("rectangle", rootf, name="Rule", height=1, props={"fill": LINE, "sizingH": "fill"})

    body = N("frame", rootf, name="Body", props={
        "layout": "horizontal", "gap": 0, "sizingH": "fill", "sizingV": "fill", "fill": BG})
    sb = N("frame", body, name="Steps", width=226, props={
        "fill": MUTEBG, "layout": "vertical", "gap": 2, "padding": [16, 12, 16, 12],
        "sizingV": "fill", "sizingH": "fixed"})
    for i, k in enumerate(T["steps"], 1):
        on, done = i == idx, i < idx
        r = N("frame", sb, name=f"step{i}", props={
            "layout": "horizontal", "gap": 10, "padding": [8, 10, 8, 10], "cornerRadius": 5,
            "sizingH": "fill", "sizingV": "hug", "crossAlign": "center",
            "fill": "#E7EEFB" if on else TRANS})
        text(N, r, "✓" if done else str(i), 12, OK if done else (ACC if on else DIM))
        text(N, r, k, 13, INK if on or done else DIM)
    N("rectangle", body, name="Rule2", width=1, props={"fill": LINE, "sizingV": "fill"})

    content = N("frame", body, name="Content", props={
        "layout": "vertical", "gap": 16, "padding": 24,
        "sizingH": "fill", "sizingV": "fill", "fill": BG})

    N("rectangle", rootf, name="Rule3", height=1, props={"fill": LINE, "sizingH": "fill"})
    ftr = N("frame", rootf, name="Footer", props={
        "fill": PANEL, "layout": "horizontal", "padding": [12, 20, 12, 20], "gap": 10,
        "sizingH": "fill", "sizingV": "hug", "mainAlign": "spaceBetween", "crossAlign": "center"})
    button(N, ftr, T["cancel"])
    right = row(N, ftr, gap=10)
    button(N, right, T["back"], "ghost" if idx == 1 else "normal")
    button(N, right, T[primary_key], "primary")
    return rootf, content


# ---------------------------------------------------------------- jednotlivé kroky

def step1(N, T, c):
    field_row(N, c, T["dye"], lambda r: dropdown(N, r, "EtBr"))
    text(N, c, T["profile_hint"], 12, DIM)

    def uv(r):
        g = row(N, r, gap=22)
        radio(N, g, "70 %", True)
        radio(N, g, "100 %", False)
    field_row(N, c, T["uv_level"], uv)
    field_row(N, c, T["gel_name"], lambda r: textfield(N, r, T["gel_name_val"]))
    field_row(N, c, T["note"], lambda r: textfield(N, r, T["note_ph"], dim=True))
    note(N, c, [T["s1_note1"], T["s1_note2"]])


def step2(N, T, c):
    pv = preview(N, c, 685, 196, "")
    grid_lines(N, pv, 685, 196, 228, 65)
    band(N, pv, 268, 26, 150, 142, "#2B2B2B", 1.0, 3)
    for i, yy in enumerate([46, 76, 106, 136]):
        band(N, pv, 280, yy, 126, 8, "#C9C9C9", 0.85 - i * 0.18)
    text(N, pv, T["preview_white"], 11, PV_INK)

    r = row(N, c, gap=8, align="center")
    text(N, r, T["lighting_now"], 12, INK)
    small_button(N, r, T["white_light"], True)
    small_button(N, r, T["uv70"])
    small_button(N, r, "UV 100 %")
    text(N, c, T["lighting_manual"], 11.5, DIM, wrap=True)

    p = panel(N, c, T["checklist"])
    g = N("frame", p, props={"layout": "horizontal", "gap": 24, "sizingH": "fill",
                             "sizingV": "hug", "fill": TRANS})
    l = col(N, g, gap=10, sizingH="fill")
    rr = col(N, g, gap=10, sizingH="fill")
    checkbox(N, l, T["chk_cabinet"], True)
    checkbox(N, l, T["chk_gel"], True)
    checkbox(N, rr, T["chk_eyepiece"], True, T["chk_eyepiece_h"])
    checkbox(N, rr, T["chk_zoom"], False, T["chk_zoom_h"])
    note(N, c, [T["s2_warn"]], "err")


def step3(N, T, c):
    top = N("frame", c, props={"layout": "horizontal", "gap": 16, "sizingH": "fill",
                               "sizingV": "hug", "fill": TRANS})
    pv = preview(N, top, 390, 268, "")
    for i, yy in enumerate([54, 134, 214]):
        band(N, pv, 46, yy, 300, 34, "#E6E6E6", 0.95 - i * 0.2, 3)
        band(N, pv, 46, yy - 5, 300, 5, "#7A7A7A", 0.5 - i * 0.12, 2)
    nav = N("frame", pv, x=390 - 106, y=10, width=96, height=66, props={
        "fill": "#0A0A0A", "stroke": "#5A5A5A", "strokeWeight": 1, "cornerRadius": 3,
        "clip": True, "opacity": 0.92})
    band(N, nav, 28, 9, 40, 48, "#2A2A2A", 1.0, 2)
    for yy in [15, 26, 37, 48]:
        band(N, nav, 32, yy, 32, 3, "#B8B8B8", 0.8, 1)
    N("rectangle", nav, x=29, y=22, width=36, height=17,
      props={"fill": TRANS, "stroke": ACC, "strokeWeight": 2, "cornerRadius": 2})
    text(N, pv, T["mag10"], 11, PV_INK)

    rightc = col(N, top, gap=12, sizingH="fill")
    p = panel(N, rightc, T["sharpness"])
    text(N, p, T["sharp_val"], 30, OK)
    text(N, p, T["sharp_hint"], 11.5, DIM, wrap=True)
    p2 = panel(N, rightc, T["focus"])
    button(N, p2, T["run_af"], "primary")
    text(N, p2, T["fine_steps"], 12, DIM)
    r = row(N, p2, gap=6)
    for lab in ["«««", "««", "«", "»", "»»", "»»»"]:
        small_button(N, r, lab)
    r2 = row(N, p2, gap=8)
    text(N, r2, T["magnifier"], 12, DIM)
    small_button(N, r2, "1×")
    small_button(N, r2, "5×")
    small_button(N, r2, "10×", True)
    note(N, c, [T["s3_note1"], T["s3_note2"]])


def step4(N, T, c):
    top = N("frame", c, props={"layout": "horizontal", "gap": 16, "sizingH": "fill",
                               "sizingV": "hug", "fill": TRANS})
    pv = preview(N, top, 330, 228, "")
    band(N, pv, 92, 30, 146, 170, "#1E1E1E", 1.0, 3)
    for i, yy in enumerate([52, 82, 112, 142, 172]):
        band(N, pv, 100, yy, 130, 9, "#E6B9B9", 0.95 - i * 0.16)
    text(N, pv, T["test_raw"], 11, PV_INK)

    rightc = col(N, top, gap=12, sizingH="fill")
    histogram(N, rightc, 330, 96)
    g = row(N, rightc, gap=26, align="min")
    stat(N, g, T["brightest"], T["brightest_val"])
    stat(N, g, T["of_range"], T["of_range_val"], OK)
    stat(N, g, T["saturated"], T["sat_val"], OK)

    p = panel(N, c, T["exp_proposal"])
    r = row(N, p, gap=14)
    text(N, r, T["exp_change"], 18)
    text(N, r, T["exp_hint"], 12, DIM)
    r2 = row(N, p, gap=8)
    button(N, r2, T["take_test"])
    button(N, r2, T["apply_proposal"], "primary")
    note(N, c, [T["s4_note"]])


def step5(N, T, c):
    g = N("frame", c, props={"layout": "horizontal", "gap": 16, "sizingH": "fill",
                             "sizingV": "hug", "fill": TRANS})
    d = panel(N, g, T["darks"], sizingH="fill")
    text(N, d, T["darks_val"], 14)
    text(N, d, T["darks_h1"], 11.5, DIM, wrap=True)
    text(N, d, T["darks_h2"], 11.5, DIM, wrap=True)
    r = row(N, d, gap=8)
    small_button(N, r, T["automatic"], True)
    small_button(N, r, T["use_stored"])

    f = panel(N, g, T["flat"], sizingH="fill")
    text(N, f, T["flat_val"], 14)
    r2 = row(N, f, gap=8, align="center")
    N("ellipse", r2, width=9, height=9, props={"fill": WARN})
    text(N, r2, T["flat_age"], 12, WARN)
    text(N, f, T["flat_src"], 11.5, DIM, wrap=True)
    r3 = row(N, f, gap=8)
    small_button(N, r3, T["take_new"])
    small_button(N, r3, T["pick_lib"])

    note(N, c, [T["s5_warn1"], T["s5_warn2"]])
    p = panel(N, c, T["applied"])
    text(N, p, T["formula"], 12.5, DIM)


def step6(N, T, c):
    p = panel(N, c, T["series"])
    field_row(N, p, T["frame_count"], lambda r: dropdown(N, r, "8", 120), label_w=120)
    text(N, p, T["series_hint"], 12, DIM, wrap=True)

    pr = panel(N, c, T["progress"])
    r = row(N, pr, gap=14, align="center")
    text(N, r, T["progress_val"], 20)
    text(N, r, T["time_left"], 12, DIM)
    progress(N, pr, 0.625, 640)
    g = row(N, pr, gap=30, align="min")
    stat(N, g, T["saturated"], T["sat2_val"], OK)
    stat(N, g, T["drift"], T["drift_val"], OK)
    stat(N, g, T["snr_gain"], T["snr_val"])
    stat(N, g, T["exposure"], T["exposure_val"], DIM)

    strip = row(N, c, gap=8)
    for i in range(8):
        done = i < 5
        t = N("frame", strip, width=62, height=44, props={
            "fill": "#2A2A2A" if done else PANEL, "stroke": OK if done else LINE,
            "strokeWeight": 1, "cornerRadius": 3, "sizingH": "fixed", "sizingV": "fixed"})
        text(N, t, str(i + 1), 11, "#CFCFCF" if done else DIM)
    note(N, c, [T["s6_note1"], T["s6_note2"]])


def step7(N, T, c):
    import random
    g = N("frame", c, props={"layout": "horizontal", "gap": 14, "sizingH": "fill",
                             "sizingV": "hug", "fill": TRANS})
    for title, noise, sub in [(T["one_frame"], 0.55, T["noise1"]),
                              (T["stack8"], 0.14, T["noise8"])]:
        cc = col(N, g, gap=6)
        text(N, cc, title, 12, DIM)
        pv = preview(N, cc, 300, 196, "")
        band(N, pv, 76, 24, 148, 150, "#1B1B1B", 1.0, 3)
        for i, yy in enumerate([44, 74, 104, 134]):
            band(N, pv, 84, yy, 132, 8, "#E2C0C0", (0.95 - i * 0.2))
        for k in range(26):
            random.seed(k + int(noise * 100))
            band(N, pv, random.randint(10, 280), random.randint(8, 180), 2, 2, "#FFFFFF", noise, 1)
        text(N, cc, sub, 11.5, DIM)

    r = row(N, c, gap=8)
    small_button(N, r, T["invert"], True)
    small_button(N, r, T["sat_map"])
    text(N, r, T["preview_only"], 11.5, DIM)

    p = panel(N, c, T["export_title"])
    text(N, p, T["export_dir"], 13)
    text(N, p, T["export_files"], 11.5, DIM, wrap=True)


BUILDERS = [step1, step2, step3, step4, step5, step6, step7]
PRIMARY = ["continue"] * 6 + ["export"]


def build_all(mcp, server="figcraft", lang="en", cols=2, x0=0, y0=0):
    """Postaví všech sedm obrazovek v zadaném jazyce a vrátí jejich id."""
    T = STRINGS[lang]
    N = make_N(mcp, server)
    frames = []
    for i, (b, prim) in enumerate(zip(BUILDERS, PRIMARY), 1):
        x = x0 + ((i - 1) % cols) * (W + GAP)
        y = y0 + ((i - 1) // cols) * (H + GAP)
        rootf, content = shell(N, T, i, x, y, prim)
        b(N, T, content)
        frames.append(rootf)
    return frames
