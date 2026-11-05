"""Draw the plant design space: every component the agent can combine, the pick lit up.

Writes docs/figures/design_space.svg (1600 x 900). Render a PNG with any headless
browser, for example Node Playwright at deviceScaleFactor 2.

Author: Sa'eed Telvari
"""

from pathlib import Path

W, H = 1600, 900
NAVY = "#14213D"
HEAT = "#C2501E"
HEAT_BG = "#FBE7DC"
COOL = "#1F6FA8"
COOL_BG = "#DDEBF6"
GAS = "#5A6474"
GAS_BG = "#ECEAE3"
OFF = "#9AA1AC"
OFF_BG = "#FFFFFF"
FAIL = "#B42318"
PAPER = "#F6F4EF"
FONT = "IBM Plex Sans, Arial, sans-serif"
HEAD = "Space Grotesk, Arial, sans-serif"

out = []


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=17, weight=400, fill=NAVY, anchor="start", family=FONT, ls=None):
    extra = f' letter-spacing="{ls}"' if ls else ""
    out.append(
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{extra}>{esc(s)}</text>'
    )


def box(x, y, w, h, title, lines=(), kind="heat", chosen=True, fail=False, size=18):
    """A component. chosen: filled in its colour; else a dashed grey outline."""
    colour = {"heat": HEAT, "cool": COOL, "gas": GAS}[kind]
    bg = {"heat": HEAT_BG, "cool": COOL_BG, "gas": GAS_BG}[kind]
    if chosen:
        out.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{bg}" '
            f'stroke="{colour}" stroke-width="2.5"/>'
        )
        tc, sc = NAVY, "#3D4757"
    else:
        out.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{OFF_BG}" '
            f'stroke="{OFF}" stroke-width="1.6" stroke-dasharray="6 5"/>'
        )
        tc, sc = "#5F6672", "#7A818C"
    cx = x + w / 2
    n = len(lines)
    top = y + h / 2 - (n * 19) / 2 + 2
    text(cx, top, title, size=size, weight=600, fill=tc, anchor="middle")
    for i, ln in enumerate(lines):
        text(cx, top + 21 + i * 19, ln, size=14.5, fill=sc, anchor="middle")
    if fail:
        fx, fy = x + w - 16, y + 16
        out.append(f'<circle cx="{fx}" cy="{fy}" r="12" fill="{FAIL}"/>')
        out.append(
            f'<path d="M{fx-5},{fy-5} L{fx+5},{fy+5} M{fx+5},{fy-5} L{fx-5},{fy+5}" '
            f'stroke="#fff" stroke-width="2.6" stroke-linecap="round"/>'
        )


def arrow(points, colour, dashed=False, width=3.0, head=True):
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    dash = ' stroke-dasharray="7 6"' if dashed else ""
    marker = f' marker-end="url(#a-{colour[1:]})"' if head else ""
    out.append(
        f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{width}"'
        f' stroke-linejoin="round"{dash}{marker}/>'
    )


def panel(x, y, w, h, label, colour, lx=16):
    out.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="none" '
        f'stroke="{colour}" stroke-opacity="0.35" stroke-width="1.5"/>'
    )
    text(x + lx, y + 26, label, size=14, weight=700, fill=colour, ls="2")


def chips(x, y, label, values, pick, colour):
    text(x, y + 18, label, size=14.5, weight=600, fill="#3D4757")
    cx = x + 8 + len(label) * 8.2
    for v in values:
        wv = 12 + len(v) * 8.4
        on = v == pick
        out.append(
            f'<rect x="{cx}" y="{y}" width="{wv}" height="26" rx="13" '
            f'fill="{colour if on else "#fff"}" stroke="{colour if on else OFF}" '
            f'stroke-width="1.4"{"" if on else " stroke-dasharray=\"4 3\""}/>'
        )
        text(cx + wv / 2, y + 18, v, size=14, weight=600 if on else 400,
             fill="#fff" if on else "#6B7280", anchor="middle")
        cx += wv + 6


def build():
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}">'
    )
    out.append("<defs>")
    for c in (HEAT, COOL, GAS, OFF, NAVY):
        out.append(
            f'<marker id="a-{c[1:]}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" '
            f'markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
            f'fill="{c}"/></marker>'
        )
    out.append("</defs>")
    out.append(f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>')

    # ---------------- Subsurface ----------------
    panel(20, 20, 390, 560, "SUBSURFACE", HEAT)
    box(45, 62, 340, 74, "Doublet 1", ("producer + ESP at 730 m, injector",), "heat")
    box(45, 148, 340, 74, "Doublet 2", ("staggered 35-day stop, N-1 cover",), "heat")
    box(45, 234, 340, 64, "Doublet 3", ("tested: wells cost too much",), "heat", chosen=False)
    chips(45, 314, "Depth km", ("2.5", "2.8", "3.1", "3.2", "3.4", "4.0"), "3.2", HEAT)
    text(45, 362, "87 · 96 · 105 · 108 · 114 · 132 °C at 30 °C/km", size=14, fill="#6B7280")
    chips(45, 378, "Wells", ("parallel", "series"), "parallel", HEAT)
    chips(45, 414, "Casing", ("GRE-lined", "carbon steel"), "GRE-lined", HEAT)
    # reservoir
    out.append(
        '<rect x="45" y="458" width="340" height="104" rx="10" fill="#F3E3D3" stroke="#B9875A" '
        'stroke-width="1.5"/>'
    )
    text(215, 486, "Reservoir aquifer, 100 m, 200 mD", size=16, weight=600, anchor="middle")
    text(215, 508, "≤ 300 m³/h per doublet, brine ≤ 40 K cooler", size=14.5, fill="#3D4757",
         anchor="middle")
    text(215, 528, "0.8 Nm³/m³ gas (80% CH₄, 20% CO₂)", size=14.5, fill="#3D4757",
         anchor="middle")
    text(215, 548, "wells ≥ 1,200 m apart (30-yr Fimbul.jl check)", size=14.5, fill="#3D4757",
         anchor="middle")

    # ---------------- Gas ----------------
    panel(440, 20, 520, 180, "CO-PRODUCED GAS", GAS)
    box(460, 56, 150, 128, "Separator", ("releases gas", "ahead of the HEX"), "gas")
    box(640, 56, 140, 58, "CHP engine", ("1.1 MWe",), "gas", size=17)
    box(640, 126, 140, 58, "Boiler fuel", ("the remainder",), "gas", size=17)
    box(800, 56, 140, 58, "Reinjection", ("€154/t CO₂",), "gas", chosen=False, size=17)
    box(800, 126, 140, 58, "Flare", ("last resort",), "gas", chosen=False, size=17)
    arrow([(610, 85), (636, 85)], GAS)
    arrow([(610, 155), (636, 155)], GAS)

    # ---------------- Heat ----------------
    panel(440, 222, 760, 358, "HEAT TO 100 °C", HEAT, lx=490)
    box(460, 262, 210, 110, "Heat exchanger", ("brine → district water", "4 MW/K per doublet"), "heat")
    box(700, 262, 210, 110, "Gas boiler 33 MW", ("tops up, covers", "both wells tripping"), "heat")
    box(940, 262, 240, 110, "Heat pump", ("lifts 87–96 °C brine", "to 100 °C, electric"), "heat",
        chosen=False)
    box(700, 400, 210, 92, "CHP heat", ("8.7 GWh/yr", "from the engine"), "gas", size=17)
    box(940, 400, 240, 92, "Seasonal heat store", ("pit store, model written", "by the agent"),
        "heat", chosen=False, size=17)
    text(460, 420, "Heat lift:", size=15, weight=600, fill="#3D4757")
    text(460, 442, "deeper wells (108 °C)", size=14.5, fill=HEAT, weight=600)
    text(460, 462, "or heat pump at", size=14.5, fill="#6B7280")
    text(460, 482, "shallow depth", size=14.5, fill="#6B7280")
    text(460, 520, "dashed: brine back", size=14.5, fill="#6B7280")
    text(460, 540, "to the injectors", size=14.5, fill="#6B7280")

    # ---------------- Cooling ----------------
    panel(20, 602, 1180, 280, "COOLING TO 20 °C   (geothermal route works, but dearer)", COOL, lx=310)
    box(45, 644, 250, 100, "Absorption chiller", ("driven by brine heat", "2 doublets: €38.5/MWh"),
        "cool", chosen=False, size=17)
    text(45, 776, "Electric chiller (pick one):", size=15, weight=600, fill="#3D4757")
    box(45, 790, 170, 72, "Air-cooled screw", ("10 MW backup",), "cool", size=16)
    box(225, 790, 170, 72, "Screw + dry cooler", ("cheapest, more CO₂",), "cool", chosen=False,
        size=16)
    box(405, 790, 200, 72, "Centrifugal + tower", ("water use",), "cool", chosen=False, size=16)
    box(615, 790, 150, 72, "Legacy chiller", ("old COP",), "cool", chosen=False, size=16)
    box(330, 644, 260, 100, "Free cooling", ("dry cooler on cold days", "4.3 GWh/yr"), "cool",
        size=17)
    box(625, 644, 290, 100, "Aquifer cold store (ATES)", ("0–3 well pairs → 3 pairs",
        "charged by winter air, 12.4 GWh"), "cool", size=17)
    text(960, 680, "Operation", size=15, weight=600, fill="#3D4757")
    text(960, 702, "daily, 365 days, measured", size=14.5, fill="#6B7280")
    text(960, 722, "KNMI Schiphol weather;", size=14.5, fill="#6B7280")
    text(960, 742, "free cooling, then ATES,", size=14.5, fill="#6B7280")
    text(960, 762, "then chiller", size=14.5, fill="#6B7280")
    arrow([(590, 694), (621, 694)], COOL, dashed=True, width=2)
    text(606, 684, "", size=12)

    # ---------------- Networks and power ----------------
    box(1250, 262, 320, 150, "District heating", ("supply 100 °C, return 40 °C",
        "peak 30 MW, 111.7 GWh/yr", "met 365 / 365 days"), "heat", size=21)
    out.append('<rect x="1250" y="262" width="8" height="150" fill="#C2501E"/>')
    box(1250, 664, 320, 150, "District cooling", ("supply 20 °C, return 26 °C",
        "peak 10 MW, 23.7 GWh/yr", "met 365 / 365 days"), "cool", size=21)
    out.append('<rect x="1250" y="664" width="8" height="150" fill="#1F6FA8"/>')
    box(1250, 56, 320, 128, "Electricity", ("CHP 4.4 GWh + grid 1.5 GWh",
        "runs ESPs, pumps, chillers", "5.5 GWh/yr used"), "gas", size=19)

    # flows
    arrow([(385, 99), (420, 99), (420, 120), (456, 120)], HEAT)  # doublet 1 -> separator
    arrow([(385, 185), (420, 185), (420, 120)], HEAT, head=False)  # doublet 2 joins
    arrow([(535, 184), (535, 220), (565, 220), (565, 258)], HEAT)  # separator -> HEX
    arrow([(670, 317), (696, 317)], HEAT)  # HEX -> boiler
    arrow([(910, 317), (935, 317)], OFF, dashed=True, width=2)  # boiler -> heat pump (option)
    arrow([(1180, 330), (1246, 330)], HEAT, width=3.5)  # to district heating
    arrow([(805, 492), (805, 562), (1215, 562), (1215, 360), (1246, 360)], GAS, width=2.4)  # CHP heat
    arrow([(710, 56), (710, 40), (1225, 40), (1225, 120), (1246, 120)], GAS,
          width=2.4)  # CHP power
    arrow([(710, 184), (710, 205), (790, 205), (790, 258)], GAS, width=2.4)  # gas -> boiler
    arrow([(460, 350), (425, 350), (425, 520), (389, 520)], HEAT, dashed=True, width=2.4)  # reinj
    arrow([(650, 372), (650, 591), (120, 591), (120, 640)], OFF, dashed=True,
          width=1.8)  # brine to absorption
    arrow([(915, 694), (940, 694), (940, 830), (1215, 830), (1215, 740), (1246, 740)], COOL,
          width=3.5)
    arrow([(765, 826), (940, 826)], COOL, width=2.4, head=False)
    out.append('<circle cx="940" cy="694" r="0"/>')

    # legend
    lx, ly = 1250, 828
    out.append(f'<rect x="{lx}" y="{ly}" width="34" height="20" rx="5" fill="{HEAT_BG}" '
               f'stroke="{HEAT}" stroke-width="2"/>')
    text(lx + 42, ly + 16, "in the pick", size=14.5)
    out.append(f'<rect x="{lx+140}" y="{ly}" width="34" height="20" rx="5" fill="#fff" '
               f'stroke="{OFF}" stroke-dasharray="5 4" stroke-width="1.5"/>')
    text(lx + 182, ly + 16, "simulated, not chosen", size=14.5)
    text(lx, ly + 44, "720 plants simulated: 1–3 doublets × 6 depths", size=13.5, fill="#6B7280")
    text(lx, ly + 63, "× boiler or heat pump × CHP or not × 10 coolers", size=13.5, fill="#6B7280")
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    path = Path(__file__).with_name("design_space.svg")
    path.write_text(build(), encoding="utf-8")
    print(path)
