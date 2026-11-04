"""Build the 10-slide pitch deck for the 5-minute video: one message per slide, few words.
python build_pitch.py
"""
from __future__ import annotations
import json
from pathlib import Path
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "GEMINI_Hackathon_Pitch_Ramdhan_Wibawa.pptx"
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


def rect(sl, x, y, w, h, fill, shape=MSO_SHAPE.RECTANGLE):
    s = sl.shapes.add_shape(shape, x, y, w, h); s.fill.solid(); s.fill.fore_color.rgb = rgb(fill)
    s.line.fill.background(); s.shadow.inherit = False
    return s


def text(sl, x, y, w, h, runs, size=18, color=INK, bold=False, font=BODY, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         space_after=6, line_spacing=1.05):
    tb = sl.shapes.add_textbox(x, y, w, h); tf = tb.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0; tf.vertical_anchor = anchor
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align; p.space_after = Pt(space_after); p.line_spacing = line_spacing
        segs = para if isinstance(para, list) else [(para, {})]
        for seg, o in segs:
            r = p.add_run(); r.text = seg
            f = r.font; f.name = o.get("font", font); f.size = Pt(o.get("size", size)); f.bold = o.get("bold", bold)
            f.color.rgb = rgb(o.get("color", color))
    return tb


def headline(sl, t, dark=False, size=36):
    text(sl, Inches(0.7), Inches(0.5), Inches(12.0), Inches(1.4), t, size=size, bold=True, font=HEAD,
         color=WHITE if dark else DEEP, line_spacing=1.0)


def footer(sl, n, dark=False):
    c = "9FB3BF" if dark else MUTED
    text(sl, Inches(0.7), Inches(7.05), Inches(9), Inches(0.3), "GEMINI Agentic Geothermal Design Hackathon 2026  |  R. A. Wibawa", size=10, color=c)
    text(sl, Inches(12.2), Inches(7.05), Inches(0.5), Inches(0.3), str(n), size=10, color=c, align=PP_ALIGN.RIGHT)


def stat(sl, x, y, w, big, label, color=ORANGE, big_size=54, label_color=MUTED):
    text(sl, x, y, w, Inches(1.0), big, size=big_size, bold=True, font=HEAD, color=color)
    text(sl, x, y + Inches(1.05), w, Inches(0.6), label, size=16, color=label_color)


def picture(sl, path, x, y, w=None, h=None):
    return sl.shapes.add_picture(str(path), x, y, width=w, height=h)


def takeaway(sl, t, y=Inches(6.2), dark=False):
    """One-sentence message strip at the bottom."""
    text(sl, Inches(0.7), y, Inches(12.0), Inches(0.7), t, size=20, color=WHITE if dark else TEAL, bold=True)


# ================================================================== 1 Title
s = prs.slides.add_slide(BLANK); rect(s, 0, 0, W, H, DEEP)
rect(s, Inches(8.9), 0, Inches(4.433), H, "143A4F")
text(s, Inches(0.8), Inches(1.4), Inches(7.6), Inches(0.4), "SPE EUROPE ENERGY GEOHACKATHON 2026  |  EXPRESS EDITION", size=13, bold=True, color="9FB3BF")
text(s, Inches(0.8), Inches(2.0), Inches(7.6), Inches(3.0),
     "Three doublets at 3,500 m, direct heating and brine-driven cooling", size=38, bold=True, font=HEAD, color=WHITE, line_spacing=1.0)
text(s, Inches(0.8), Inches(4.6), Inches(7.6), Inches(0.9), "An AI agent designed it. The GEMINI digital twin verified every step.", size=18, color="CADCE3")
text(s, Inches(0.8), Inches(5.9), Inches(7.6), Inches(0.9), [[("Ramdhan Ari Wibawa", {"bold": True, "color": WHITE, "size": 16})],
     [("ramdhan@zanskar.us  |  4 November 2026", {"color": "9FB3BF", "size": 12})]], size=12)
stat(s, Inches(9.4), Inches(1.5), Inches(3.5), "3 x 3,500 m", "doublets, depth", color=ORANGE, big_size=40, label_color="CADCE3")
stat(s, Inches(9.4), Inches(3.2), Inches(3.5), "COP 17", "heat + cooling per unit of electricity", color=WHITE, big_size=40, label_color="CADCE3")
stat(s, Inches(9.4), Inches(4.9), Inches(3.5), "0 unmet", "365 days, every limit passed", color=WHITE, big_size=40, label_color="CADCE3")
footer(s, 1, dark=True)

# ================================================================== 2 Problem
s = prs.slides.add_slide(BLANK)
headline(s, "A district needs heat and cooling. The reservoir on offer is too cold.")
stat(s, Inches(0.7), Inches(2.5), Inches(3.9), "30 + 10 MW", "heating at 100 C, cooling at 20 C", big_size=44)
stat(s, Inches(4.8), Inches(2.5), Inches(3.9), "2,500 m", "reservoir in the brief", big_size=44)
stat(s, Inches(8.9), Inches(2.5), Inches(3.9), "87 C", "brine: 13 C short of the network", big_size=44)
takeaway(s, "We gave the problem to an AI agent with the GEMINI digital twin: design it, prove it, explain it.", y=Inches(4.9))
footer(s, 2)

# ================================================================== 3 How the agent works
s = prs.slides.add_slide(BLANK)
headline(s, "The agent works like an engineer: propose, test on the twin, fix, repeat")
steps = [("Propose", ORANGE), ("Evaluate", TEAL), ("Diagnose", TEAL), ("Repair", TEAL)]
bx, by, bw, bh, gap = Inches(0.7), Inches(2.4), Inches(2.75), Inches(1.5), Inches(0.3)
for i, (h1, c) in enumerate(steps):
    x = bx + i * (bw + gap)
    r = rect(s, x, by, bw, bh, c, MSO_SHAPE.ROUNDED_RECTANGLE); r.adjustments[0] = 0.15
    text(s, x, by, bw, bh, h1, size=26, bold=True, color=WHITE, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    if i < 3:
        a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x + bw + Inches(0.02), by + bh / 2 - Inches(0.15), gap - Inches(0.04), Inches(0.3))
        a.fill.solid(); a.fill.fore_color.rgb = rgb(MUTED); a.line.fill.background()
text(s, Inches(0.7), Inches(4.4), Inches(12.0), Inches(1.4), [
    [("GEMINI", {"bold": True, "color": DEEP}), ("  supplies the well, pump, corrosion and erosion physics.", {})],
    [("We built", {"bold": True, "color": DEEP}), ("  the heat exchanger, heat pump, chillers and dispatcher that GEMINI did not have.", {})],
    [("Every move", {"bold": True, "color": DEEP}), ("  is logged with its reasoning and its token count. A rule-based mode gives the same design with no LLM.", {})]],
    size=18, space_after=10)
footer(s, 3)

# ================================================================== 4 The answer
s = prs.slides.add_slide(BLANK)
headline(s, "The answer: drill deeper. Hot brine feeds the network directly and drives the chiller.")
stat(s, Inches(0.7), Inches(2.5), Inches(3.9), "30 + 10 MW", "delivered on the peak day", big_size=44)
stat(s, Inches(4.8), Inches(2.5), Inches(3.9), "94 %", "of the energy from the ground", big_size=44)
stat(s, Inches(8.9), Inches(2.5), Inches(3.9), f"{COST['levelised_cost_eur_per_mwh']:.0f} EUR", "per MWh delivered (indicative)", big_size=44)
text(s, Inches(0.7), Inches(4.6), Inches(12.0), Inches(1.4), [
    "3 doublets at 3,500 m  |  direct plate heat exchange  |  10 MW absorption chiller on the brine  |  2.5 MW heat pump for cold spells"],
    size=18, color=INK)
takeaway(s, "One decision, depth, removes almost all the electricity the shallow design needed.", y=Inches(5.5))
text(s, Inches(0.7), Inches(6.15), Inches(12.0), Inches(0.6), "And the methane in the brine, burned in a 1 MW engine, can supply what is left.", size=18, color=INK)
footer(s, 4)

# ================================================================== 5 Why: the alternatives
s = prs.slides.add_slide(BLANK)
headline(s, "Every alternative was tried and rejected with a number: cost in EUR per MWh")
cd = CategoryChartData()
cd.categories = ["Shallow, 31 MW heat pump", "3,000 m", "4,000 m", "2 doublets (fails)", "Electric chillers", "Selected"]
cd.add_series("Cost, EUR/MWh", [86.0, 92.1, 70.7, 57.2, 68.5, 63.8])
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.7), Inches(1.9), Inches(12.0), Inches(4.2), cd)
ch = gf.chart; ch.has_legend = False; ch.has_title = False
pl = ch.plots[0]; pl.gap_width = 60; pl.has_data_labels = True
pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END; pl.data_labels.font.size = Pt(14); pl.data_labels.number_format = '0.0'; pl.data_labels.number_format_is_linked = False
ser = pl.series[0]
for i, pt_color in enumerate([MUTED, MUTED, MUTED, "B23A3A", MUTED, ORANGE]):
    pt = ser.points[i]; pt.format.fill.solid(); pt.format.fill.fore_color.rgb = rgb(pt_color)
ch.value_axis.visible = False; ch.value_axis.has_major_gridlines = False
ch.category_axis.tick_labels.font.size = Pt(13); ch.category_axis.format.line.fill.background()
takeaway(s, "The two-doublet shortcut looks cheapest and fails 16 peak days. The agent kept three.", y=Inches(6.25))
footer(s, 5)

# ================================================================== 6 Proof
s = prs.slides.add_slide(BLANK)
headline(s, "Proven on all 365 days: every limit in the brief passes")
picture(s, CL / "fig_dispatch.png", Inches(0.7), Inches(1.9), h=Inches(4.3))
x0 = Inches(8.4)
stat(s, x0, Inches(2.0), Inches(4.5), "8 of 8", "challenge limits pass every day", big_size=44)
stat(s, x0, Inches(3.9), Inches(4.5), "+3", "engineering guards we added: gas, erosion, injection", big_size=44, color=TEAL)
footer(s, 6)

# ================================================================== 7 Uncertainty + 25 years
s = prs.slides.add_slide(BLANK)
headline(s, "Beyond the brief: the design is tested against uncertain geology and 25 years of operation")
picture(s, CL / "fig_closed_loop.png", Inches(0.7), Inches(2.1), w=Inches(7.6))
text(s, Inches(8.6), Inches(2.1), Inches(4.3), Inches(4.0), [
    [("Uncertainty", {"bold": True, "color": DEEP, "size": 20})],
    "Re-run over a range of permeability and gradient. We found a cliff at 3,250 m; our design keeps 250 m of margin.",
    [("Operations", {"bold": True, "color": DEEP, "size": 20})],
    "A yearly controller re-runs the twin with reservoir cooling and pump wear and books acid jobs and workovers."], size=16, space_after=10)
footer(s, 7)

# ================================================================== 8 Optimisers
s = prs.slides.add_slide(BLANK)
headline(s, "Three external optimisers agree with the agent and trim the cost by 5 %")
picture(s, OPT / "fig_optimizer_convergence.png", Inches(0.7), Inches(2.1), w=Inches(7.6))
text(s, Inches(8.6), Inches(2.1), Inches(4.3), Inches(4.0), [
    "Same structure: three doublets, direct heating, absorption cooling.",
    "Sweet spot 150 m shallower, just deep enough for 100 C.",
    "Started from the brief's 2,500 m, the optimiser lands in a worse design. The agent's reasoning is the right starting point."],
    size=16, space_after=12)
footer(s, 8)

# ================================================================== 9 Monitoring
s = prs.slides.add_slide(BLANK)
headline(s, "Live pump monitoring closes the loop: faults are caught from telemetry and fed back into the plan")
picture(s, MON / "fig_esp_monitoring.png", Inches(0.7), Inches(1.9), h=Inches(4.2))
x0 = Inches(8.8)
stat(s, x0, Inches(2.0), Inches(4.0), "91 %", "of fault hours detected", big_size=44)
stat(s, x0, Inches(3.6), Inches(4.0), "< 1 %", "false alarms", big_size=44, color=TEAL)
stat(s, x0, Inches(5.2), Inches(4.0), "4 of 4", "faults correctly named", big_size=44, color=DEEP)
footer(s, 9)

# ================================================================== 10 Close
s = prs.slides.add_slide(BLANK); rect(s, 0, 0, W, H, DEEP)
headline(s, "The agent knows its limits", dark=True)
text(s, Inches(0.7), Inches(2.0), Inches(12.0), Inches(2.6), [
    "Incomplete data: it lists what is missing and asks before running.",
    "Out-of-scope request: it declines.",
    "Contradictory inputs: it refuses to size the plant until they are resolved."], size=22, color="CADCE3", space_after=12)
text(s, Inches(0.7), Inches(4.9), Inches(12.0), Inches(1.6), [
    [("Open source. Runs offline in five minutes. Pushed to the GEMINI repository.", {"bold": True, "color": WHITE, "size": 20})],
    [("Dashboard: " + DASH, {"color": "9FB3BF", "size": 14})],
    [("Thank you.", {"color": ORANGE, "size": 24, "bold": True, "font": HEAD})]], size=16, space_after=10)
footer(s, 10, dark=True)

prs.save(OUT)
print("written", OUT, "slides", len(prs.slides))
