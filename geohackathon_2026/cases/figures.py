"""Draw the report figures as SVG files, from the yearly model, with no plotting library.

Writes results/figures/year_supply.svg, the daily heating and cooling supply of
the recommended design over 2027 stacked by source, and
results/figures/system_diagram.svg, its layout with the annual energy flows.

Run from the project folder:
    PYTHONPATH=../src:cases:agent python cases/figures.py
"""

from pathlib import Path

from yearly_energy import (
    ASSUMED_COOLING_COP,
    COOLING_FILE,
    HEATING_FILE,
    EnergyDesign,
    lowest_demand_windows,
    read_demand,
    run_design,
)

ROOT = Path(__file__).parent.parent
FIGURES_DIR = ROOT / "results" / "figures"
DESIGN = EnergyDesign(2, 3000.0, heating_top_up="chp", cooling="absorption")

# Validated categorical slots 1-4 (light surface); every band also carries a direct label
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
COLORS = {"geothermal": "#2a78d6", "chp": "#eb6834", "absorption": "#1baf7a", "electric": "#eda100"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_STARTS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


def stacked_bands(rows, keys):
    """Return, per key, the lower and upper edge of its band for every day."""
    bands, base = {}, [0.0] * len(rows)
    for key in keys:
        top = [low + row[key] for low, row in zip(base, rows)]
        bands[key] = (base, top)
        base = top
    return bands


def panel(rows, keys, labels, y_max, y_step, top, height, title, label_days):
    """Return SVG elements for one stacked-area panel."""
    left, width = 60, 800
    x = lambda day: left + day * width / 364  # noqa: E731
    y = lambda value: top + height - value * height / y_max  # noqa: E731
    parts = [f'<text x="{left}" y="{top - 14}" font-size="15" font-weight="600" fill="{TEXT}">{title}</text>']
    for value in range(0, int(y_max) + 1, y_step):
        parts.append(f'<line x1="{left}" x2="{left + width}" y1="{y(value):.1f}" y2="{y(value):.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{left - 8}" y="{y(value) + 4:.1f}" font-size="12" text-anchor="end" fill="{TEXT_SECONDARY}">{value}</text>')
    parts.append(
        f'<text x="{left - 44}" y="{top + height / 2:.1f}" font-size="12" fill="{TEXT_SECONDARY}" '
        f'transform="rotate(-90 {left - 44} {top + height / 2:.1f})" text-anchor="middle">MW</text>'
    )
    for key in keys:
        low, high = stacked_bands(rows, keys)[key]
        upper = " ".join(f"{x(day):.1f},{y(value):.1f}" for day, value in enumerate(high))
        lower = " ".join(f"{x(day):.1f},{y(value):.1f}" for day, value in reversed(list(enumerate(low))))
        parts.append(f'<polygon points="{upper} {lower}" fill="{COLORS[key]}" stroke="{SURFACE}" stroke-width="1"/>')
    bands = stacked_bands(rows, keys)
    for key, (day, rise) in label_days.items():
        low, high = bands[key]
        middle = (low[day] + high[day]) / 2
        label_y = y(middle) + 4
        if rise:
            # Thin band: label above the stack, with a leader line to the band.
            label_y = y(high[day]) - rise
            parts.append(
                f'<line x1="{x(day):.1f}" x2="{x(day):.1f}" y1="{label_y + 4:.1f}" y2="{y(middle):.1f}" '
                f'stroke="{TEXT_SECONDARY}" stroke-width="1"/>'
            )
        parts.append(
            f'<text x="{x(day):.1f}" y="{label_y:.1f}" font-size="13" font-weight="600" text-anchor="middle" '
            f'fill="{TEXT}" stroke="{SURFACE}" stroke-width="3" paint-order="stroke">{labels[key]}</text>'
        )
    for month, start in zip(MONTHS, MONTH_STARTS):
        parts.append(f'<text x="{x(start + 15):.1f}" y="{top + height + 18}" font-size="12" text-anchor="middle" fill="{TEXT_SECONDARY}">{month}</text>')
    parts.append(f'<line x1="{left}" x2="{left + width}" y1="{top + height}" y2="{top + height}" stroke="{TEXT_SECONDARY}" stroke-width="1"/>')
    return parts


def year_supply(rows):
    """Return the SVG text of the yearly supply figure."""
    heat = [
        {"geothermal": row["geothermal_heat_mw"], "chp": row["chp_heat_mw"] + row["backup_heat_mw"]}
        for row in rows
    ]
    cool = [{"absorption": row["absorption_cooling_mw"], "electric": row["electric_cooling_mw"]} for row in rows]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 600" font-family="Arial, Helvetica, sans-serif">',
        f'<rect width="900" height="600" fill="{SURFACE}"/>',
    ]
    parts += panel(
        heat, ["geothermal", "chp"], {"geothermal": "Geothermal heat", "chp": "CHP + backup boiler"},
        30, 5, 50, 290, "Heating supply, 2 x 3,000 m doublets (100 C, 111.7 GWh/yr)",
        {"geothermal": (60, 0), "chp": (200, 60)},
    )
    parts += panel(
        cool, ["absorption", "electric"], {"absorption": "Absorption chillers", "electric": "Electric chillers"},
        10, 5, 420, 130, "Cooling supply (20 C, 23.7 GWh/yr)",
        {"absorption": (200, 0), "electric": (250, 30)},
    )
    parts.append(
        f'<text x="60" y="590" font-size="12" fill="{TEXT_SECONDARY}">Electric chillers mainly cover the planned '
        "outages (from 5 May and from 25 August), when one doublet is off. Source: yearly model, checked daily in GEMINI.</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts)


def box(x, y, w, h, title, lines, accent):
    """Return SVG for one component box: a title and up to two detail lines."""
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="#ffffff" stroke="{accent}" stroke-width="2"/>',
        f'<text x="{x + w / 2}" y="{y + 20}" font-size="13" font-weight="600" text-anchor="middle" fill="{TEXT}">{title}</text>',
    ]
    for index, line in enumerate(lines):
        parts.append(
            f'<text x="{x + w / 2}" y="{y + 37 + 15 * index}" font-size="11.5" text-anchor="middle" '
            f'fill="{TEXT_SECONDARY}">{line}</text>'
        )
    return parts


def arrow(points, color, label=None, label_at=None, dashed=False):
    """Return SVG for a flow line through the points, with an arrowhead and an optional label."""
    marker = {"#2a78d6": "brine", "#eb6834": "gas", "#1baf7a": "cool", TEXT_SECONDARY: "power"}[color]
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    path = " ".join(f"{x},{y}" for x, y in points)
    parts = [
        f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="2.5"{dash} marker-end="url(#{marker})"/>'
    ]
    if label:
        x, y = label_at
        parts.append(
            f'<text x="{x}" y="{y}" font-size="11.5" fill="{TEXT}" stroke="{SURFACE}" stroke-width="3" '
            f'paint-order="stroke">{label}</text>'
        )
    return parts


def system_diagram():
    """Return the SVG text of the system layout of the recommended design."""
    brine, gas, cool, power = COLORS["geothermal"], COLORS["chp"], COLORS["absorption"], TEXT_SECONDARY
    markers = "".join(
        f'<marker id="{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker>'
        for name, color in (("brine", brine), ("gas", gas), ("cool", cool), ("power", power))
    )
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 540" font-family="Arial, Helvetica, sans-serif">',
        f"<defs>{markers}</defs>",
        f'<rect width="1000" height="540" fill="{SURFACE}"/>',
        f'<text x="20" y="28" font-size="15" font-weight="600" fill="{TEXT}">Recommended system: 2 doublets at 3,000 m, CHP on produced gas, absorption cooling</text>',
    ]
    parts += box(20, 190, 160, 70, "2 production wells", ["3,000 m, 101 C at wellhead", "50-300 m3/h each"], brine)
    parts += box(230, 195, 120, 60, "Separator", ["gas 0.8 Nm3 per m3"], brine)
    parts += box(220, 60, 140, 70, "CHP", ["produced gas only", "1.1 MW electric"], gas)
    parts += box(410, 130, 160, 70, "Heating exchanger", ["district water 50 C in", "2 MW/K per doublet"], brine)
    parts += box(410, 260, 160, 70, "Chiller exchanger", ["94 C hot water", "brine out 75 C or more"], brine)
    parts += box(20, 400, 160, 70, "2 injection wells", ["equal volume", "brine cooled 40 C or less"], brine)
    parts += box(630, 130, 140, 70, "Backup boiler", ["15.9 MW, gas", "0.1 GWh a year"], gas)
    parts += box(820, 130, 160, 70, "District heating", ["100 C supply", "30 MW peak, 111.7 GWh"], TEXT_SECONDARY)
    parts += box(630, 260, 140, 70, "Absorption chillers", ["10 MW, COP 0.67", "20.8 GWh a year"], cool)
    parts += box(630, 380, 140, 70, "Electric chillers", ["3.7 MW, COP 5", "2.9 GWh a year"], cool)
    parts += box(820, 300, 160, 70, "District cooling", ["20 C supply", "10 MW peak, 23.7 GWh"], TEXT_SECONDARY)
    parts += box(820, 440, 160, 60, "Grid", ["1.88 GWh a year bought"], power)

    parts += arrow([(180, 225), (228, 225)], brine)
    parts += arrow([(290, 195), (290, 132)], gas, "gas", (296, 170))
    parts += arrow([(350, 225), (385, 225), (385, 165), (408, 165)], brine, "brine", (360, 160))
    parts += arrow([(385, 225), (385, 295), (408, 295)], brine)
    parts += arrow([(490, 200), (490, 240), (595, 240), (595, 360), (100, 360), (100, 398)], brine, "cooled brine, 62 C", (215, 352))
    parts += arrow([(490, 330), (490, 360)], brine)
    parts += arrow([(570, 165), (628, 165)], gas, "water", (582, 156))
    parts += arrow([(360, 95), (700, 95), (700, 128)], gas, "CHP heat 12.3 GWh", (440, 88))
    parts += arrow([(770, 165), (818, 165)], gas)
    parts += arrow([(570, 295), (628, 295)], cool, "hot water", (574, 286))
    parts += arrow([(770, 295), (795, 295), (795, 325), (818, 325)], cool)
    parts += arrow([(770, 415), (795, 415), (795, 345), (818, 345)], cool)
    parts += arrow([(220, 115), (200, 115), (200, 515), (700, 515), (700, 452)], power, "CHP electricity 6.2 GWh: pumps and chillers", (215, 508), dashed=True)
    parts += arrow([(820, 470), (772, 440)], power, dashed=True)
    parts.append(
        f'<text x="20" y="535" font-size="11.5" fill="{TEXT_SECONDARY}">Blue: brine. Orange: produced gas and the heat it makes. '
        "Green: cooling. Dashed: electricity. Annual values for 2027 from the yearly model.</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    """Run the recommended design and write the figures."""
    dates, heating = read_demand(HEATING_FILE)
    _, cooling = read_demand(COOLING_FILE)
    first, second = lowest_demand_windows(heating + cooling / ASSUMED_COOLING_COP)
    rows, _ = run_design(DESIGN, dates, heating, cooling, first, second)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / "year_supply.svg"
    path.write_text(year_supply(rows), encoding="utf-8")
    diagram = FIGURES_DIR / "system_diagram.svg"
    diagram.write_text(system_diagram(), encoding="utf-8")
    print(path, diagram)


if __name__ == "__main__":
    main()
