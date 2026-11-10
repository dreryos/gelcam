"""Calibration capture, dye profiles and log screens of GelCam (FigCraft).

Run after design_wizard.py and design_liveview.py in the same namespace:
    frames = ns["build_tools"](host.mcp)

These are tool windows opened from the wizard (step 5), from Settings and from the
status bar, so they share one shell: header, body, footer with actions.
"""

TY = 6800          # row below the error states


def tool_shell(N, name, title, subtitle, x, y, left=(), right=()):
    rootf = N("frame", name=name, x=x, y=y, width=W, height=H, props={
        "fill": BG, "layout": "vertical", "gap": 0, "padding": 0, "clip": True})
    hdr = N("frame", rootf, name="Header", props={
        "fill": PANEL, "layout": "horizontal", "padding": [14, 20, 14, 20],
        "sizingH": "fill", "sizingV": "hug", "mainAlign": "spaceBetween",
        "crossAlign": "center"})
    text(N, hdr, title, 18)
    text(N, hdr, subtitle, 11.5, DIM)
    N("rectangle", rootf, height=1, props={"fill": LINE, "sizingH": "fill"})
    body = N("frame", rootf, name="Body", props={
        "layout": "horizontal", "gap": 18, "padding": 24, "sizingH": "fill",
        "sizingV": "fill", "fill": BG})
    N("rectangle", rootf, height=1, props={"fill": LINE, "sizingH": "fill"})
    ftr = N("frame", rootf, name="Footer", props={
        "fill": PANEL, "layout": "horizontal", "padding": [12, 20, 12, 20], "gap": 10,
        "sizingH": "fill", "sizingV": "hug", "mainAlign": "spaceBetween",
        "crossAlign": "center"})
    lf = row(N, ftr, gap=10)
    for label, kind in left:
        button(N, lf, label, kind)
    rt = row(N, ftr, gap=10)
    for label, kind in right:
        button(N, rt, label, kind)
    return rootf, body


def dot_line(N, parent, label, color, size=12.5, ink=INK):
    r = row(N, parent, gap=8, align="center")
    N("ellipse", r, width=8, height=8, props={"fill": color})
    text(N, r, label, size, ink)
    return r


def build_tools(mcp, server="figcraft"):
    N = make_N(mcp, server)
    out = []

    # ------------------------------------------------ C1 new flat field
    f, body = tool_shell(N, "C1 · New flat field", "New flat field",
                         "opened from step 5 or the flat library", 0, TY,
                         left=[("Cancel", "normal")],
                         right=[("Pause", "normal"), ("Save to library", "ghost")])
    lc = col(N, body, gap=12, sizingH="fill")
    pv = N("frame", lc, width=440, height=294, props={
        "cornerRadius": 4, "clip": True, "sizingH": "fixed", "sizingV": "fixed",
        "fills": [{"type": "radialGradient", "stops": ["#E9B7A0", "#9C6655"]}]})
    text(N, lc, "last flat, R channel — corners 74 % of centre", 11.5, DIM)
    g = row(N, lc, gap=30, align="min")
    stat(N, g, "Centre, R", "8 650 ADU · 64 %")
    stat(N, g, "Corners", "74 % of centre")
    stat(N, g, "Saturated", "0 %", OK)
    text(N, lc, "Target: centre at 50–80 % of range, nothing saturated. The flat is "
                "divided out, so only its shape matters, not its brightness.",
         11.5, DIM, wrap=True)

    rc = col(N, body, gap=12, sizingH="fill")
    a = panel(N, rc, "Arrangement")
    for k, v in [("Zoom", "A — marked position"), ("Light", "UV 70 %"),
                 ("Target", "uniformly fluorescing plate"),
                 ("Exposure", "8 s · ISO 100 · f/8")]:
        r = row(N, a, gap=10, align="center")
        text(N, r, k, 12, DIM, width=80)
        text(N, r, v, 12.5)
    text(N, a, "A flat is valid only for this zoom and UV level.", 11, DIM, wrap=True)
    p = panel(N, rc, "Capture")
    r = row(N, p, gap=12, align="center")
    text(N, r, "Flat 11 / 16", 16)
    text(N, r, "about 1 min left", 11.5, DIM)
    progress(N, p, 11 / 16, 340)
    dot_line(N, p, "Then 16 dark frames for the flat (8 s), lights off", DIM, 12, DIM)
    dot_line(N, p, "Brightness between frames ±0.6 % — lamp is stable", OK, 12)
    out.append(f)

    # ------------------------------------------------ C2 dark frames
    f, body = tool_shell(N, "C2 · Dark frames", "Dark frames",
                         "right after the series · same time and ISO", W + GAP, TY,
                         left=[("Cancel", "normal")],
                         right=[("Skip, use stored darks", "normal"),
                                ("Taking dark frames…", "ghost")])
    lc = col(N, body, gap=14, sizingH="fill")
    st = panel(N, lc, None, gap=12)
    r = row(N, st, gap=12, align="center")
    N("ellipse", r, width=14, height=14, props={"fill": "#1A1A1A"})
    text(N, r, "Turn off all light", 18)
    for s in ["UV lamp and white light off", "Cabinet door closed",
              "Eyepiece covered", "Do not touch the camera — the shot is running"]:
        checkbox(N, st, s, True)
    p = panel(N, lc, "Progress")
    r = row(N, p, gap=12, align="center")
    text(N, r, "7 / 16", 20)
    text(N, r, "16 × 5 s · ISO 100 · f/8 · 50 s left", 12, DIM)
    progress(N, p, 7 / 16, 400)

    rc = col(N, body, gap=12, sizingH="fill")
    m = panel(N, rc, "Check of the last frame")
    g = row(N, m, gap=26, align="min")
    stat(N, g, "Above bias", "0.1 ADU", OK)
    stat(N, g, "Noise", "7.3 ADU")
    stat(N, g, "Hot pixels", "116")
    dot_line(N, m, "No light leak", OK, 12)
    note(N, rc, ["Darks are taken now, not from the library: hot pixels depend on sensor "
                 "temperature, and after a series the sensor is warmer. Measured 4 Nov: "
                 "421 warm pixels at 8 s on a cold sensor, 2035 at 4 s after 1.5 h of "
                 "shooting."])
    out.append(f)

    # ------------------------------------------------ P1 dye profiles
    py = TY + H + GAP
    f, body = tool_shell(N, "P1 · Dye profiles", "Dye profiles",
                         "opened from Settings · TOML in the application folder", 0, py,
                         left=[("Delete", "normal")],
                         right=[("Revert", "normal"), ("Save", "primary")])
    lst = N("frame", body, width=210, props={
        "fill": PANEL, "stroke": LINE, "strokeWeight": 1, "cornerRadius": 6,
        "layout": "vertical", "gap": 2, "padding": 8, "sizingH": "fixed",
        "sizingV": "fill"})
    for name_, ch, on in [("EtBr", "R", True), ("GelRed", "R", False),
                          ("SYBR Safe", "G", False)]:
        r = N("frame", lst, props={
            "layout": "horizontal", "padding": [8, 10, 8, 10], "cornerRadius": 5,
            "sizingH": "fill", "sizingV": "hug", "mainAlign": "spaceBetween",
            "crossAlign": "center", "fill": "#E7EEFB" if on else TRANS})
        text(N, r, name_, 13, INK)
        text(N, r, ch, 12, ACC if on else DIM)
    r = N("frame", lst, props={"layout": "horizontal", "padding": [8, 10, 8, 10],
                               "sizingH": "fill", "sizingV": "hug", "fill": TRANS})
    text(N, r, "+ New profile", 13, ACC)

    fm = col(N, body, gap=12, sizingH="fill")
    p = panel(N, fm, "EtBr")
    field_row(N, p, "Name", lambda r: textfield(N, r, "EtBr", 260), label_w=130)

    def channel(r):
        radio(N, r, "R", True)
        radio(N, r, "G", False)
        text(N, r, "taken from the CFA mosaic, no demosaicing", 11.5, DIM)
    field_row(N, p, "Channel", channel, label_w=130)
    field_row(N, p, "Emission filter", lambda r: dropdown(N, r, "orange (fixed)", 200),
              label_w=130)

    def uv(r):
        radio(N, r, "70 %", True)
        radio(N, r, "100 %", False)
    field_row(N, p, "UV level", uv, label_w=130)

    def expo(r):
        dropdown(N, r, "ISO 100", 100)
        dropdown(N, r, "4\"", 80)
        dropdown(N, r, "f/8", 80)
    field_row(N, p, "Start exposure", expo, label_w=130)
    field_row(N, p, "Frames", lambda r: dropdown(N, r, "8", 80), label_w=130)
    field_row(N, p, "Note", lambda r: textfield(N, r, "standard 1× TAE gels", 400, True),
              label_w=130)
    text(N, fm, "Only values the connected camera reports are offered. Editing a profile "
                "does not change images already taken — each metadata.json keeps the "
                "profile it used.", 11.5, DIM, wrap=True)
    out.append(f)

    # ------------------------------------------------ L1 log and about
    f, body = tool_shell(N, "L1 · Log and about", "Log",
                         "opened from the status bar", W + GAP, py,
                         left=[("Copy for support", "normal")],
                         right=[("Close", "primary")])
    lc = col(N, body, gap=10, sizingH="fill", sizingV="fill")
    r = row(N, lc, gap=8, align="center")
    small_button(N, r, "All", True)
    small_button(N, r, "Warnings")
    small_button(N, r, "Errors")
    textfield(N, r, "Search", 200, True)
    lg = N("frame", lc, props={
        "fill": PANEL, "stroke": LINE, "strokeWeight": 1, "cornerRadius": 6,
        "layout": "vertical", "gap": 7, "padding": 14, "sizingH": "fill",
        "sizingV": "fill", "clip": True})
    level = {OK: "info", DIM: "info", WARN: "warning", BAD: "error"}
    for t, lvl, msg in [
            ("11:36:02", OK, "Connected: Canon EOS 100D, quality RAW"),
            ("11:36:02", DIM, "Allowed values: ISO 100–12800, 30\"–1/4000, f/5.6–f/36"),
            ("11:38:40", DIM, "Autofocus: sharpness 5.5 → 53.1"),
            ("11:40:11", DIM, "Series started: 8 × 5 s, ISO 100, profile EtBr"),
            ("11:42:07", WARN, "Connection lost (0x7, device not found)"),
            ("11:42:16", OK, "Reconnected after 9 s, settings restored"),
            ("11:42:18", DIM, "Series resumed from frame 6"),
            ("11:43:30", DIM, "Dark frames 16 × 5 s, no light leak"),
            ("11:43:58", BAD, "Saturated: 0.8 % pixels at 13 583 ADU (marker)"),
            ("11:44:20", DIM, "Exported D:\\GelCam\\2026-11-10_PCR-primer-check")]:
        rr = row(N, lg, gap=10, align="center")
        text(N, rr, t, 11.5, DIM, width=62)
        N("ellipse", rr, width=7, height=7, props={"fill": lvl})
        text(N, rr, level[lvl], 11.5, lvl if lvl in (WARN, BAD) else DIM, width=56)
        text(N, rr, msg, 12, BAD if lvl == BAD else INK)

    rc = col(N, body, gap=12, width=250, sizingH="fixed")
    a = panel(N, rc, "About GelCam")
    for k, v in [("Version", "0.1.0"), ("Canon EDSDK", "13.21.10"),
                 ("Python", "3.12 x64"), ("Camera", "Canon EOS 100D")]:
        r = row(N, a, gap=10, align="center")
        text(N, r, k, 12, DIM, width=86)
        text(N, r, v, 12)
    text(N, a, "Uses Canon EDSDK under Canon's licence.", 11, DIM, wrap=True)
    lf = panel(N, rc, "Log files")
    text(N, lf, "%APPDATA%\\GelCam\\logs", 12, wrap=True)
    text(N, lf, "One file per day, kept 30 days.", 11, DIM, wrap=True)
    small_button(N, lf, "Open folder")
    out.append(f)
    return out
