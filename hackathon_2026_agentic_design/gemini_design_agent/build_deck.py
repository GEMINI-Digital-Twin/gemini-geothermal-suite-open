"""Build the 10-slide technical report deck for the committee.   python build_deck.py"""
from __future__ import annotations
import json
from pathlib import Path
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt, Emu

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "GEMINI_Hackathon_Report_Ramdhan_Wibawa.pptx"
CL, OPT, MON = ROOT / "outputs_claude", ROOT / "outputs_opt", ROOT / "outputs_monitoring"
DASH = "https://claude.ai/artifact/NsWjVJL11z7fZCAK5Fe4my"

DEEP, TEAL, ORANGE, SAND, WHITE, INK, MUTED = "0F2A3A", "1C7293", "E07A1F", "EEF2F4", "FFFFFF", "1B1F23", "5B6770"
HEAD, BODY = "Cambria", "Calibri"
W, H = Inches(13.333), Inches(7.5)
kp = json.loads((CL / "final_kpis.json").read_text(encoding="utf-8"))
K, COST = kp["kpis"], kp["cost"]

prs = Presentation(); prs.slide_width, prs.slide_height = W, H
BLANK = prs.slide_layouts[6]


def rgb(h): return RGBColor.from_string(h)


def rect(sl, x, y, w, h, fill, shape=MSO_SHAPE.RECTANGLE, line=None):
    s = sl.shapes.add_shape(shape, x, y, w, h); s.fill.solid(); s.fill.fore_color.rgb = rgb(fill)
    if line: s.line.color.rgb = rgb(line); s.line.width = Pt(0.75)
    else: s.line.fill.background()
    s.shadow.inherit = False
    return s


def text(sl, x, y, w, h, runs, size=14, color=INK, bold=False, font=BODY, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         bullets=False, space_after=4, line_spacing=1.05):
    """runs: str | list of paragraphs; each paragraph str or list of (text, {opts})."""
    tb = sl.shapes.add_textbox(x, y, w, h); tf = tb.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0; tf.vertical_anchor = anchor
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align; p.space_after = Pt(space_after); p.line_spacing = line_spacing
        segs = para if isinstance(para, list) else [(para, {})]
        for seg, o in segs:
            r = p.add_run(); r.text = (("•  " if bullets else "") + seg) if segs.index((seg, o)) == 0 else seg
            f = r.font; f.name = o.get("font", font); f.size = Pt(o.get("size", size)); f.bold = o.get("bold", bold)
            f.italic = o.get("italic", False); f.color.rgb = rgb(o.get("color", color))
    return tb


def title(sl, t, sub=None, dark=False):
    text(sl, Inches(0.6), Inches(0.4), Inches(12.1), Inches(0.8), t, size=28, bold=True, font=HEAD, color=WHITE if dark else DEEP)
    if sub: text(sl, Inches(0.6), Inches(1.15), Inches(12.1), Inches(0.5), sub, size=15, color="CADCE3" if dark else MUTED)


def footer(sl, n, dark=False):
    text(sl, Inches(0.6), Inches(7.05), Inches(9), Inches(0.3), "GEMINI Agentic Geothermal Design Hackathon 2026  |  R. A. Wibawa",
         size=10, color="9FB3BF" if dark else MUTED)
    text(sl, Inches(12.2), Inches(7.05), Inches(0.5), Inches(0.3), str(n), size=10, color="9FB3BF" if dark else MUTED, align=PP_ALIGN.RIGHT)


def card(sl, x, y, w, h, head, body, accent=TEAL, head_size=15, body_size=12.5):
    rect(sl, x, y, w, h, SAND, MSO_SHAPE.ROUNDED_RECTANGLE).adjustments[0] = 0.06
    dot = rect(sl, x + Inches(0.2), y + Inches(0.22), Inches(0.22), Inches(0.22), accent, MSO_SHAPE.OVAL)
    text(sl, x + Inches(0.55), y + Inches(0.15), w - Inches(0.7), Inches(0.4), head, size=head_size, bold=True, color=DEEP)
    text(sl, x + Inches(0.2), y + Inches(0.6), w - Inches(0.4), h - Inches(0.7), body, size=body_size, color=INK, bullets=isinstance(body, list), space_after=3)


def stat(sl, x, y, w, big, label, color=ORANGE, big_size=40, label_color=MUTED):
    text(sl, x, y, w, Inches(0.8), big, size=big_size, bold=True, font=HEAD, color=color)
    text(sl, x, y + Inches(0.78), w, Inches(0.5), label, size=12, color=label_color)


def picture(sl, path, x, y, w=None, h=None):
    return sl.shapes.add_picture(str(path), x, y, width=w, height=h)


def table(sl, x, y, w, rows, col_w, font=11, head_fill=DEEP, row_h=Inches(0.32), numeric=False):
    t = sl.shapes.add_table(len(rows), len(rows[0]), x, y, w, row_h * len(rows)).table
    for j, cw in enumerate(col_w): t.columns[j].width = cw
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = t.cell(i, j); c.text = ""; c.margin_left = c.margin_right = Inches(0.06); c.margin_top = c.margin_bottom = Inches(0.03)
            p = c.text_frame.paragraphs[0]; r = p.add_run(); r.text = str(val); r.font.size = Pt(font); r.font.name = BODY
            r.font.bold = i == 0; r.font.color.rgb = rgb(WHITE if i == 0 else INK)
            c.fill.solid(); c.fill.fore_color.rgb = rgb(head_fill if i == 0 else (SAND if i % 2 else WHITE))
            if numeric and j > 0 and i > 0: p.alignment = PP_ALIGN.RIGHT
    return t


# ================================================================== 1 Title (dark)
s = prs.slides.add_slide(BLANK); rect(s, 0, 0, W, H, DEEP)
rect(s, Inches(8.9), Inches(0), Inches(4.433), H, "143A4F")
text(s, Inches(0.8), Inches(1.5), Inches(7.8), Inches(0.5), "SPE EUROPE ENERGY GEOHACKATHON 2026  |  EXPRESS EDITION", size=12, color="9FB3BF", bold=True)
text(s, Inches(0.8), Inches(2.0), Inches(7.8), Inches(2.2), "Three doublets at 3,500 m, direct heating and brine-driven cooling: an AI-designed, twin-verified district energy system",
     size=34, bold=True, font=HEAD, color=WHITE, line_spacing=1.05)
text(s, Inches(0.8), Inches(4.5), Inches(7.8), Inches(1.2), [
    "Propose - evaluate - diagnose - repair on the GEMINI twin, then closed-loop management, robust optimisation and real-time ESP monitoring.",
    ], size=15, color="CADCE3")
text(s, Inches(0.8), Inches(5.9), Inches(7.8), Inches(0.9), [[("Ramdhan Ari Wibawa", {"bold": True, "color": WHITE, "size": 15})],
     [("ramdhan@zanskar.us  |  4 November 2026  |  dashboard: " + DASH, {"color": "9FB3BF", "size": 11})]], size=12)
stat(s, Inches(9.4), Inches(1.6), Inches(3.5), "3 x 3,500 m", "doublets and reservoir depth selected", color=ORANGE, big_size=34, label_color="CADCE3")
stat(s, Inches(9.4), Inches(3.1), Inches(3.5), f"COP {K['system_cop']:.1f}", "heat + cooling per unit of electricity", color=WHITE, big_size=34, label_color="CADCE3")
stat(s, Inches(9.4), Inches(4.6), Inches(3.5), "0 MWh", "unmet demand over 365 days", color=WHITE, big_size=34, label_color="CADCE3")
footer(s, 1, dark=True)

# ================================================================== 2 Challenge and answer
s = prs.slides.add_slide(BLANK)
title(s, "The challenge, and what the agent delivered", "A 2,500 m, 87 C reservoir must serve 30 MW of heating at 100 C and 10 MW of cooling at 20 C, inside eight hard caps")
card(s, Inches(0.6), Inches(1.8), Inches(4.0), Inches(2.5), "Hard caps from the brief", [
    "1-3 doublets, 50-300 m3/h each", "Brine cooled at most 40 C", "330 operating days per doublet",
    "Pump efficiency 70 %, volumes balanced", "100 C heating and 20 C cooling supply"], accent=ORANGE)
card(s, Inches(0.6), Inches(4.5), Inches(4.0), Inches(2.3), "Not fixed, and not needed", [
    "Depth: 'for a different depth use hydrostatic pressure and the 30 C/km gradient'",
    "Surface plant: GEMINI has no heating or cooling models; they are ours",
    "Thermal storage: not added. The heat-pump top-up runs through 144- and 110-day cold stretches that a daily buffer cannot shift, and at 94 % geothermal share seasonal storage has nothing to displace"], accent=TEAL, body_size=10.5)
x0 = Inches(5.0)
stat(s, x0, Inches(1.8), Inches(2.6), "3", "doublets, 6 wells, 3,500 m TVD")
stat(s, x0 + Inches(2.7), Inches(1.8), Inches(2.6), "117 C", "reservoir, 114 C at the wellhead")
stat(s, x0 + Inches(5.4), Inches(1.8), Inches(2.6), f"{K['heat_delivered_gwh']:.0f} + {K['cool_delivered_gwh']:.0f}", "GWh heat + cooling, nothing unmet")
stat(s, x0, Inches(3.4), Inches(2.6), f"{K['electricity_gwh']:.1f} GWh", "electricity per year, 94 % geothermal")
stat(s, x0 + Inches(2.7), Inches(3.4), Inches(2.6), f"{COST['levelised_cost_eur_per_mwh']:.1f}", "EUR per MWh delivered (indicative)")
stat(s, x0 + Inches(5.4), Inches(3.4), Inches(2.6), f"{COST['capex_total_meur']:.0f} MEUR", "capex, of which wells dominate")
card(s, x0, Inches(5.0), Inches(7.9), Inches(1.8), "Selected system", [
    "Direct plate heat exchange carries 105 of 112 GWh of heat; a 2.5 MW high-temperature heat pump tops up cold spells",
    "10 MW single-effect absorption chiller driven by the brine covers all cooling; no electric chiller",
    "ESP at 1,000 m, 26 stages, VSD 30-65 Hz, intake 70 bar against a 29 bar bubble point; inhibitor + lined tubing against 8 mm/yr CO2 corrosion"], accent=ORANGE)
footer(s, 2)

# ================================================================== 3 Agentic architecture
s = prs.slides.add_slide(BLANK)
title(s, "Agentic workflow: the twin pushes back on every proposal", "Two orchestrators drive one toolbox; the loop ends when the simulator has nothing left to object to")
steps = [("Propose", "archetype or\nmodification", ORANGE), ("Evaluate", "365-day dispatch\non the GEMINI twin", TEAL),
         ("Diagnose", "worst violation ->\nengineering cause", TEAL), ("Repair", "deeper, more doublets,\nbigger HP, new ESP...", TEAL),
         ("Explore + trim", "16 archetypes,\nright-size capacities", TEAL), ("Rank + explain", "cost, COP, share,\nrationale per step", ORANGE)]
bx, by, bw, bh, gap = Inches(0.6), Inches(1.85), Inches(1.9), Inches(1.25), Inches(0.14)
for i, (h1, h2, c) in enumerate(steps):
    x = bx + i * (bw + gap)
    r = rect(s, x, by, bw, bh, c, MSO_SHAPE.ROUNDED_RECTANGLE); r.adjustments[0] = 0.12
    text(s, x + Inches(0.12), by + Inches(0.12), bw - Inches(0.24), Inches(0.4), h1, size=15, bold=True, color=WHITE)
    text(s, x + Inches(0.12), by + Inches(0.52), bw - Inches(0.24), Inches(0.7), h2, size=11.5, color=WHITE)
    if i < len(steps) - 1:
        a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x + bw - Inches(0.02), by + bh / 2 - Inches(0.12), gap + Inches(0.06), Inches(0.24))
        a.fill.solid(); a.fill.fore_color.rgb = rgb(MUTED); a.line.fill.background()
arr = s.shapes.add_shape(MSO_SHAPE.U_TURN_ARROW, Inches(5.3), by + bh + Inches(0.05), Inches(2.1), Inches(0.5)); arr.rotation = 180
arr.fill.solid(); arr.fill.fore_color.rgb = rgb("B8C4CC"); arr.line.fill.background()
text(s, Inches(7.5), by + bh + Inches(0.12), Inches(3.5), Inches(0.4), "repeat until feasible, at most 2 repeats per action", size=11, color=MUTED)
card(s, Inches(0.6), Inches(3.85), Inches(4.0), Inches(2.95), "Orchestrator 1: Claude", [
    "Claude Fable 5.1 drives the toolbox (claude_session.py): chooses each move, states the hypothesis before the run, reads the twin's verdict after",
    "Commercial model, documented; API key is a placeholder in the committed code",
    "8 turns, 7 evaluations, ~2 min; ~33k tokens (770 output + 32k context re-read), per-turn table in INTERACTION_EVIDENCE.md"], accent=ORANGE)
card(s, Inches(4.8), Inches(3.85), Inches(4.0), Inches(2.95), "Orchestrator 2: rule-based", [
    "Same tools, deterministic engineering heuristics, zero LLM tokens, fully offline and reproducible",
    "Explores 16 archetypes, 38 evaluations, ~5 min",
    "Both orchestrators converge on the same design"], accent=TEAL)
card(s, Inches(9.0), Inches(3.85), Inches(3.75), Inches(2.95), "Reasoning, memory, gates", [
    "Intake gate: missing inputs, out-of-scope asks and contradictory data are returned to the user before any run",
    "Memory: evaluation cache keyed on design signature, repeat guard, session state on disk",
    "Repairs are explicit rules with a stated cause, so every step is auditable"], accent=DEEP)
footer(s, 3)

# ================================================================== 4 GEMINI inside vs built by us
s = prs.slides.add_slide(BLANK)
title(s, "GEMINI gives the physics; plant, dispatcher and agent are ours", "Python, gemini_model called directly; numpy, pandas, scipy, matplotlib, scikit-learn, py-trsqp, petlab, anthropic SDK")
table(s, Inches(0.6), Inches(1.8), Inches(6.1), [
    ["GEMINI model (gemini_model)", "Used for"],
    ["bottomhole_skin_dp + IPR", "productivity / injectivity, drawdown vs flow"],
    ["DPDT wellbore P and T + PVT", "wellhead T and P, marched 100 m with the gradient"],
    ["ESP stage curve (HC27000)", "stages, VSD frequency, pump power; affinity-scaled frame"],
    ["CO2Corrosion (de Waard-Milliams)", "8 mm/yr un-mitigated -> material decision"],
    ["ErosionModel (API RP14E)", "erosional velocity -> casing ID check"]],
    [Inches(2.6), Inches(3.5)], font=11)
table(s, Inches(6.95), Inches(1.8), Inches(5.8), [
    ["Built for this challenge", "Model"],
    ["Plate heat exchanger", "3 C approach, 95 % effectiveness"],
    ["HT heat pump", "COP = 0.5 x Carnot, 85 C max lift"],
    ["Absorption chiller", "LiBr single effect, off < 72 C, COP 0.72 at >= 95 C"],
    ["Electric chiller, gas handling", "COP 5.5; CH4/CO2 at GLR 0.8, bubble point"],
    ["Daily dispatcher", "min brine flow, parallel heating/cooling split"],
    ["Cost model, closed loop, monitor", "ranking only; 25-year controller; ESP anomaly detection"]],
    [Inches(2.4), Inches(3.4)], font=11)
picture(s, CL / "fig_well_performance.png", Inches(0.6), Inches(4.45), w=Inches(8.0))
text(s, Inches(8.8), Inches(4.5), Inches(3.95), Inches(2.3), [
    [("Well performance from the twin", {"bold": True, "size": 13, "color": DEEP})],
    "ESP head and power across the 50-300 m3/h band; intake pressure stays 40 bar above the 29 bar bubble point, which is why the pump sits at 1,000 m.",
    "Tubing velocity 2.3 m/s at 300 m3/h, below the API erosional limit in 9-5/8\" casing.",
    [("Why these models", {"bold": True, "size": 12, "color": DEEP})],
    "Single-effect LiBr is the standard chiller for 90-100 C driving heat; 0.5 x Carnot matches published HT heat-pump COPs; 3 C approach is plate-HX practice. Simple enough to run 365 days in seconds, so the agent can iterate."], size=11, color=INK)
footer(s, 4)

# ================================================================== 5 How the agent got there (native chart)
s = prs.slides.add_slide(BLANK)
title(s, "How the agent got there: a number and a reason for every move", "Claude-orchestrated run, levelised cost per step; the twin rejected the two-doublet shortcut")
cd = CategoryChartData()
labels = ["2 dbl, 2,500 m\n31 MW heat pump", "3 dbl, 3,500 m\ndirect HX + abs", "3 dbl, 3,000 m", "3 dbl, 4,000 m", "2 dbl, 3,500 m\n15 MW HP (FAILS)", "3 dbl, 3,500 m\nelectric chiller", "final: trimmed\nHP 2.5 MW, ESP 170"]
vals = [86.0, 66.6, 92.1, 70.7, 57.2, 68.5, 63.8]
cd.categories = labels; cd.add_series("LCOE EUR/MWh", vals)
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.6), Inches(1.75), Inches(7.6), Inches(4.9), cd)
ch = gf.chart; ch.has_legend = False; ch.has_title = False
pl = ch.plots[0]; pl.gap_width = 60; pl.has_data_labels = True; pl.data_labels.font.size = Pt(11); pl.data_labels.number_format = '0.0'; pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
ser = pl.series[0]
for i, pt in enumerate(vals):
    p = ser.points[i]; p.format.fill.solid(); p.format.fill.fore_color.rgb = rgb(ORANGE if i == 6 else ("B8C4CC" if i == 4 else TEAL))
ch.category_axis.tick_labels.font.size = Pt(9.5); ch.value_axis.tick_labels.font.size = Pt(10); ch.value_axis.has_major_gridlines = True
ch.value_axis.major_gridlines.format.line.color.rgb = rgb("DDE3E7"); ch.value_axis.maximum_scale = 100; ch.value_axis.minimum_scale = 0
ch.category_axis.format.line.color.rgb = rgb("B8C4CC"); ch.value_axis.format.line.fill.background()
card(s, Inches(8.5), Inches(1.75), Inches(4.25), Inches(4.95), "Why the design is what it is", [
    "One doublet is infeasible: the 330-day rule leaves 35 days without supply",
    "The 40 C cap, not temperature, sets heat per doublet (~13.4 MW at 300 m3/h): 30 MW needs three",
    "2,500 m brine is 85 C: all heat lifted by a 31 MW heat pump, 36 GWh/yr electricity",
    "3,000 m is the worst of both: deep wells and still a heat pump",
    "3,500 m clears the 103 C direct-supply threshold; electricity falls to 7.8 GWh/yr",
    "4,000 m adds well cost for no extra cap-limited heat",
    "Two doublets + 15 MW heat pump fail 16 peak days: at the 40 C cap there is no source left for the heat pump",
    "Absorption cooling saves 4.3 GWh/yr versus electric chillers"], accent=ORANGE, body_size=11.5)
footer(s, 5)

# ================================================================== 6 Validation
s = prs.slides.add_slide(BLANK)
title(s, "Validated on all 365 days: every cap and every engineering guard", "Annual dispatch of the selected design; one doublet at a time is out for its 35-day window in the low-load season")
picture(s, CL / "fig_dispatch.png", Inches(0.6), Inches(1.75), h=Inches(5.0))
table(s, Inches(6.4), Inches(1.75), Inches(6.35), [
    ["Check", "Value", "Limit", ""],
    ["Flow per doublet", f"{K['peak_flow_per_doublet_m3_h']:.0f} peak / {K['mean_flow_per_doublet_m3_h']:.0f} mean", "50-300 m3/h", "pass"],
    ["Brine cooling", f"{K['max_brine_dt_c']:.1f} C max", "40 C", "pass"],
    ["Operating days per doublet", "330", "330", "pass"],
    ["Unmet heat / cooling", "0 / 0 GWh", "0", "pass"],
    ["ESP intake vs bubble point", f"{K['esp_intake_pressure_at_300_bar']:.0f} vs {K['bubble_point_bar']:.0f} bar", "> + 5 bar", "pass"],
    ["Tubing velocity", f"{K['tubing_velocity_at_300_m_s']:.1f} m/s", f"< {K['erosional_velocity_m_s']:.1f} m/s", "pass"],
    ["Injection wellhead pressure", f"{K['injection_whp_at_300_bar']:.0f} bar", "< 60 bar", "pass"],
    ["ESP power", f"{K['esp_power_at_300_mw'] * 1000:.0f} kW", "< 1,500 kW", "pass"]],
    [Inches(2.3), Inches(1.9), Inches(1.35), Inches(0.8)], font=11)
text(s, Inches(6.4), Inches(4.85), Inches(6.35), Inches(1.9), [
    [("Realized capacities and energy balance, year 1", {"bold": True, "size": 13, "color": DEEP})],
    "Heating 30.0 MW delivered on the peak day (28.2 MW direct HX + 1.8 MW heat pump; installed 3 x 13.7 MW HX + 2.5 MW HP). Cooling 10.0 MW delivered (10 MW absorption installed).",
    f"Heat {K['heat_delivered_gwh']:.1f} GWh (direct {K['heat_direct_gwh']:.1f}, heat pump {K['heat_hp_gwh']:.1f}); cooling {K['cool_delivered_gwh']:.1f} GWh, all absorption.",
    f"Electricity {K['electricity_gwh']:.1f} GWh: ESP {K['electricity_esp_gwh']:.1f}, injection {K['electricity_injection_gwh']:.1f}, heat pump {K['electricity_heat_pump_gwh']:.1f}, chillers {K['electricity_chillers_gwh']:.1f}. System COP {K['system_cop']:.1f}, geothermal share {K['geothermal_share'] * 100:.0f} %.",
    f"Associated gas {K['annual_gas_mnm3']:.2f} MNm3/yr (80 % CH4): a 1 MW gas engine on the CH4 yields 7.8 GWh/yr, the plant's whole electricity; CO2 balance 5,100 t/yr versus 7,500 t flaring with grid power at 0.3 kg/kWh."], size=11)
footer(s, 6)

# ================================================================== 7 Closed loop + uncertainty
s = prs.slides.add_slide(BLANK)
title(s, "Beyond the brief 1: 25-year closed loop under uncertainty", "The twin is re-run every year with reservoir cooling, injector skin growth and ESP wear; the controller books the interventions")
picture(s, CL / "fig_closed_loop.png", Inches(0.6), Inches(1.75), w=Inches(8.3))
card(s, Inches(9.2), Inches(1.75), Inches(3.55), Inches(2.45), "Controller actions", [
    "Acid stimulation when injector skin reaches +3 or WHP hits 85 % of its limit",
    "ESP workover at 90 % efficiency (about every 5 years)",
    "Heat-pump or chiller retrofit if produced temperature falls",
    "Spacing: breakthrough after 20 yr at 600 m, 36 yr at 800 m, > project life at 1,500 m"], accent=TEAL, body_size=11.5)
card(s, Inches(0.6), Inches(4.35), Inches(8.3), Inches(2.4), "Uncertainty: a six-member geological ensemble", [
    "Permeability lognormal around 200 mD (140-220 mD), gradient 30 +/- 1.5 C/km, injector skin varied; every candidate is re-scored on all members",
    "Finding: the design space has a cliff at ~3,250 m. A design sitting on it is cheapest on paper and collapses when the gradient is 1 C/km lower (worst case +30 % cost)",
    "The 3,500 m design keeps 250 m of margin; the recommendation is conditional on a temperature log confirming the gradient"], accent=ORANGE, body_size=11.5)
card(s, Inches(9.2), Inches(4.35), Inches(3.55), Inches(2.4), "What is still assumed", [
    "Permeability independent of depth", "Lumped Gringarten-Sauty breakthrough", "Degradation rates (0.6 skin/yr, 2 % ESP/yr) until field data replaces them"], accent=DEEP, body_size=11.5)
footer(s, 7)

# ================================================================== 8 Optimisers
s = prs.slides.add_slide(BLANK)
title(s, "Beyond the brief 2: optimisers confirm the agent, shave 5 %", "DFTR-Filter (py-trsqp), COBYLA and StoSAG robust optimisation via petlab's backend interface; every candidate re-run at full fidelity")
picture(s, OPT / "fig_optimizer_convergence.png", Inches(0.6), Inches(1.75), w=Inches(6.6))
table(s, Inches(7.4), Inches(1.75), Inches(5.35), [
    ["Candidate", "Depth", "HP", "MEUR/yr", "Worst"],
    ["Agent design", "3,500", "2.5", "8.63", "8.86"],
    ["DFTR from agent", "3,344", "0", "8.17", "8.65"],
    ["StoSAG robust", "3,335", "1.9", "8.42", "8.88"],
    ["COBYLA", "3,250", "0", "8.28", "10.63"],
    ["DFTR from 2,500 m", "3,938", "0", "8.86", "9.02"]],
    [Inches(1.75), Inches(0.9), Inches(0.7), Inches(1.0), Inches(1.0)], font=11, numeric=True)
text(s, Inches(7.4), Inches(3.8), Inches(5.35), Inches(0.4), "Depth in m, heat pump in MW, worst = highest cost over the ensemble", size=10, color=MUTED)
card(s, Inches(0.6), Inches(4.85), Inches(12.15), Inches(1.9), "What the optimisers taught us", [
    "They agree with the agent's structure (3 doublets, direct heating, absorption cooling) and find the sweet spot 150 m shallower: just deep enough for 100 C, no heat pump",
    "COBYLA sat on the 3,250 m cliff; DFTR kept 100 m of margin and stays cheapest in every realisation; StoSAG, optimising the ensemble mean, keeps a 1.9 MW heat pump as hedge",
    "Starting DFTR from the specified 2,500 m lands in a worse local optimum (deep wells, electric cooling): the agent's reasoning is the right starting point for a black-box optimiser"], accent=ORANGE, body_size=11.5)
footer(s, 8)

# ================================================================== 9 ESP monitoring
s = prs.slides.add_slide(BLANK)
title(s, "Beyond the brief 3: real-time ESP monitoring closes the loop", "Hourly telemetry against the same twin; anomaly detection, fault naming, health index and remaining useful life")
picture(s, MON / "fig_esp_monitoring.png", Inches(0.6), Inches(1.75), h=Inches(5.0))
card(s, Inches(6.4), Inches(1.75), Inches(6.35), Inches(2.55), "How it works", [
    "Twin residuals: measured head, intake pressure and power minus the GEMINI expectation at the measured frequency and flow",
    "Detectors: robust Mahalanobis distance (MCD), Isolation Forest, CUSUM on hydraulic efficiency for slow drift; trained on 14 healthy days, no labels",
    "Signature classifier: gas interference, stage wear / scale, motor thermal, trip; each with a recommended action for the dispatcher or controller"], accent=TEAL, body_size=11.5)
stat(s, Inches(6.5), Inches(4.5), Inches(2.0), "91 %", "recall on fault hours", big_size=32)
stat(s, Inches(8.6), Inches(4.5), Inches(2.0), "0.7 %", "false alarms on healthy hours", big_size=32)
stat(s, Inches(10.7), Inches(4.5), Inches(2.0), "100 %", "faults correctly named", big_size=32)
text(s, Inches(6.4), Inches(5.9), Inches(6.35), Inches(0.9), [
    "Synthetic telemetry (no field data in the challenge) with four injected faults the detector was not told about. The health index replaces the assumed ESP wear rate in the 25-year loop and the RUL brings the workover forward; a trip or gas slug is re-balanced across doublets by the dispatcher."], size=11.5, color=INK)
footer(s, 9)

# ================================================================== 10 Evidence, deliverables, limits (dark)
s = prs.slides.add_slide(BLANK); rect(s, 0, 0, W, H, DEEP)
title(s, "Evidence, deliverables and what we would do next", "Everything runs offline from the command line in about five minutes; 13 unit tests pass", dark=True)
card(s, Inches(0.6), Inches(1.8), Inches(4.0), Inches(4.4), "Agent interaction evidence", [
    "Heating file without cooling file: the agent lists the three missing inputs and asks whether to proceed on heating only",
    "'Design a 50 MWe ORC power plant': declined, direct use only",
    "'Which stock should I buy': declined, not an engineering question",
    "'The reservoir is 140 C at 2,500 m': flagged as contradicting the 30 C/km gradient (87 C); refuses to size until resolved, because the design flips on it",
    "Full exchanges in INTERACTION_EVIDENCE.md; design reasoning in orchestration_log.md"], accent=ORANGE, body_size=11.5)
card(s, Inches(4.8), Inches(1.8), Inches(4.0), Inches(4.4), "Deliverables", [
    "This deck (10 slides) and the 5-minute pitch",
    "Code pushed to the GEMINI repository: gemini_design_agent (spec, demand, components, subsurface, system, agent, closed_loop, intake, esp_monitoring, optimize_ext, report, cli, tests)",
    "Generated reports: DESIGN_REPORT (both modes), OPTIMIZATION_REPORT, ESP_MONITORING_REPORT",
    "Interactive dashboard with 14 data sources: " + DASH,
    "Zip with all outputs as a fallback attachment"], accent=TEAL, body_size=11.5)
card(s, Inches(9.0), Inches(1.8), Inches(3.75), Inches(4.4), "Limits and next steps", [
    "Costs are indicative planning figures used to rank, not to budget",
    "Claude is a commercial model; the rule-based mode gives the same design with zero tokens",
    "Monitoring telemetry is synthetic; the classifier is signature-based until field events exist",
    "Next: assimilate produced temperature and injection pressure each year to update the ensemble (EnKF), then re-run StoSAG on the updated ensemble: the model-updating half of closed-loop reservoir management",
    "Next: contribute the chiller, heat-pump and monitor models back to GEMINI"], accent=DEEP, body_size=11.5)
footer(s, 10, dark=True)

prs.save(OUT)
print("written", OUT, "slides", len(prs.slides))
