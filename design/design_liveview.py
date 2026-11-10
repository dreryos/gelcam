
"""Mockup okna Live View pro GelCam (FigCraft).

Používá pomocné funkce z design_wizard.py — v `repl` nejdřív spusť ten skript
do stejného namespace:

    ns = {}
    exec(open("design_wizard.py", encoding="utf-8").read(), ns)
    exec(open("design_liveview.py", encoding="utf-8").read(), ns)
    frames = ns["build_liveview"](host.mcp)

Texty jsou anglicky natvrdo jen v mockupu; v aplikaci půjdou přes Qt tr().
"""

LW, LH = 1280, 800          # okno aplikace
PANE_W, PANE_H = 780, 480   # plocha live view (EVF 960x640 je 3:2)


def lv_histogram(N, parent, w, h, profile="white", clipped=False):
    """Histogram pod live view. profile: white = jasná scéna, uv = tmavá scéna."""
    import math
    f = N("frame", parent, width=w, height=h, props={
        "fill": "#1C1C1C", "cornerRadius": 4, "layout": "horizontal", "gap": 1,
        "padding": [10, 10, 10, 10], "crossAlign": "max",
        "sizingH": "fixed", "sizingV": "fixed"})
    n = 96
    for i in range(n):
        t = i / (n - 1)
        if profile == "white":
            v = (math.exp(-((t - 0.16) ** 2) / 0.010) * 0.9
                 + math.exp(-((t - 0.63) ** 2) / 0.020) * 0.42)
        else:
            v = (math.exp(-((t - 0.07) ** 2) / 0.0016) * 1.0
                 + math.exp(-((t - 0.34) ** 2) / 0.012) * 0.22)
        v = max(v, 0.02)
        c = BAD if (clipped and i >= n - 3) else "#8FB4F2"
        N("rectangle", f, width=max(2, (w - 24) // n - 1), height=max(2, v * (h - 24)),
          props={"fill": c, "cornerRadius": 1})
    return f


def sparkline(N, parent, values, w=232, h=46, color=OK):
    f = N("frame", parent, width=w, height=h, props={
        "fill": "#F4F4F4", "cornerRadius": 4, "layout": "horizontal", "gap": 2,
        "padding": [6, 8, 6, 8], "crossAlign": "max", "sizingH": "fixed", "sizingV": "fixed"})
    mx = max(values)
    for i, v in enumerate(values):
        last = i == len(values) - 1
        N("rectangle", f, width=8, height=max(2, (v / mx) * (h - 14)),
          props={"fill": color if last else "#BFD3F5", "cornerRadius": 1})
    return f


def chip_select(N, parent, label, value, dot=None):
    """Chip, který se dá rozkliknout — obsluha jím hlásí, co ručně přepnula."""
    f = row(N, parent, gap=7, fill=PANEL, padding=[5, 10, 5, 10], cornerRadius=12,
            stroke=ACC, strokeWeight=1)
    if dot:
        N("ellipse", f, width=8, height=8, props={"fill": dot})
    text(N, f, label, 11.5, DIM)
    text(N, f, value, 12, INK)
    text(N, f, "▾", 10, ACC)
    return f


def chip(N, parent, label, dot=None):
    f = row(N, parent, gap=7, fill=PANEL, padding=[5, 10, 5, 10], cornerRadius=12,
            stroke=LINE, strokeWeight=1)
    if dot:
        N("ellipse", f, width=8, height=8, props={"fill": dot})
    text(N, f, label, 12, INK)
    return f


def slider(N, parent, label, frac, value, w=168):
    """Popisek + dráha s úchytem + hodnota. Jen kresba, žádná interakce."""
    r = row(N, parent, gap=10, align="center")
    text(N, r, label, 11.5, DIM, width=58)
    track = N("frame", r, width=w, height=16, props={
        "fill": TRANS, "sizingH": "fixed", "sizingV": "fixed"})
    N("rectangle", track, x=0, y=6, width=w, height=4,
      props={"fill": "#DCDCDC", "cornerRadius": 2})
    N("rectangle", track, x=0, y=6, width=max(2, int(w * frac)), height=4,
      props={"fill": ACC, "cornerRadius": 2})
    N("ellipse", track, x=max(0, int(w * frac) - 6), y=2, width=13, height=13,
      props={"fill": PANEL, "stroke": ACC, "strokeWeight": 2})
    text(N, r, value, 11.5, INK, width=52)
    return r


def hist_with_points(N, parent, w, h, profile="uv", black=0.06, white=0.52):
    """Histogram s úchyty černého a bílého bodu; mimo rozsah je ztmavený."""
    import math
    f = N("frame", parent, width=w, height=h, props={
        "fill": "#1C1C1C", "cornerRadius": 4, "clip": True,
        "sizingH": "fixed", "sizingV": "fixed"})
    n = 86
    bw = (w - 20) / n
    for i in range(n):
        t = i / (n - 1)
        if profile == "white":
            v = (math.exp(-((t - 0.16) ** 2) / 0.010) * 0.9
                 + math.exp(-((t - 0.63) ** 2) / 0.020) * 0.42)
        else:
            v = (math.exp(-((t - 0.07) ** 2) / 0.0016) * 1.0
                 + math.exp(-((t - 0.34) ** 2) / 0.012) * 0.22)
        v = max(v, 0.02)
        bh = max(2, v * (h - 34))
        N("rectangle", f, x=10 + i * bw, y=h - 22 - bh, width=max(2, bw - 1), height=bh,
          props={"fill": "#8FB4F2", "cornerRadius": 1})
    for x0, x1 in [(0, 10 + black * (w - 20)), (10 + white * (w - 20), w)]:
        N("rectangle", f, x=x0, y=0, width=max(1, x1 - x0), height=h - 18,
          props={"fill": "#000000", "opacity": 0.55})
    for frac, col_ in [(black, "#FFFFFF"), (white, "#FFFFFF")]:
        x = 10 + frac * (w - 20)
        N("rectangle", f, x=x - 1, y=0, width=2, height=h - 18, props={"fill": col_, "opacity": 0.8})
        N("rectangle", f, x=x - 5, y=h - 20, width=10, height=10,
          props={"fill": col_, "cornerRadius": 2})
    return f


def display_strip(N, parent, w, profile="uv", black=0.06, white=0.52,
                  gamma="0.55", auto=True):
    """Pruh pod náhledem: histogram s body + jas, kontrast, gamma. Jen zobrazení."""
    card = N("frame", parent, width=w, props={
        "fill": PANEL, "stroke": LINE, "strokeWeight": 1, "cornerRadius": 6,
        "layout": "vertical", "gap": 8, "padding": 12,
        "sizingH": "fixed", "sizingV": "hug"})
    head = N("frame", card, props={"layout": "horizontal", "gap": 10, "sizingH": "fill",
             "sizingV": "hug", "crossAlign": "center", "mainAlign": "spaceBetween",
             "fill": TRANS})
    hl = row(N, head, gap=10)
    text(N, hl, "Display", 13, INK, fontStyle="Bold")
    text(N, hl, "preview only — result.tif and the RAW stay linear", 11, DIM)
    hr = row(N, hr_parent := head, gap=6)
    small_button(N, hr, "Auto stretch", auto)
    small_button(N, hr, "Reset")
    small_button(N, hr, "Invert")

    body = row(N, card, gap=14, align="min")
    hist_with_points(N, body, 392, 104, profile, black, white)
    sl = col(N, body, gap=7)
    slider(N, sl, "Black", black, f"{int(black * 255)}")
    slider(N, sl, "White", white, f"{int(white * 255)}")
    slider(N, sl, "Gamma", 0.42, gamma)
    r = row(N, sl, gap=6)
    text(N, r, "Channel", 11.5, DIM, width=58)
    for ch in ["R", "G", "B"]:
        small_button(N, r, ch, ch == "R")
    return card


def lv_shell(N, idx, title, x, y, connected=True):
    """Okno aplikace: horní lišta, levý sloupec s live view, pravý panel, stavový řádek."""
    rootf = N("frame", name=f"LV{idx} · {title}", x=x, y=y, width=LW, height=LH,
              props={"fill": BG, "layout": "vertical", "gap": 0, "padding": 0, "clip": True})

    top = N("frame", rootf, name="Toolbar", props={
        "fill": PANEL, "layout": "horizontal", "padding": [12, 18, 12, 18], "gap": 14,
        "sizingH": "fill", "sizingV": "hug", "mainAlign": "spaceBetween", "crossAlign": "center"})
    left = row(N, top, gap=12)
    text(N, left, "GelCam", 17)
    if connected:
        chip(N, left, "Canon EOS 100D", OK)
        chip(N, left, "AC adapter")
        chip(N, left, "RAW")
        chip_select(N, left, "Light:", "UV 70 %" if idx == 2 else "white",
                    "#8A6BD1" if idx == 2 else "#E8C46A")
    else:
        chip(N, left, "No camera", BAD)
    button(N, top, "New gel image…", "primary" if connected else "ghost")
    N("rectangle", rootf, height=1, props={"fill": LINE, "sizingH": "fill"})

    body = N("frame", rootf, name="Body", props={
        "layout": "horizontal", "gap": 16, "padding": 16, "sizingH": "fill",
        "sizingV": "fill", "fill": BG})
    leftcol = col(N, body, gap=10)
    sidebar = N("frame", body, name="Sidebar", width=300, props={
        "layout": "vertical", "gap": 10, "sizingH": "fixed", "sizingV": "fill", "fill": TRANS})

    N("rectangle", rootf, height=1, props={"fill": LINE, "sizingH": "fill"})
    status = N("frame", rootf, name="Status", props={
        "fill": PANEL, "layout": "horizontal", "padding": [8, 18, 8, 18], "gap": 18,
        "sizingH": "fill", "sizingV": "hug", "mainAlign": "spaceBetween", "crossAlign": "center"})
    return rootf, leftcol, sidebar, status


def view_toolbar(N, parent, zoom="1x"):
    r = row(N, parent, gap=8)
    text(N, r, "View", 12, DIM)
    small_button(N, r, "Grid", True)
    small_button(N, r, "Clipping")
    text(N, r, "·", 12, "#C0C0C0")
    text(N, r, "Zoom", 12, DIM)
    for z in ["1x", "5x", "10x"]:
        small_button(N, r, z, z == zoom)
    text(N, r, "·", 12, "#C0C0C0")
    text(N, r, "AF point: click in the image", 11.5, DIM)
    return r


def camera_card(N, parent, iso_warn=False):
    p = panel(N, parent, "Camera")
    for lab, val in [("Model", "Canon EOS 100D"), ("Power", "AC adapter ACK-E15"),
                     ("Quality", "RAW (enforced)"), ("Card", "free for 612 frames")]:
        r = row(N, p, gap=10)
        text(N, r, lab, 11.5, DIM, width=78)
        text(N, r, val, 12)
    r = row(N, p, gap=8, align="center")
    N("ellipse", r, width=8, height=8, props={"fill": OK})
    text(N, r, "auto power-off extended", 11.5, DIM)
    return p


def exposure_card(N, parent, iso="100", tv="4\"", warn=False):
    p = panel(N, parent, "Exposure")
    for lab, val in [("ISO", iso), ("Shutter", tv), ("Aperture", "f/8")]:
        r = N("frame", p, props={"layout": "horizontal", "gap": 10, "sizingH": "fill",
                                 "sizingV": "hug", "crossAlign": "center", "fill": TRANS})
        text(N, r, lab, 11.5, DIM, width=68)
        dropdown(N, r, val, 150)
    text(N, p, "Values are read from the camera; only what it allows is offered.",
         11, DIM, wrap=True)
    if warn:
        note(N, p, ["ISO 800 — set ISO 100 for gels."], "err")
    return p


def build_liveview(mcp, server="figcraft", x0=0, y0=2880):
    N = make_N(mcp, server)
    frames = []

    # ---------------------------------------------------------------- LV1: framing
    rootf, leftcol, side, status = lv_shell(N, 1, "Framing (white light)", x0, y0)
    view_toolbar(N, leftcol, "1x")
    pv = preview(N, leftcol, PANE_W, PANE_H, "")
    grid_lines(N, pv, PANE_W, PANE_H, PANE_W // 3, PANE_H // 3)
    band(N, pv, 250, 78, 280, 360, "#262626", 1.0, 4)
    for i, yy in enumerate([118, 176, 234, 292, 350]):
        band(N, pv, 272, yy, 236, 14, "#C7C7C7", 0.92 - i * 0.14)
    af = N("frame", pv, x=264, y=104, width=252, height=42, props={
        "fill": TRANS, "stroke": "#58D06A", "strokeWeight": 2, "cornerRadius": 2})
    text(N, af, "AF point", 10, "#58D06A")
    text(N, pv, "live view · 960 × 640 · 16.5 fps", 11, "#7A7A7A")

    display_strip(N, leftcol, PANE_W, "white", black=0.03, white=0.86,
                  gamma="1.00", auto=False)

    camera_card(N, side)
    exposure_card(N, side, "100", "4\"")
    cap = panel(N, side, "Single frame")
    button(N, cap, "Capture frame", "primary")
    text(N, cap, "IMG_0042.CR2 · 24 MB", 12)
    g = row(N, cap, gap=18, align="min")
    stat(N, g, "Brightest (R)", "9,420 ADU")
    stat(N, g, "Saturated", "0.00 %", OK)
    text(N, cap, "measured on RAW, white level 13,583 at ISO 100", 11, DIM, wrap=True)

    text(N, status, "Connected · live view 16.5 fps · light set by hand, declared in the top bar", 11.5, DIM)
    text(N, status, "Log", 11.5, ACC)
    frames.append(rootf)

    # ---------------------------------------------------------------- LV2: focusing
    rootf2, leftcol2, side2, status2 = lv_shell(N, 2, "Focusing at 10× (UV 70 %)",
                                                x0 + LW + GAP, y0)
    view_toolbar(N, leftcol2, "10x")
    pv2 = preview(N, leftcol2, PANE_W, PANE_H, "")
    for i, yy in enumerate([92, 212, 332]):
        band(N, pv2, 120, yy, 540, 48, "#F0D7D7", 0.95 - i * 0.18, 3)
        band(N, pv2, 120, yy - 6, 540, 6, "#8A6B6B", 0.5 - i * 0.12, 2)
        band(N, pv2, 120, yy + 48, 540, 6, "#8A6B6B", 0.5 - i * 0.12, 2)
    nav = N("frame", pv2, x=PANE_W - 168, y=16, width=152, height=102, props={
        "fill": "#0A0A0A", "stroke": "#5A5A5A", "strokeWeight": 1, "cornerRadius": 3,
        "clip": True, "opacity": 0.92})
    band(N, nav, 44, 14, 64, 74, "#2A2A2A", 1.0, 2)
    for yy in [24, 40, 56, 72]:
        band(N, nav, 50, yy, 52, 4, "#B8B8B8", 0.8, 1)
    N("rectangle", nav, x=46, y=34, width=56, height=26,
      props={"fill": TRANS, "stroke": ACC, "strokeWeight": 2, "cornerRadius": 2})
    text(N, pv2, "camera magnifier 10× · auto stretch on (preview only)", 11, "#7A7A7A")

    display_strip(N, leftcol2, PANE_W, "uv", black=0.06, white=0.52,
                  gamma="0.55", auto=True)

    fp = panel(N, side2, "Focus")
    text(N, fp, "53.1", 32, OK)
    text(N, fp, "variance of Laplacian · 5.5 before AF", 11, DIM, wrap=True)
    sparkline(N, fp, [5.5, 7.2, 9.0, 14.4, 28.1, 41.6, 53.1, 49.8])
    button(N, fp, "Run autofocus", "primary")
    text(N, fp, "Fine steps (near ← → far)", 11.5, DIM)
    rr = row(N, fp, gap=5)
    for lab in ["«««", "««", "«", "»", "»»", "»»»"]:
        small_button(N, rr, lab)
    button(N, fp, "Auto fine-focus")
    note(N, fp, ["Focus under white light, then switch back to UV. "
                 "The shutter never refocuses."])

    exposure_card(N, side2, "800", "4\"", warn=True)

    text(N, status2, "Connected · live view 15.9 fps · UV 70 % · zoom “A”", 11.5, DIM)
    text(N, status2, "Log", 11.5, ACC)
    frames.append(rootf2)
    return frames
