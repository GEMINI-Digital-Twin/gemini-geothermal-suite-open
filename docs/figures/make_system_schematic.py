"""Draw the high-level environment and workflow schematic.

Writes ``system_workflow.svg`` (editable: plain SVG text and shapes, opens in
Inkscape, Illustrator, draw.io or PowerPoint) next to this script. Render the
PNG with any SVG renderer, for example::

    python docs/figures/make_system_schematic.py
    python docs/figures/make_system_schematic.py --png   # needs Python playwright + Chromium

(or open the SVG in a browser / Inkscape and export at 2x, 3200 x 1800 px).

The numbers in the output card are the report headline for the ATES pick on
KNMI Schiphol 2025 weather, staggered 35-day doublet stops, 33 MW boiler, 3.2 km wells, 10 MW
backup chiller (study_results/2026-11-04/margin_pick, daily prices + boiler part load):
EUR 36.35/MWh, 4,269 t CO2/yr, CAPEX EUR 47.6 M. Edit them here if they change.
Author: Sa'eed Telvari (Single Core).
"""

import argparse
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
LOGO = HERE / "single_core_mark.svg"  # Single Core mark, copied from deliverables/branding

W, H = 1600, 900

# Single Core palette (same as the slide deck)
NAVY = "#14213D"
INK = "#3D4757"
MUTED = "#5A6474"
LINE = "#8A93A6"
PAPER = "#FBFAF7"
PAPER2 = "#F6F4EF"
RULE = "#ECEAE3"
HEAT = "#F08A4B"
HEAT_DK = "#C2501E"
HEAT_BG = "#FBE7DC"
COOL = "#1F6FA8"
COOL_BG = "#DCEAF5"
COOL_BG2 = "#EEF4FA"

SANS = "Inter, 'IBM Plex Sans', 'Helvetica Neue', Arial, sans-serif"
HEAD = "'Space Grotesk', Inter, 'Helvetica Neue', Arial, sans-serif"
MONO = "'JetBrains Mono', 'IBM Plex Mono', Consolas, monospace"

out = []


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def rect(x, y, w, h, fill, stroke="none", sw=1.5, rx=10, dash=None, extra=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="{sw}"{d}{extra}/>'
    )


def text(x, y, s, size=15, fill=INK, weight=400, family=SANS, anchor="start", italic=False):
    st = ' font-style="italic"' if italic else ""
    out.append(
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{st}>{esc(s)}</text>'
    )


def rich(x, y, parts, size=15, anchor="start", family=SANS):
    """One line with mixed styles: parts = [(text, fill, weight, family|None)]."""
    spans = "".join(
        f'<tspan fill="{f}" font-weight="{wt}"'
        + (f' font-family="{fam}"' if fam else "")
        + f">{esc(t)}</tspan>"
        for t, f, wt, fam in parts
    )
    out.append(
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'text-anchor="{anchor}">{spans}</text>'
    )


def arrow(points, color=INK, sw=2.2, dash=None, head=True):
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    marker = f' marker-end="url(#ah-{color[1:]})"' if head else ""
    da = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" '
        f'stroke-linejoin="round"{da}{marker}/>'
    )


def step(x, y, n, color=NAVY):
    out.append(f'<circle cx="{x}" cy="{y}" r="13" fill="{color}" stroke="{PAPER}" stroke-width="2"/>')
    text(x, y + 5, str(n), 14, PAPER, 700, HEAD, "middle")


def gate_badge(x, y, label, sub=None, w=None):
    w = w or (26 + 8.4 * len(label))
    h = 30 if sub is None else 46
    rect(x - w / 2, y - h / 2, w, h, HEAT_BG, HEAT, 2, 15)
    text(x, y + (5 if sub is None else -3), label, 14, HEAT_DK, 700, SANS, "middle")
    if sub:
        text(x, y + 14, sub, 12.5, HEAT_DK, 400, SANS, "middle")


def panel_title(x, y, title, sub, fill=NAVY, subfill=MUTED):
    text(x, y, title, 20, fill, 700, HEAD)
    if sub:
        text(x, y + 20, sub, 13.5, subfill, 400, MONO)


def chip(x, y, w, label, fill=PAPER, stroke=LINE, color=NAVY):
    rect(x, y, w, 22, fill, stroke, 1.2, 6)
    text(x + 10, y + 16, label, 13, color, 500, MONO)


def build():
    marker_colors = {INK, HEAT_DK, COOL, LINE, NAVY}
    defs = "".join(
        f'<marker id="ah-{c[1:]}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
        for c in sorted(marker_colors)
    )
    out.append(f"<defs>{defs}</defs>")
    rect(0, 0, W, H, PAPER, rx=0)

    # ---------------------------------------------------------------- header
    logo = LOGO.read_text(encoding="utf-8")
    logo = re.sub(r"<metadata>.*?</metadata>", "", logo, flags=re.S)
    logo = re.sub(r"^<svg[^>]*>", '<svg x="28" y="14" width="64" height="64" viewBox="0 0 120 120">', logo)
    logo = logo.replace('id="cyl"', 'id="logo-cyl"').replace("url(#cyl)", "url(#logo-cyl)")
    out.append(f'<g id="logo">{logo}</g>')
    text(104, 44, "How the design agent works: environment and workflow", 28, NAVY, 700, HEAD)
    rich(104, 70, [
        ("Single Core", HEAT_DK, 700, None),
        ("  ·  SPE GeoHackathon 2026  ·  agentic deep-geothermal heating + cooling design on GEMINI", MUTED, 400, None),
    ], 15)
    text(W - 30, 44, "repo: saeedtelvari/gemini-hackathon", 13.5, MUTED, 400, MONO, "end")
    out.append(f'<line x1="30" y1="90" x2="{W - 30}" y2="90" stroke="{RULE}" stroke-width="2"/>')

    top = 140  # panels start here; the lane above carries the final answer
    bot = 668

    # ---------------------------------------------------------------- A: inputs
    ax, aw = 30, 236
    rect(ax, top, aw, 250, PAPER2, LINE, 1.5)
    panel_title(ax + 16, top + 30, "Challenge brief", "gemini_design.challenge")
    y = top + 82
    for line in [
        "Daily heating + cooling",
        "demand, 2027 (365 days)",
        "Reservoir + brine data,",
        "associated gas",
        "Hard rules: 1-3 doublets,",
        "50-300 m³/h, brine ΔT ≤ 40 K,",
        "≤ 330 days per doublet",
    ]:
        text(ax + 16, y, line, 14.5, INK)
        y += 21

    rect(ax, top + 268, aw, 118, PAPER2, LINE, 1.5)
    panel_title(ax + 16, top + 298, "Weather year", "gemini_design.climate")
    text(ax + 16, top + 345, "KNMI Schiphol daily, 2025", 14.5, INK)
    text(ax + 16, top + 366, "→ chiller lift, free cooling", 14.5, INK)

    rect(ax, top + 404, aw, bot - top - 404, "#FFFFFF", NAVY, 2)
    panel_title(ax + 16, top + 432, "Engineer", None)
    text(ax + 16, top + 458, "“Which design meets", 14.5, INK, italic=True)
    text(ax + 16, top + 478, "demand at lowest cost", 14.5, INK, italic=True)
    text(ax + 16, top + 498, "and CO₂?”", 14.5, INK, italic=True)
    rich(ax + 16, top + 520, [("answers ", MUTED, 400, None), ("ask_user", MUTED, 500, MONO), (" questions", MUTED, 400, None)], 13)

    # ---------------------------------------------------------------- B: agent
    bx, bw = 306, 282
    rect(bx, top, bw, bot - top, NAVY, NAVY, 1.5, 14)
    text(bx + 18, top + 32, "Design agent", 22, PAPER, 700, HEAD)
    text(bx + 18, top + 53, "gemini_agent", 13.5, "#BFC6D4", 400, MONO)

    rect(bx + 16, top + 72, bw - 32, 164, "#22304F", "#3B4A6B", 1.2, 10)
    text(bx + 30, top + 98, "Swappable LLM", 15.5, HEAT, 700, SANS)
    llms = [
        [("DeepSeek V4.1 Flash", PAPER, 700, None), ("  default", HEAT, 600, None)],
        [("GLM 5.3 · Qwen 3.8 27B", PAPER, 600, None)],
        [("  via OpenRouter", "#BFC6D4", 400, None)],
        [("GPT-6.1 Sol · Terra · GPT-6 Luna", PAPER, 600, None)],
        [("  via Codex CLI", "#BFC6D4", 400, None)],
    ]
    y = top + 121
    for parts in llms:
        rich(bx + 30, y, parts, 14)
        y += 19
    text(bx + 30, top + 222, "6 benchmarked, same tools + gate", 13, "#BFC6D4", 400, SANS, italic=True)

    text(bx + 18, top + 268, "Plans the study, calls tools,", 14.5, PAPER)
    text(bx + 18, top + 289, "reads results, retries when", 14.5, PAPER)
    text(bx + 18, top + 310, "a gate rejects, explains.", 14.5, PAPER)

    rect(bx + 16, top + 332, bw - 32, 150, "#22304F", "#3B4A6B", 1.2, 10)
    text(bx + 30, top + 358, "Memory", 15.5, HEAT, 700, SANS)
    for i, (k, v) in enumerate([
        ("scratchpad", "per question"),
        ("run ledger", "runs/Rxxxx, reused"),
        ("project notes", "every session"),
    ]):
        rich(bx + 30, top + 386 + 26 * i, [(k, PAPER, 600, MONO), ("  " + v, "#BFC6D4", 400, None)], 13.5)
    text(bx + 30, top + 466, "only gated runs can be cited", 13, "#BFC6D4", 400, SANS, italic=True)

    text(bx + 18, bot - 18, "transcripts: JSONL + Markdown, tokens", 12.5, "#BFC6D4", 400, SANS)

    # ---------------------------------------------------------------- C: tools
    cx, cw = 678, 238
    rect(cx, top, cw, bot - top, "#FFFFFF", NAVY, 1.5, 14)
    panel_title(cx + 16, top + 30, "15 tools", "gemini_agent.tools")
    groups = [
        ("Simulate", ["run_design", "screen", "sensitivity", "stress_test", "cross_check", "reservoir_simulation"], COOL_BG, COOL),
        ("Inspect + decide", ["describe_inputs", "list_models", "get_run", "compare_runs", "log_option"], PAPER2, LINE),
        ("Extend", ["write_model"], HEAT_BG, HEAT),
        ("Talk + remember", ["ask_user", "memory_read", "memory_write"], PAPER2, LINE),
    ]
    y = top + 66
    for g, names, fill, stroke in groups:
        text(cx + 16, y + 4, g.upper(), 11.5, MUTED, 700, SANS)
        y += 12
        for n in names:
            chip(cx + 16, y, cw - 32, n, fill, stroke)
            y += 26
        y += 8

    # ---------------------------------------------------------------- D: engine
    dx, dw = 980, 372
    rect(dx, top, dw, 338, COOL_BG2, COOL, 1.5, 14)
    panel_title(dx + 16, top + 30, "Deterministic simulation", "gemini_design on GEMINI models", COOL)
    # pipeline
    stages = [
        ("Doublet hydraulics", "depth, drawdown, ESP, injection"),
        ("Plant flowsheet, daily", "HEX (40 K cap), boiler, CHP,"),
        ("365-day dispatch", "staggered 35-day stops"),
        ("Economics", "CAPEX, LCOE, CO₂"),
    ]
    sx, sw_ = dx + 16, 214
    sy = top + 70
    for i, (t, s) in enumerate(stages):
        hh = 50 if i != 1 else 66
        rect(sx, sy, sw_, hh, "#FFFFFF", COOL, 1.3, 8)
        text(sx + 10, sy + 22, t, 14.5, NAVY, 700)
        text(sx + 10, sy + 40, s, 12.5, MUTED)
        if i == 1:
            text(sx + 10, sy + 56, "chillers, free cooling, ATES", 12.5, MUTED)
        if i < 3:
            arrow([(sx + sw_ / 2, sy + hh), (sx + sw_ / 2, sy + hh + 12)], COOL, 1.8)
        sy += hh + 12
    # providers on the right
    px, pw = dx + 242, dw - 256
    rect(px, top + 70, pw, 98, "#FFFFFF", LINE, 1.3, 8)
    text(px + 10, top + 92, "Fimbul.jl", 14.5, NAVY, 700)
    text(px + 10, top + 111, "JutulDarcy", 12.5, MUTED)
    text(px + 10, top + 129, "30-year doublet", 12.5, MUTED)
    text(px + 10, top + 147, "cached lookup", 12.5, MUTED)
    arrow([(px, top + 100), (sx + sw_ + 2, top + 100)], LINE, 1.6)

    rect(px, top + 180, pw, 142, RULE, LINE, 1.3, 8)
    text(px + 10, top + 204, "GEMINI (TNO)", 14.5, NAVY, 700)
    for i, s in enumerate(["wells, ESP, HEX,", "heat pump,", "boiler, CHP", "+ ours: chillers,", "ATES, dry cooler"]):
        text(px + 10, top + 224 + 18 * i, s, 12.5, MUTED if i < 3 else HEAT_DK, 400 if i < 3 else 600)
    arrow([(px, top + 250), (sx + sw_ + 2, top + 250)], LINE, 1.6)

    # screen strip
    rect(dx, top + 350, dw, 60, "#FFFFFF", COOL, 1.5, 12)
    rich(dx + 16, top + 376, [("screen", NAVY, 600, MONO), ("  720 designs × 365 days", NAVY, 700, None)], 15)
    text(dx + 16, top + 398, "1-3 doublets × 6 depths × boiler/HP × CHP × 10 cooling", 12.5, MUTED)

    # write_model sandbox
    rect(dx, top + 422, dw, bot - top - 422, HEAT_BG, HEAT, 1.5, 12)
    rich(dx + 16, top + 448, [("write_model", HEAT_DK, 700, MONO), ("  sandbox (own process)", NAVY, 700, None)], 15)
    text(dx + 16, top + 472, "new model → agent's own tests →", 13, INK)
    text(dx + 16, top + 492, "our acceptance tests (interface + physics", 13, INK)
    text(dx + 16, top + 512, "contracts) → registered for design runs", 13, INK)

    # ---------------------------------------------------------------- E: output + uncertainty
    ex, ew = 1388, 182
    rect(ex, top, ew, 330, "#FFFFFF", HEAT, 2.5, 14)
    text(ex + 14, top + 28, "Recommended", 18, HEAT_DK, 700, HEAD)
    text(ex + 14, top + 49, "design", 18, HEAT_DK, 700, HEAD)
    y = top + 78
    for line in ["2 doublets, 3,200 m", "33 MW gas boiler", "+ CHP on assoc. gas", "air-cooled chiller", "+ free cooling", "3 ATES well pairs", "10 MW backup chiller"]:
        text(ex + 14, y, line, 13.5, INK)
        y += 19
    out.append(f'<line x1="{ex + 14}" y1="{top + 220}" x2="{ex + ew - 14}" y2="{top + 220}" stroke="{RULE}" stroke-width="1.5"/>')
    text(ex + 14, top + 250, "€36.35/MWh", 22, NAVY, 700, HEAD)
    text(ex + 14, top + 270, "LCOE", 12, MUTED)
    text(ex + 14, top + 298, "4,269 t CO₂/yr", 18, NAVY, 700, HEAD)
    text(ex + 14, top + 317, "demand met all 365 days", 12, MUTED)

    rect(ex, top + 348, ew, bot - top - 348, COOL_BG2, COOL, 1.5, 14)
    text(ex + 14, top + 374, "Uncertainty", 17, COOL, 700, HEAD)
    text(ex + 14, top + 392, "gemini_uncertainty", 12, MUTED, 400, MONO)
    for i, s in enumerate(["400-sample Latin", "hypercube, 14 sourced", "parameters → P10/P90,", "tornado, P(demand met)"]):
        text(ex + 14, top + 418 + 19 * i, s, 13, INK)
    text(ex + 14, top + 512, "runs the same engine", 12, MUTED, italic=True)

    # ---------------------------------------------------------------- gates 2-5 band
    gy, gh = 694, 92
    rect(cx, gy, ex + ew - cx, gh, HEAT_BG, HEAT, 2, 14)
    text(cx + 16, gy + 26, "Physics gate on every run (gates 2-5)", 16.5, HEAT_DK, 700, HEAD)
    gates = [
        ("2", "Hard rules", "every day"),
        ("3", "Energy balance", "closes to 0.1 %"),
        ("4", "Second solver", "GEMINI Solver, 0.5 K"),
        ("5", "Sanity bounds", "Carnot, T order, pumps"),
    ]
    gx = cx + 16
    for n, t, s in gates:
        out.append(f'<circle cx="{gx + 11}" cy="{gy + 58}" r="11" fill="{HEAT}"/>')
        text(gx + 11, gy + 63, n, 13, "#FFFFFF", 700, HEAD, "middle")
        text(gx + 28, gy + 54, t, 14, NAVY, 700)
        text(gx + 28, gy + 72, s, 12.5, MUTED)
        gx += 196
    # pass / fail notes at right
    text(ex + ew - 16, gy + 26, "checks we wrote; the LLM can't skip them", 13, MUTED, 400, SANS, "end", italic=True)

    # ---------------------------------------------------------------- arrows (workflow)
    # 1 question in
    arrow([(ax + aw, top + 500), (bx - 2, top + 500)], INK)
    step(ax + aw + 20, top + 482, 1)
    # inputs feed the tools' engine (the brief is read by describe_inputs; drawn into the agent)
    arrow([(ax + aw, top + 120), (bx - 2, top + 120)], LINE, 1.8)
    arrow([(ax + aw, top + 330), (bx - 2, top + 330)], LINE, 1.8)
    # ask_user back to the engineer
    arrow([(bx, top + 440), (ax + aw + 2, top + 440)], INK, 1.8, dash="6 4")

    # 2 tool call through gate 1
    arrow([(bx + bw, top + 230), (cx - 2, top + 230)], INK)
    step((bx + bw + cx) / 2, top + 207, 2)
    gate_badge((bx + bw + cx) / 2, top + 274, "Gate 1", "valid inputs", 84)

    # 3 tools drive the engine
    arrow([(cx + cw, top + 140), (dx - 2, top + 140)], COOL)
    step((cx + cw + dx) / 2, top + 117, 3, COOL)
    arrow([(cx + cw, top + 380), (dx - 2, top + 380)], COOL)
    arrow([(cx + cw, top + 470), (dx - 2, top + 470)], HEAT_DK)

    # engine -> uncertainty
    arrow([(ex + ew / 2, top + 348), (ex + ew / 2, top + 332)], COOL, 1.8, dash="4 3")

    # 4 results down into gates 2-5, then back to the agent's ledger
    arrow([(dx + 110, top + 338), (dx + 110, top + 350)], COOL, 1.8, head=False)
    arrow([(dx + dw, top + 300), (dx + dw + 18, top + 300), (dx + dw + 18, gy - 2)], COOL)
    step(dx + dw + 18, top + 470, 4, COOL)
    arrow([(cx, gy + 46), (bx + bw / 2, gy + 46), (bx + bw / 2, bot + 2)], HEAT_DK)
    text(bx + bw / 2 - 10, gy + 30, "pass → run ledger, citable", 13, NAVY, 600, SANS, "end")
    text(bx + bw / 2 - 10, gy + 50, "fail → error back to the LLM", 13, HEAT_DK, 600, SANS, "end")

    # 5 final answer over the top lane through gate 6
    lane = 112
    arrow([(bx + 150, top), (bx + 150, lane), (ex + ew / 2, lane), (ex + ew / 2, top - 2)], HEAT_DK, 2.4)
    step(bx + 150, lane, 5, HEAT_DK)
    gate_badge((bx + ex) / 2 + 120, lane, "Gate 6  no orphan numbers: every number in the answer traces to a run", None, 640)

    # ---------------------------------------------------------------- legend
    ly = 818
    out.append(f'<line x1="30" y1="{ly - 14}" x2="{W - 30}" y2="{ly - 14}" stroke="{RULE}" stroke-width="2"/>')
    items = [
        (NAVY, NAVY, "LLM (non-deterministic)"),
        (COOL_BG2, COOL, "deterministic simulation"),
        (RULE, LINE, "upstream GEMINI (TNO)"),
        (HEAT_BG, HEAT, "checks we wrote (gates, acceptance tests)"),
    ]
    lx = 30
    for fill, stroke, label in items:
        rect(lx, ly + 2, 22, 16, fill, stroke, 1.5, 4)
        text(lx + 30, ly + 15, label, 13.5, INK)
        lx += 40 + 7.6 * len(label) + 20
    rich(30, ly + 48, [
        ("Workflow: ", NAVY, 700, None),
        ("1 ask  →  2 the LLM calls a tool (gate 1 checks the arguments)  →  3 deterministic models run  →  "
         "4 gates 2-5 check every run; failures go back to the LLM  →  5 the answer is checked by gate 6 before you see it", INK, 400, None),
    ], 13.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", action="store_true", help="also render system_workflow.png with Playwright")
    ap.add_argument("--scale", type=float, default=2.0)
    args = ap.parse_args()
    build()
    meta = (
        "<metadata><rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#' "
        "xmlns:dc='http://purl.org/dc/elements/1.1/'><rdf:Description>"
        "<dc:title>Environment and workflow of the Single Core design agent</dc:title>"
        "<dc:creator>Sa'eed Telvari</dc:creator><dc:publisher>Single Core</dc:publisher>"
        "</rdf:Description></rdf:RDF></metadata>"
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
        "<title>Single Core: environment and workflow</title>" + meta + "\n" + "\n".join(out) + "\n</svg>\n"
    )
    svg_path = HERE / "system_workflow.svg"
    svg_path.write_text(svg, encoding="utf-8")
    print("wrote", svg_path)
    if args.png:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=args.scale)
            pg.goto(svg_path.as_uri())
            pg.screenshot(path=str(HERE / "system_workflow.png"))
            b.close()
        print("wrote", HERE / "system_workflow.png")


if __name__ == "__main__":
    main()
