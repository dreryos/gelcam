
"""Chybové stavy a zbývající obrazovky GelCam (FigCraft).

Spouští se po design_wizard.py a design_liveview.py do stejného namespace:
    frames = ns["build_rest"](host.mcp)

Model chyb, kterým se to řídí:
  blokující stav  -> plocha náhledu se nahradí zprávou a akcemi (foťák není)
  pruh v kroku    -> problém, který nebrání pokračovat (saturace, starý flat)
  dialog          -> rozhodnutí, které musí padnout teď (přerušená série)
"""

EY = 3760          # kam se řada chybových obrazovek položí


def big_state(N, parent, w, h, icon_color, title, lines, actions, checklist=None):
    """Plocha náhledu nahrazená zprávou."""
    f = N("frame", parent, width=w, height=h, props={
        "fill": "#FAFAFA", "stroke": LINE, "strokeWeight": 1, "cornerRadius": 6,
        "layout": "vertical", "gap": 12, "padding": 28, "mainAlign": "center",
        "crossAlign": "center", "sizingH": "fixed", "sizingV": "fixed"})
    dot = N("frame", f, width=42, height=42, props={
        "fill": icon_color, "cornerRadius": 21, "layout": "horizontal",
        "mainAlign": "center", "crossAlign": "center",
        "sizingH": "fixed", "sizingV": "fixed"})
    text(N, dot, "!", 22, "#FFFFFF")
    text(N, f, title, 18, INK)
    for s in lines:
        text(N, f, s, 12.5, DIM, width=w - 160, textAlign="center")
    if checklist:
        box = N("frame", f, width=w - 240, props={
            "fill": PANEL, "stroke": LINE, "strokeWeight": 1, "cornerRadius": 5,
            "layout": "vertical", "gap": 6, "padding": 14,
            "sizingH": "fixed", "sizingV": "hug"})
        for s in checklist:
            r = row(N, box, gap=8, align="center")
            N("ellipse", r, width=5, height=5, props={"fill": DIM})
            text(N, r, s, 12, INK)
    br = row(N, f, gap=10)
    for label, kind in actions:
        button(N, br, label, kind)
    return f


def modal(N, parent, x, y, w, title, lines, actions, tone="warn"):
    """Dialog nad obrazovkou průvodce. Kreslí se jako samostatný rámec nad ní."""
    shade = N("frame", name="shade", x=x, y=y, width=960, height=640, props={
        "fill": "#0B0B0B", "opacity": 0.45, "cornerRadius": 0})
    card = N("frame", name="dialog", x=x + (960 - w) // 2, y=y + 170, width=w, props={
        "fill": PANEL, "cornerRadius": 8, "layout": "vertical", "gap": 12, "padding": 22,
        "sizingH": "fixed", "sizingV": "hug",
        "effects": [{"type": "dropShadow", "color": "#00000055",
                     "offset": [0, 10], "radius": 28}]})
    hr = row(N, card, gap=10, align="center")
    N("ellipse", hr, width=10, height=10, props={"fill": WARN if tone == "warn" else BAD})
    text(N, hr, title, 16, INK)
    for s in lines:
        text(N, card, s, 12.5, DIM, wrap=True)
    br = N("frame", card, props={"layout": "horizontal", "gap": 10, "sizingH": "fill",
           "sizingV": "hug", "mainAlign": "max", "fill": TRANS})
    for label, kind in actions:
        button(N, br, label, kind)
    return [shade, card]


def table(N, parent, w, cols, rows_data, widths):
    t = N("frame", parent, width=w, props={
        "fill": PANEL, "stroke": LINE, "strokeWeight": 1, "cornerRadius": 6,
        "layout": "vertical", "gap": 0, "padding": 0, "clip": True,
        "sizingH": "fixed", "sizingV": "hug"})
    hr = N("frame", t, props={"layout": "horizontal", "gap": 0, "padding": [9, 14, 9, 14],
           "sizingH": "fill", "sizingV": "hug", "fill": MUTEBG})
    for c, cw in zip(cols, widths):
        text(N, hr, c, 11, DIM, width=cw)
    for i, rd in enumerate(rows_data):
        N("rectangle", t, height=1, props={"fill": "#ECECEC", "sizingH": "fill"})
        rr = N("frame", t, props={"layout": "horizontal", "gap": 0,
               "padding": [10, 14, 10, 14], "sizingH": "fill", "sizingV": "hug",
               "crossAlign": "center", "fill": "#EEF4FF" if i == 0 else TRANS})
        for j, (val, cw) in enumerate(zip(rd, widths)):
            if isinstance(val, tuple):
                cell = row(N, rr, gap=6, align="center")
                N("ellipse", cell, width=8, height=8, props={"fill": val[1]})
                text(N, cell, val[0], 12, INK)
            else:
                text(N, rr, val, 12, INK if j == 0 else DIM, width=cw)
    return t


def build_rest(mcp, server="figcraft"):
    N = make_N(mcp, server)
    T = STRINGS["en"]
    out = []

    # ---------------------------------------------------- E1 foťák není k dispozici
    rootf, leftcol, side, status = lv_shell(N, 3, "Camera unavailable", 0, EY,
                                            connected=False)
    big_state(N, leftcol, PANE_W, PANE_H + 30, BAD, "No camera found",
              ["EDSDK does not report a connected camera."],
              [("Try again", "primary"), ("Open log", "normal")],
              ["EOS Utility is running — close it first",
               "USB cable connected to the camera, not through a hub",
               "Camera switched on, mode M, AC adapter plugged in",
               "No other tethering application holds the camera"])
    p = panel(N, side, "Camera")
    text(N, p, "not connected", 13, BAD)
    text(N, p, "Last seen: Canon EOS 100D, 11:38", 11.5, DIM, wrap=True)
    p2 = panel(N, side, "Detected applications")
    for app_, st in [("EOS Utility — running", BAD), ("digiCamControl — not running", DIM),
                     ("Lightroom — not running", DIM)]:
        r = row(N, p2, gap=8, align="center")
        N("ellipse", r, width=8, height=8, props={"fill": st})
        text(N, r, app_, 12, INK if st == BAD else DIM)
    text(N, p2, "Only EOS Utility is running. It keeps the camera for itself.",
         11, DIM, wrap=True)
    text(N, status, "Disconnected · retrying every 5 s", 11.5, DIM)
    text(N, status, "Log", 11.5, ACC)
    out.append(rootf)

    # ---------------------------------------------------- E2 spojení spadlo za běhu
    rootf2, leftcol2, side2, status2 = lv_shell(N, 4, "Connection lost", LW + GAP, EY)
    view_toolbar(N, leftcol2, "1x")
    pv = preview(N, leftcol2, PANE_W, PANE_H, "")
    band(N, pv, 250, 78, 280, 300, "#1A1A1A", 1.0, 4)
    N("rectangle", pv, x=0, y=0, width=PANE_W, height=PANE_H,
      props={"fill": "#0B0B0B", "opacity": 0.6})
    cardw = 420
    c = N("frame", pv, x=(PANE_W - cardw) // 2, y=150, width=cardw, props={
        "fill": PANEL, "cornerRadius": 8, "layout": "vertical", "gap": 10, "padding": 20,
        "sizingH": "fixed", "sizingV": "hug"})
    hr = row(N, c, gap=10, align="center")
    N("ellipse", hr, width=10, height=10, props={"fill": WARN})
    text(N, hr, "Connection lost — reconnecting", 15, INK)
    text(N, c, "Last frame 3 s ago. Usually back within about 10 s "
               "(measured: 9 s after a cable pull).", 12, DIM, wrap=True)
    progress(N, c, 0.35, cardw - 40)
    text(N, c, "ISO 100 · 5 s · f/8 will be restored automatically.", 11.5, DIM, wrap=True)
    br = row(N, c, gap=10)
    button(N, br, "Reconnect now", "primary")
    button(N, br, "Cancel")
    display_strip(N, leftcol2, PANE_W, "white", black=0.03, white=0.86, gamma="1.00", auto=False)
    camera_card(N, side2)
    exposure_card(N, side2, "100", "5\"")
    text(N, status2, "Reconnecting · attempt 2 · 00:06", 11.5, DIM)
    text(N, status2, "Log", 11.5, ACC)
    out.append(rootf2)

    # ---------------------------------------------------- E3 série přerušena (dialog)
    y2 = EY + LH + GAP
    wiz, content = shell(N, T, 6, 0, y2)
    step6(N, T, content)
    out.append(wiz)
    out += modal(N, None, 0, y2, 520, "Series interrupted after 5 of 8 frames",
                 ["The camera disconnected at 11:42. Five frames are downloaded and kept; "
                  "exposure and focus are unchanged.",
                  "Stacking only five frames gives a signal-to-noise gain of x2.2 instead "
                  "of x2.8."],
                 [("Stack the 5 frames", "normal"), ("Start over", "normal"),
                  ("Resume from frame 6", "primary")])

    # ---------------------------------------------------- E4 saturovaný marker
    wiz2, content2 = shell(N, T, 4, 960 + 80, y2)
    step4(N, T, content2)
    # červená hláška nahrazuje žlutou poznámku, nepřidává se k ní
    kids = mcp(server, "get_node", id=content2, depth=1).get("children", [])
    if kids:
        mcp(server, "run_command", command="edit.delete", params={"ids": [kids[-1]["id"]]})
    note(N, content2, ["The marker band is saturated — 0.8 % of pixels at 13,583 ADU, the "
                       "white level at ISO 100. It cannot be quantified.",
                       "Shorten the exposure to 2 s, or continue if only the faint bands "
                       "matter."], "err")
    out.append(wiz2)

    # ---------------------------------------------------- E5 autofokus selhal
    y3 = y2 + 640 + GAP
    wiz3, content3 = shell(N, T, 3, 0, y3)
    step3(N, T, content3)
    note(N, content3, ["Autofocus did not lock — under UV the scene is too dim for the "
                       "sensor to find contrast. Sharpness stayed at 5.5.",
                       "Switch the cabinet to white light, run autofocus again, then switch "
                       "back to UV. The focus will hold."], "err")
    out.append(wiz3)

    # ---------------------------------------------------- E6 knihovna kalibrací
    wiz4, content4 = shell(N, T, 5, 960 + 80, y3)
    text(N, content4, "Flat field library", 15, INK, fontStyle="Bold")
    text(N, content4, "A flat is valid for one arrangement: same zoom, same UV level, "
                      "same geometry.", 12, DIM, wrap=True)
    table(N, content4, 685,
          ["Taken", "UV", "Zoom", "Exposure", "Frames", "Age"],
          [["2026-09-25", "70 %", "A", "8 s", "16", ("46 days", WARN)],
           ["2026-09-25", "100 %", "A", "8 s", "16", ("46 days", WARN)],
           ["2026-06-02", "70 %", "B", "8 s", "8", ("161 days", BAD)]],
          [96, 56, 56, 86, 66, 110])
    r = row(N, content4, gap=8)
    button(N, r, "Use selected", "primary")
    button(N, r, "Take a new flat")
    button(N, r, "Delete")
    out.append(wiz4)

    # ---------------------------------------------------- E7 hotovo po exportu
    y4 = y3 + 640 + GAP
    wiz5, content5 = shell(N, T, 7, 0, y4, "export")
    text(N, content5, "Saved", 18, OK)
    text(N, content5, "D:\\GelCam\\2026-11-10_PCR-primer-check\\", 13, INK)
    p3 = panel(N, content5, "What is in the folder")
    for name, desc in [
            ("result.tif", "16-bit, linear, channel R, 2604 x 1738 — the file to quantify"),
            ("preview.png", "8-bit, with the display settings you chose — for slides"),
            ("metadata.json", "exposure, ISO, UV level, profile, every processing step"),
            ("raw/", "8 original CR2 frames, untouched"),
            ("calib/", "16 dark frames and a reference to the flat used")]:
        r = row(N, p3, gap=12, align="min")
        text(N, r, name, 12, INK, width=110)
        text(N, r, desc, 11.5, DIM)
    r = row(N, content5, gap=8)
    button(N, r, "Open folder", "primary")
    button(N, r, "New gel image")
    button(N, r, "Back to live view")
    out.append(wiz5)

    # ---------------------------------------------------- E8 nastavení
    st = N("frame", name="S1 · Settings", x=960 + 80, y=y4, width=960, height=640, props={
        "fill": BG, "layout": "vertical", "gap": 0, "padding": 0, "clip": True})
    hdr = N("frame", st, props={"fill": PANEL, "layout": "horizontal",
            "padding": [14, 20, 14, 20], "sizingH": "fill", "sizingV": "hug",
            "mainAlign": "spaceBetween", "crossAlign": "center"})
    text(N, hdr, "Settings", 18)
    text(N, hdr, "stored in %APPDATA%\\GelCam", 11.5, DIM)
    N("rectangle", st, height=1, props={"fill": LINE, "sizingH": "fill"})
    body = N("frame", st, props={"layout": "vertical", "gap": 14, "padding": 24,
             "sizingH": "fill", "sizingV": "fill", "fill": BG})
    g = panel(N, body, "General")
    field_row(N, g, "Language", lambda r: dropdown(N, r, "English", 200), label_w=150)
    field_row(N, g, "Root folder", lambda r: textfield(N, r, "D:\\GelCam", 300), label_w=150)
    d = panel(N, body, "Defaults for a new gel")
    field_row(N, d, "Frames in a series", lambda r: dropdown(N, r, "8", 110), label_w=150)
    field_row(N, d, "Flat field warning", lambda r: dropdown(N, r, "older than 30 days", 220),
              label_w=150)
    field_row(N, d, "Binning", lambda r: dropdown(N, r, "off", 110), label_w=150)
    pr = panel(N, body, "Dye profiles")
    table(N, pr, 620, ["Dye", "Channel", "Filter", "Default exposure"],
          [["EtBr", "R", "orange", "4 s · ISO 100 · f/8"],
           ["GelRed", "R", "orange", "4 s · ISO 100 · f/8"],
           ["SYBR Safe", "G", "amber", "8 s · ISO 100 · f/8"]],
          [150, 90, 110, 200])
    text(N, pr, "Profiles are TOML files in the application folder.", 11, DIM, wrap=True)
    out.append(st)
    return out
