"""GEMINI GeoDesign cockpit (Gradio): one page, a chat with the design agent.

Each answer comes with its steps (collapsible), the verifier's verdict and, when the turn produced a
design, the design's figures, constraint checklist and heat supply chart in the chat. Recorded
evidence sessions can be replayed.

Run:  PYTHONPATH=src python -m gemini_agent.ui.app   (serves on 127.0.0.1:7860)
"""

from __future__ import annotations

import html
import json
import os
from pathlib import Path

import gradio as gr

from gemini_agent.agents import DEFAULT_MODEL
from gemini_agent.service import Evaluation
from gemini_agent.ui import charts
from gemini_agent.ui.steps import annotate_turn, live_step, step_messages

# Direction: exact, calm, a little warm. Graphite neutrals; one ember accent (heat from the ground)
# for the primary action, selection and geothermal heat; IBM Plex for an engineer's legibility.
EMBER, EMBER_DARK, INK, INK2, MUTED = "#c2410c", "#9a3412", "#171717", "#525252", "#737373"
HAIR, HAIR2 = "rgba(23,23,23,0.08)", "rgba(23,23,23,0.14)"

CSS = """
/* one-page layout: the page never scrolls; the chat (and the left column) scroll inside */
html, body {height: 100%; overflow: hidden;}
body > .gradio-container, .gradio-container.app {height: 100vh !important; min-height: 0 !important;
  display: flex; flex-direction: column; overflow: hidden;}
.gradio-container {width: 100% !important; max-width: 1600px !important; margin: 0 auto
!important; padding: 12px 32px 12px !important; box-sizing: border-box;}
.gradio-container > .main, .gradio-container .wrap.main {width: 100%;}
.gradio-container > .main {flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column;}
.gradio-container > .main > .wrap {flex: 1 1 auto; min-height: 0 !important; display: flex;
  flex-direction: column; overflow: hidden;}
.gradio-container main.contain {flex: 1 1 auto; min-height: 0 !important; overflow: hidden;}
/* Gradio's root column and the unequal-height row must stretch for the chat to fill the page */
.gradio-container .contain > .column:has(> #gd-main) {flex: 1 1 auto !important; min-height: 0;
  overflow: hidden;}
/* basis 0: the row's height comes from the page, never from the settings column's content */
#gd-main {flex: 0 0 auto !important; height: calc(100vh - 128px) !important; min-height: 0;
  align-items: stretch !important; overflow: hidden;}  /* fixed: header ~114 px + padding */
#gd-left {overflow-y: auto; min-height: 0; max-height: 100%; height: 100%;}
/* Gradio columns wrap overflow into a hidden second column: keep one column that scrolls */
#gd-left {flex-wrap: nowrap !important;}
#gd-left > * {flex-shrink: 0 !important;}  /* panels keep their height; the column scrolls */
#gd-right {display: flex; flex-direction: column; min-height: 0; height: 100%; gap: 10px;
  overflow: hidden;}
/* the chat and the input block are positioned inside the right column, so the chat's content can
   never push the input out of view: chat = column height minus the input block */
#gd-right {position: relative;}
#gd-chat {position: absolute !important; top: 0; left: 0; right: 0;
  height: calc(100% - 176px) !important; min-height: 0; overflow: hidden !important;}
#gd-input, #gd-input.column {position: absolute; left: 0; right: 0; bottom: 0; height: 166px;
  overflow: hidden;}
#gd-input .gallery {max-height: 66px; overflow: hidden;}
/* charts in the chat: Plotly autosizes to its container on every zoom; without a minimum height the
   container collapses to 0 and the chart vanishes */
#gd-chat .js-plotly-plot {min-height: 320px;}
#gd-chat .wrapper {display: flex; flex-direction: column; height: 100%; min-height: 0;}
#gd-chat .panel-wrap, #gd-chat .bubble-wrap {flex: 1 1 auto !important; min-height: 0;
  max-height: 100%; overflow-y: auto !important;}
#gd-chat > .wrapper, #gd-chat .bubble-wrap, #gd-chat .message-wrap {min-height: 0;}
#gd-chat .bubble-wrap {height: 100% !important; max-height: none !important; overflow-y: auto;}
#gd-input, #gd-input.column {flex: 0 0 auto !important; flex-grow: 0 !important; min-height: 0;
  gap: 6px;}
#gd-input .gallery {gap: 6px !important;}
#gd-input .examples, #gd-input .gallery {padding-top: 0 !important;}
.tabs, .tabitem {width: 100%;}
.gradio-container, .gradio-container * {font-feature-settings: "tnum" 1;}
.gd-head {padding: 0 0 8px; border-bottom: 1px solid rgba(23,23,23,0.08); margin-bottom: 4px;
  flex: 0 0 auto;}
.gd-head h1 {font-size: 22px; font-weight: 500; color: #171717; margin: 0; letter-spacing: -0.01em;}
.gd-head h1 span {color: #c2410c;}
.gd-head p {font-size: 14px; color: #525252; margin: 0;}
.gd-head .gd-rule {color: #737373;}
.prose em, .prose i {font-style: normal; color: #737373;}
.prose h3 {font-size: 16px; font-weight: 500; color: #171717; margin: 8px 0 4px;}
.gd-cards {display: grid; grid-template-columns: repeat(12, 1fr); gap: 12px;}
.gd-card {grid-column: span var(--span, 3); min-width: 0;}
.gd-design {margin: 0 0 12px; font-size: 13px; color: #525252;}
.gd-design p {margin: 4px 0 0; font-size: 15px; font-weight: 500; color: #171717;}
.gd-card {background: #ffffff; border: 1px solid rgba(23,23,23,0.08); border-radius: 12px;
padding: 16px;}
.gd-card .v {font-size: 28px; font-weight: 500; color: #171717; line-height: 1; white-space:
nowrap;}
.gd-card .v small {font-size: 13px; font-weight: 400; color: #525252; margin-left: 4px;}
.gd-card .l {font-size: 13px; color: #525252; margin-top: 8px; line-height: 18px;}
.gd-card.lead .v {color: #9a3412;}
.gd-checks-head {font-size: 14px; font-weight: 500; color: #171717; margin: 4px 0 8px;}
.gd-checks {list-style: none; padding: 0; margin: 0;}
.gd-checks li {display: grid; grid-template-columns: 20px 1fr auto; align-items: baseline; gap:
8px; padding: 8px 0; border-bottom: 1px solid rgba(23,23,23,0.06); font-size: 14px; color: #171717;}
.gd-checks li:last-child {border-bottom: 0;}
.gd-ok {color: #16a34a;}
.gd-bad {color: #dc2626; font-weight: 500;}
.gd-muted {color: #737373; font-size: 13px; font-family: var(--font-mono);}
.gd-meter {font-size: 13px; color: #525252;}
.gd-meter b {font-weight: 500; color: #171717; font-family: var(--font-mono);}
kbd {font-family: var(--font-mono); font-size: 12px; padding: 1px 6px; border-radius: 4px;
border: 1px solid rgba(23,23,23,0.14); border-bottom-width: 2px;
  background: #fafafa; color: #171717;}
footer {display: none !important;}
#gd-left .wrap label {padding: 8px 12px !important;}
#gd-left {gap: 12px;}
.gd-acc {background: #ffffff !important; border: 1px solid rgba(23,23,23,0.08) !important;
border-radius: 12px !important;}
.gd-acc .block {border: 0 !important; box-shadow: none !important; padding: 4px 0 !important;
background: transparent !important;}
.gd-acc .form {border: 0 !important; gap: 8px; background: transparent !important;}
.gd-file {min-height: 0 !important;}
.gd-file .file-preview-holder, .gd-file table {max-height: none !important; overflow: visible
!important;}
.gd-file button.center {min-height: 96px; padding: 12px !important;}
.gd-file .wrap {font-size: 13px !important; line-height: 1.4 !important;}
.gd-details {margin-top: 16px;}
#gd-chat .prose {font-size: 14.5px; line-height: 1.6; color: #171717;}
#gd-chat .prose h1, #gd-chat .prose h2, #gd-chat .prose h3, #gd-chat .prose h4 {font-size: 16px
!important;
  font-weight: 600 !important; margin: 14px 0 6px !important; letter-spacing: 0;}
#gd-chat .prose strong {font-weight: 600;}
#gd-chat .prose code {font-family: var(--font-mono); font-size: 12.5px; background: #f4f4f5;
padding: 1px 5px;
  border-radius: 4px; border: 0;}
#gd-chat .prose ul, #gd-chat .prose ol {margin: 4px 0 10px; padding-left: 20px;}
#gd-chat .prose li {margin: 2px 0;}
#gd-chat .prose hr {border: 0; border-top: 1px solid rgba(23,23,23,0.08); margin: 12px 0 8px;}
#gd-chat .user.message {background: #f4f4f5 !important; border-radius: 12px !important;}
#gd-chat .bot.message {background: #ffffff !important;}
.gd-ok {color: #16a34a; font-weight: 600; margin-right: 2px;}
.gd-run {color: #c2410c; font-weight: 700; margin-right: 2px;}
.gd-warn {color: #b45309; font-weight: 700; margin-right: 2px;}
.gd-bad {color: #dc2626; font-weight: 600;}
.gd-who {font-family: var(--font-mono); font-size: 11.5px; color: #9a3412; background: #fff7ed;
padding: 1px 6px;
  border-radius: 4px; margin-right: 6px;}
.gd-res {color: #737373;}
#gd-chat .thought-group .arrow {transform: none !important; display: inline-flex; align-items:
center; justify-content: center;
  width: 18px; height: 18px;}
#gd-chat .thought-group .arrow .icon-button {background: transparent !important; border: 0
!important; padding: 0 !important;
  width: 18px; height: 18px; display: flex; align-items: center; justify-content: center;}
#gd-chat .thought-group .arrow svg {display: none !important;}
#gd-chat .thought-group .arrow .icon-button::before {content: ""; width: 6px; height: 6px;
border-right: 1.5px solid #737373;
  border-bottom: 1.5px solid #737373; transform: translateY(-2px) rotate(45deg); transition:
  transform 150ms ease;}
#gd-chat .thought-group .title.expanded .arrow .icon-button::before {transform: translateY(2px)
rotate(-135deg);}
#gd-chat .children .thought-group > .content {padding-left: 30px !important;}
#gd-chat .children .thought-group > .content .prose {font-size: 13px !important; color:
#525252; line-height: 1.55;}
#gd-chat .children .thought-group > .content .prose p {margin: 2px 0 !important;}
.gd-info {display: inline-flex; align-items: center; justify-content: center; width: 15px;
height: 15px; margin-left: 6px;
  border: 1px solid rgba(23,23,23,0.3); border-radius: 50%; font: italic 500 10px/1 Georgia,
  serif; color: #525252;
  cursor: help; position: relative; vertical-align: middle;}
.gd-info:hover, .gd-info:focus {border-color: #c2410c; color: #c2410c; outline: none;}
.gd-tip {position: fixed; z-index: 1000; padding: 10px 12px; background: #171717; color:
#fafafa; border-radius: 8px;
  font: 400 13px/1.45 'IBM Plex Sans', sans-serif; box-shadow: 0 8px 24px rgba(0,0,0,0.18);
  pointer-events: none;}
.gd-details summary {cursor: pointer; font-size: 14px; font-weight: 500; color: #171717;
padding: 4px 0;}
.gd-design {margin-bottom: 12px;}
.gd-opts {width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 14px;}
.gd-opts th {text-align: left; font-weight: 500; color: #525252; border-bottom: 1px solid
rgba(23,23,23,0.14); padding: 6px 8px;}
.gd-opts td {padding: 6px 8px; border-bottom: 1px solid rgba(23,23,23,0.06);}
.gd-opts .n {text-align: right; font-family: var(--font-mono);}
.gd-opts .d {color: #737373; font-family: var(--font-mono); font-size: 13px;}
.gd-opts tr.sel td {color: #9a3412; font-weight: 500;}

"""


def cockpit_theme() -> gr.themes.Base:
    """Graphite light theme, one ember accent, IBM Plex type."""
    t = gr.themes.Base(
        primary_hue=gr.themes.colors.orange,
        neutral_hue=gr.themes.colors.neutral,
        font=[
            gr.themes.GoogleFont("IBM Plex Sans", weights=(400, 500, 600)),
            "Segoe UI",
            "sans-serif",
        ],
        font_mono=[
            gr.themes.GoogleFont("IBM Plex Mono", weights=(400, 500)),
            "Consolas",
            "monospace",
        ],
        radius_size=gr.themes.sizes.radius_md,
        spacing_size=gr.themes.sizes.spacing_md,
        text_size=gr.themes.sizes.text_md,
    )
    return t.set(
        body_background_fill="#fafafa",
        body_text_color=INK,
        body_text_color_subdued=MUTED,
        body_text_size="14px",
        background_fill_primary="#ffffff",
        background_fill_secondary="#f4f4f5",
        border_color_primary=HAIR,
        color_accent=EMBER,
        color_accent_soft="#f4f4f5",
        border_color_accent=EMBER,
        block_background_fill="#ffffff",
        block_border_color=HAIR,
        block_border_width="1px",
        block_radius="12px",
        block_shadow="none",
        block_padding="16px",
        layout_gap="16px",
        block_label_background_fill="transparent",
        block_label_text_color=INK2,
        block_label_text_weight="500",
        block_label_text_size="13px",
        block_label_border_width="0",
        block_label_shadow="none",
        block_title_background_fill="transparent",
        block_title_text_color=INK,
        block_title_text_weight="500",
        block_title_text_size="13px",
        block_title_border_width="0",
        block_title_padding="0",
        input_background_fill="#ffffff",
        input_border_color=HAIR2,
        input_border_color_hover="rgba(23,23,23,0.24)",
        input_border_color_focus=EMBER,
        input_border_width="1px",
        button_primary_background_fill=EMBER,
        button_primary_background_fill_hover=EMBER_DARK,
        button_primary_border_color=EMBER,
        button_primary_text_color="#ffffff",
        button_primary_shadow="none",
        button_secondary_background_fill="#ffffff",
        button_secondary_background_fill_hover="#f4f4f5",
        button_secondary_border_color=HAIR2,
        button_secondary_text_color=INK,
        button_secondary_shadow="none",
        button_large_radius="8px",
        button_small_radius="6px",
        button_large_text_weight="500",
        button_large_text_size="14px",
        button_large_padding="10px 16px",
        checkbox_label_background_fill="#ffffff",
        checkbox_label_background_fill_hover="#f4f4f5",
        checkbox_label_background_fill_selected="#fff7ed",
        checkbox_label_border_color=HAIR2,
        checkbox_label_border_color_selected=EMBER,
        checkbox_label_text_color_selected=EMBER_DARK,
        checkbox_label_text_weight="400",
        checkbox_label_shadow="none",
        slider_color=EMBER,
        chatbot_text_size="14px",
    )


def kpi_cards(ev: Evaluation) -> str:
    """Design figures: LCOE, CO2 and geothermal share lead; the rest follow."""
    k, e = ev.kpis, ev.economics
    met = 365 - k["days_with_unmet"]
    cards = [
        (f"{e['lcoe_eur_per_mwh']:.1f}", "€/MWh", "Levelised cost of heat and cooling", True),
        (
            f"{k['co2_t']:,.0f}",
            "t CO₂/yr",
            f"{e['co2_intensity_kg_per_mwh']:.0f} kg per MWh delivered",
            True,
        ),
        (f"{k['geothermal_share_of_heat_pct']:.1f}", "%", "Heat from geothermal", True),
        (f"{met}", "/ 365", "Days with heating and cooling met", False),
        (f"{e['capex_total_meur']:.1f}", "M€", "Total CAPEX", False),
        (f"{k['max_brine_dt_k']:.1f}", "°C", "Brine temperature drop, limit 40 °C", False),
    ]
    if k.get("hp_spf"):
        cards.append((f"{k['hp_spf']:.2f}", "", "Heat pump seasonal COP", False))
    rest = sum(1 for c in cards if not c[3])

    def span(lead: bool) -> int:  # three leads on top, the rest share a row
        return 4 if lead else 12 // rest

    body = "".join(
        f'<div class="gd-card{" lead" if lead else ""}" style="--span:{span(lead)}"><div '
        f'class="v">{v}'
        f'<small>{u}</small></div><div class="l">{l}</div></div>'
        for v, u, l, lead in cards
    )
    return f'<div class="gd-cards">{body}</div>'


CHECK_TEXT = {
    "flow_within_50_300_m3h_per_active_doublet": "Flow 50–300 m³/h per active doublet",
    "brine_cooling_le_40K": "Brine cooled by at most 40 °C",
    "heating_demand_met_all_365_days": "Heating demand met on all 365 days",
    "cooling_demand_met_all_365_days": "Cooling demand met on all 365 days",
    "geothermal_operating_days_le_330_per_doublet": "Each doublet online at most 330 days",
    "production_equals_injection_volume": "Production equals injection volume",
    "n_doublets_1_to_3": "Between 1 and 3 doublets",
    "thermal_breakthrough_after_lifetime": "Thermal breakthrough after the design life",
    "heat_pump_cop_physical": "Heat-pump COP physically plausible",
}


def _fmt(v, sep: str = ", ") -> str:
    """Compact value: 300.0 -> 300, per-doublet [330, 267] -> 330, 267, a limit range -> 50–300."""
    if v is None:
        return "none"
    if isinstance(v, (list, tuple)):
        return sep.join(_fmt(x) for x in v)
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def checklist(ev: Evaluation, collapsible: bool = False) -> str:
    """Constraint checklist: icon + label + value (never colour alone)."""
    rows = []
    for c in ev.checks["checks"]:
        icon = '<span class="gd-ok">✓</span>' if c["passed"] else '<span class="gd-bad">✗</span>'
        label = CHECK_TEXT.get(c["check"], c["check"].replace("_", " ").capitalize())
        if not c["passed"]:
            label = f'<span class="gd-bad">{html.escape(label)}</span>'
        else:
            label = html.escape(label)
        rows.append(
            f"<li>{icon}<span>{label}</span><span class='gd-muted'>{html.escape(_fmt(c['value']))}"
            f" · limit {html.escape(_fmt(c['limit'], '–'))}</span></li>"
        )
    head = (
        "All hard constraints satisfied"
        if ev.checks["passed"]
        else f"{len(ev.checks['violations'])} constraint violation(s)"
    )
    if collapsible:
        return (
            f"<details class='gd-details'><summary>Verifier · {head}</summary>"
            f"<ul class='gd-checks'>{''.join(rows)}</ul></details>"
        )
    return f"<div class='gd-checks-head'>Verifier · {head}</div><ul class='gd-checks'>{''.join(rows)}</ul>"  # noqa: E501


DATA_DIR = Path(__file__).resolve().parents[3] / "dataset" / "geohackathon2026"
DEFAULT_HEAT = DATA_DIR / "GEMINI_Heating_Demand_Daily_2027.csv"
DEFAULT_COOL = DATA_DIR / "GEMINI_Cooling_Demand_Daily_2027.csv"
BAKEOFF = Path(__file__).resolve().parents[3] / "docs_geohackathon2026" / "evidence" / "bakeoff"


def model_choices(names: list[str]) -> list[tuple[str, str]]:
    """Dropdown entries labelled with the bake-off result; the recommended default first."""
    res = {}
    for f in BAKEOFF.glob("*.json"):
        try:
            r = json.loads(f.read_text())
            res[r["model"]] = r
        except Exception:
            continue

    def label(n):
        short = n.removesuffix(":latest").removesuffix("-q4_K_M")
        return f"{short} (recommended)" if n == DEFAULT_MODEL else short

    order = sorted(
        names,
        key=lambda n: (
            n != DEFAULT_MODEL,
            -(res.get(n) or res.get(n.removesuffix(":latest")) or {}).get("score", -1),
            n,
        ),
    )
    return [(label(n), n) for n in order]


def ollama_models() -> list[str]:
    """Locally available open-weight models (Ollama)."""
    import json as _json
    import os
    import urllib.request

    try:
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        with urllib.request.urlopen(f"{host}/api/tags", timeout=3) as r:
            names = [m["name"] for m in _json.load(r)["models"]]
        return sorted(names) or [DEFAULT_MODEL]
    except Exception:
        return [DEFAULT_MODEL]


def _k(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def _n(k: int, word: str) -> str:
    return f"{k} {word}{'' if k == 1 else 's'}"


def _dur(secs: float) -> str:
    secs = int(secs)
    return f"{secs // 60} min {secs % 60:02d} s" if secs >= 60 else f"{secs} s"


DESIGN_TOOLS = {
    "evaluate_design",
    "search_designs",
    "add_capacity_margin",
    "verify_design",
    "compare_designs",
}


def options_table(svc, chosen: Evaluation) -> str:
    """The cheapest feasible design of each alternative the search evaluated, against the "
    "chosen one."""
    c = chosen.spec
    cats = {
        "Shallower wells + heat pump": lambda x: x.well_depth_m < c.well_depth_m
        and x.heat_pump_mw > 0,
        "Deeper wells": lambda x: x.well_depth_m > c.well_depth_m,
        "Fewer doublets": lambda x: x.n_doublets < c.n_doublets,
        "More doublets": lambda x: x.n_doublets > c.n_doublets,
        "Absorption cooling": lambda x: x.absorption_chiller_mw > 0 and not c.absorption_chiller_mw,
        "Burn the associated gas": lambda x: x.gas_handling != c.gas_handling
        and x.gas_handling.startswith("sep"),
        "Re-inject the associated gas": lambda x: x.gas_handling != c.gas_handling
        and x.gas_handling.startswith("keep"),
    }
    pool = {
        e.spec.key(): e for k, e in list(svc.history.items()) if "[" not in k and e.checks["passed"]
    }
    rows = []
    for name, test in cats.items():
        alts = [e for e in pool.values() if test(e.spec)]
        if alts:
            rows.append((name, min(alts, key=lambda e: e.economics["lcoe_eur_per_mwh"])))
    if not rows:
        return ""
    l0, c0 = chosen.economics["lcoe_eur_per_mwh"], chosen.kpis["co2_t"]
    tr = "".join(
        f"<tr><td>{n}</td><td class='n'>{e.economics['lcoe_eur_per_mwh']:.1f}</td>"
        f"<td class='n'>{e.kpis['co2_t']:,.0f}</td><td "
        f"class='d'>{e.economics['lcoe_eur_per_mwh'] - l0:+.1f} €/MWh · "
        f"{e.kpis['co2_t'] - c0:+,.0f} t</td></tr>"
        for n, e in rows
    )
    return (
        "<details class='gd-details' open><summary>Options considered · cheapest feasible "
        "design of each</summary>"
        "<table class='gd-opts'><tr><th>Option</th><th class='n'>€/MWh</th><th class='n'>t "
        "CO₂/yr</th>"
        f"<th>vs selected</th></tr><tr class='sel'><td>Selected</td><td class='n'>{l0:.1f}</td>"
        f"<td class='n'>{c0:,.0f}</td><td class='d'>—</td></tr>{tr}</table></details>"
    )


def design_messages(ev: Evaluation, svc=None) -> list[dict]:
    """The design a turn produced, shown in the chat: figures, options weighed, verifier "
    "checklist, charts."""
    head = (
        f"<div class='gd-design'><span>Design</span> <kbd>{ev.spec.key()}</kbd>"
        f"<p>{html.escape(ev.spec.label())}</p></div>"
    )
    body = (
        head
        + kpi_cards(ev)
        + (options_table(svc, ev) if svc is not None else "")
        + checklist(ev, collapsible=True)
    )
    return [
        {"role": "assistant", "content": gr.HTML(body)},
        {"role": "assistant", "content": gr.Plot(charts.heat_supply(ev.result), show_label=False)},
        {
            "role": "assistant",
            "content": gr.Plot(charts.cooling_supply(ev.result), show_label=False),
        },
    ]


def agent_chat(message, history, runner, model, profile, mode, router_on=False, inputs=None):
    """Run one agent turn in a worker thread, streaming its steps into the chat."""
    import threading
    import time

    from gemini_agent.runner import AgentRunner

    if not message.strip():
        yield "", history, runner
        return
    from gemini_agent.router import from_env

    if runner is None:
        from gemini_agent.service import custom_service

        svc = (
            custom_service(inputs["values"], inputs["heat"], inputs["cool"])
            if inputs and inputs.get("custom")
            else None
        )
        runner = AgentRunner(
            model=model,
            profile=profile,
            mode=mode,
            service=svc,
            inputs_note=(inputs or {}).get("note"),
        )
    runner.router = from_env(model, router_on in (True, "on"))  # applies from the next turn on
    history = list(history) + [{"role": "user", "content": message}]
    start = len(runner.trace.events)
    box = {}

    def work():
        try:
            box["turn"] = runner.ask(message)
        except Exception as exc:  # surface errors in the chat
            box["error"] = repr(exc)

    th = threading.Thread(target=work, daemon=True)
    th.start()
    t0, pid = time.time(), f"steps-{len(history)}"

    def dropdown(done: bool) -> list[dict]:
        evs = runner.trace.events[start:]
        children = step_messages(evs, pid)
        if done and "turn" in box:
            children = annotate_turn(children, box["turn"], pid)
        secs = int(time.time() - t0)
        if done:
            llm = [e for e in evs if e["type"] == "llm"]
            title = (
                f"{_n(len(children), 'step')} · {_n(len(llm), 'model call')} · "
                f"{_k(sum(e['prompt_tokens'] + e['completion_tokens'] for e in llm))} tokens · "
                f"{_dur(secs)}"
            )
        else:  # running: the header shows time, the step in progress is the last line
            title = f"Working · {_dur(secs)}"
            children = children + live_step(evs, pid)
        head = {
            "role": "assistant",
            "content": "" if children else "(no steps yet)",
            "metadata": {"title": title, "id": pid, "status": "done" if done else "pending"},
        }
        return [head] + children

    while th.is_alive():
        yield "", history + dropdown(False), runner
        time.sleep(1.0)
    history = history + dropdown(True)
    if "error" in box:
        history.append({"role": "assistant", "content": f"Agent error: {box['error']}"})
    else:
        turn = box["turn"]
        history.append(
            {
                "role": "assistant",
                "content": (turn["answer"] or "(no answer)") + verifier_badge(turn),
            }
        )
        cur = runner.session.current_design
        if cur and DESIGN_TOOLS & set(turn["tool_calls"]):
            history += design_messages(runner.session.evaluations[cur], runner.session.svc)
    yield "", history, runner


def verifier_badge(turn: dict) -> str:
    """One line under each answer: what the deterministic verifier found."""
    p = turn["provenance"]
    problems = []
    if p["unsupported"]:
        problems.append(f"untraceable: {', '.join(f'{x:g}' for x in p['unsupported'])}")
    if p.get("unit_mismatches"):
        problems.append(
            "unit: "
            + "; ".join(f"{u['number']:g} as '{u['unit_written']}'" for u in p["unit_mismatches"])
        )
    if p.get("claim_issues"):
        problems.append("claim: " + "; ".join(c["detail"] for c in p["claim_issues"]))
    if problems:
        rev = " · revised once, still flagged" if turn.get("revised_from") else ""
        return "\n\n---\n*Verifier flagged — " + " · ".join(problems) + rev + "*"
    if not p["numbers_checked"]:
        return ""  # a question or a refusal: nothing to verify
    rev = " · revised once" if turn.get("revised_from") else ""
    return (
        f"\n\n---\n*✓ Verified · {_n(p['numbers_checked'], 'number')} traced to tool results{rev}*"
    )


def replay_chat(session_path, step_s=None, turn_pause_s=None):
    """Play a recorded session back into the chat: same dropdown, badge and design panel, faster.
    Pacing: GEODESIGN_REPLAY_STEP_S / GEODESIGN_REPLAY_TURN_PAUSE_S (the video renderer fits them
    to the narration)."""
    import os
    import time

    step_s = float(step_s or os.environ.get("GEODESIGN_REPLAY_STEP_S", 0.45))
    turn_pause_s = float(
        turn_pause_s or os.environ.get("GEODESIGN_REPLAY_TURN_PAUSE_S", step_s * 3)
    )

    from gemini_agent.ui import replay

    if not session_path:
        yield []
        return
    d = Path(session_path)
    meta = json.loads((d / "meta.json").read_text())
    turns, events = replay._jsonl(d / "transcript.jsonl"), replay._jsonl(d / "trace.jsonl")
    ledger = replay._jsonl(d / "ledger.jsonl")
    history = [
        {
            "role": "assistant",
            "content": f"*Replay of a recorded run · {meta.get('model', '').removesuffix('-q4_K_M')} · sped up*",  # noqa: E501
        }
    ]
    svc = replay.session_service(ledger)
    for n, (turn, evs) in enumerate(zip(turns, replay.split_turns(events, turns))):
        history = history + [{"role": "user", "content": turn["user"]}]
        pid = f"replay-{n}"
        for k in range(1, len(evs) + 1):
            if evs[k - 1]["type"] == "tool_start":
                continue
            kids = step_messages(evs[:k], pid) + live_step(evs[:k], pid)
            head = {
                "role": "assistant",
                "content": "",
                "metadata": {"title": "Working", "id": pid, "status": "pending"},
            }
            yield history + [head] + kids
            time.sleep(step_s)
        kids = annotate_turn(step_messages(evs, pid), turn, pid)
        llm = [e for e in evs if e["type"] == "llm"]
        head = {
            "role": "assistant",
            "content": "",
            "metadata": {
                "title": f"{_n(len(kids), 'step')} · {_n(len(llm), 'model call')} · "
                f"{_k(sum(e['prompt_tokens'] + e['completion_tokens'] for e in llm))} tokens · "
                f"{_dur(turn['seconds'])} recorded",
                "id": pid,
                "status": "done",
            },
        }
        history = (
            history
            + [head]
            + kids
            + [
                {
                    "role": "assistant",
                    "content": (turn["answer"] or "(no answer)") + verifier_badge(turn),
                }
            ]
        )
        spec = replay.spec_from_label(
            replay._label_of(turn.get("current_design") or "", ledger) or ""
        )
        if spec is not None and DESIGN_TOOLS & set(turn["tool_calls"]):
            history += design_messages(svc.evaluate(spec))
        yield history
        time.sleep(turn_pause_s)


def apply_inputs(heat_file, cool_file, *values):
    """Validate the inputs panel; a new conversation starts with them."""
    from gemini_agent.service import EDITABLE_INPUTS, custom_service, default_inputs

    defaults, names = default_inputs(), list(EDITABLE_INPUTS)
    vals = {k: float(v) for k, v in zip(names, values) if v is not None}
    changed = {k: v for k, v in vals.items() if abs(v - defaults[k]) > 1e-9}
    heat = heat_file if heat_file and Path(heat_file).name != DEFAULT_HEAT.name else None
    cool = cool_file if cool_file and Path(cool_file).name != DEFAULT_COOL.name else None
    try:
        custom_service(changed, heat, cool)
    except Exception as exc:
        raise gr.Error(str(exc))
    parts = [
        f"{EDITABLE_INPUTS[k][2].lower()} {v:g} {EDITABLE_INPUTS[k][3]}" for k, v in changed.items()
    ]
    parts += [f"heating file {Path(heat).name}"] if heat else []
    parts += [f"cooling file {Path(cool).name}"] if cool else []
    custom = bool(parts)
    note = ("custom: " + "; ".join(parts)) if custom else "default"
    msg = f"*Inputs for this chat · {note}*" if custom else "*Default inputs of the brief*"
    return (
        {"custom": custom, "values": changed, "heat": heat, "cool": cool, "note": note},
        [{"role": "assistant", "content": msg}],
        None,
    )


def reset_agent():
    """Start a fresh conversation."""
    return [], None


def build_app() -> gr.Blocks:
    """Assemble the cockpit: a left column (new chat, settings, inputs, replay) and the chat."""
    from gemini_agent.service import EDITABLE_INPUTS, default_inputs
    from gemini_agent.ui.replay import list_sessions

    with gr.Blocks(title="DeepLayers · GeoDesign Agent") as app:
        gr.HTML("<div class='gd-head'><h1><span>DeepLayers</span> · GeoDesign Agent</h1></div>")
        runner_state, inputs_state = gr.State(None), gr.State(None)
        with gr.Row(equal_height=False, elem_id="gd-main"):
            with gr.Column(scale=1, min_width=300, elem_id="gd-left"):
                reset_btn = gr.Button("New chat", variant="primary")
                with gr.Accordion("Settings", open=True, elem_classes="gd-acc"):
                    models = ollama_models()
                    default_model = DEFAULT_MODEL if DEFAULT_MODEL in models else models[0]
                    model_dd = gr.Dropdown(
                        model_choices(models), value=default_model, label="Model"
                    )
                    profile_rb = gr.Radio(
                        [("Lean", "lean"), ("Deep", "deep")], value="lean", label="Agent"
                    )
                    mode_rb = gr.Radio(
                        [("Interactive", "interactive"), ("Auto", "auto")],
                        value="interactive",
                        label="Mode",
                    )
                    router_cb = gr.Radio(
                        [("Off", "off"), ("On", "on")], value="off", label="Router"
                    )
                with gr.Accordion("Inputs", open=False, elem_classes="gd-acc"):
                    f_heat = gr.File(
                        str(DEFAULT_HEAT),
                        label="Heating demand (CSV)",
                        file_types=[".csv"],
                        elem_classes="gd-file",
                    )
                    f_cool = gr.File(
                        str(DEFAULT_COOL),
                        label="Cooling demand (CSV)",
                        file_types=[".csv"],
                        elem_classes="gd-file",
                    )
                    dflt = default_inputs()
                    num = [
                        gr.Number(dflt[k], label=f"{lab} ({unit})")
                        for k, (_, _, lab, unit) in EDITABLE_INPUTS.items()
                    ]
                    apply_btn = gr.Button("Apply inputs", variant="secondary")
                with gr.Accordion(
                    "Replay a recorded run", open=False, elem_classes="gd-acc", elem_id="gd-replay"
                ):
                    rp_dd = gr.Dropdown(list_sessions(), label="Recorded session")
                    rp_btn = gr.Button("Replay", variant="secondary")
            with gr.Column(scale=3, elem_id="gd-right"):
                chat_h = os.environ.get("GEODESIGN_CHAT_HEIGHT")  # the video capture pins it
                chat = gr.Chatbot(
                    height=int(chat_h) if chat_h else "100%",
                    label="Design agent",
                    show_label=False,
                    layout="panel",
                    elem_id="gd-chat",
                )
                with gr.Column(elem_id="gd-input"):
                    box = gr.Textbox(placeholder="Message the design agent", show_label=False)
                    gr.Examples(
                        [
                            "Design the system for the supplied demand. Balance cost and CO2.",
                            "Why not deeper wells instead of a heat pump?",
                            "What if a doublet trips on the coldest day?",
                            "Run each doublet at 500 m3/h.",
                            "What's the weather in Delft tomorrow?",
                        ],
                        inputs=box,
                        label=None,
                    )
        outs = [box, chat, runner_state]
        apply_btn.click(apply_inputs, [f_heat, f_cool, *num], [inputs_state, chat, runner_state])
        box.submit(
            agent_chat,
            [box, chat, runner_state, model_dd, profile_rb, mode_rb, router_cb, inputs_state],
            outs,
            show_progress="hidden",
        )
        rp_btn.click(replay_chat, rp_dd, [chat], show_progress="hidden")
        reset_btn.click(reset_agent, None, [chat, runner_state], show_progress="hidden")
    return app


TIPS = {  # label -> explanation shown by the ⓘ next to it
    "Model": "The open-weight LLM that plans, asks and calls tools, served locally by Ollama. "
    "Bigger models are more accurate but slower. Applies to a new chat.",
    "Agent": "Lean: one agent with all tools (fastest). Deep: an orchestrator delegates to "
    "specialists: "
    "requirements analyst, design engineer, risk & verification, model builder.",
    "Mode": "Interactive: the agent asks you about missing inputs, one question per turn. "
    "Auto: it never asks; it uses documented defaults and logs them as assumptions.",
    "Router": "Optional one-token triage before the agent: answers clearly off-topic questions "
    "in about a second. "
    "Anything it is unsure about goes to the full agent.",
    "Heating demand (CSV)": "Daily heating demand for one year: 365 rows of date and MW. "
    "Replace it to test another district.",
    "Cooling demand (CSV)": "Daily cooling demand for one year: 365 rows of date and MW, same "
    "dates as heating.",
    "Geothermal gradient (°C/km)": "Temperature rise per km of depth; with 12 °C at the "
    "surface it sets the reservoir "
    "temperature at any well depth.",
    "Permeability (mD)": "How easily brine flows through the reservoir rock; sets how much a "
    "well can produce "
    "for a given pressure drop.",
    "Max flow per doublet (m³/h)": "The brief's cap on pumped brine per doublet (50-300 m³/h).",
    "Max brine temperature drop (°C)": "How much the brine may be cooled before it is "
    "re-injected (brief: 40 °C). "
    "With the flow cap it limits the heat per doublet.",
    "Electricity price (€/MWh)": "Price of grid electricity for pumps, chillers and heat "
    "pumps; enters the cost (LCOE).",
    "Gas price (€/MWh)": "Price of grid gas for the backup boiler; enters the cost (LCOE).",
    "Grid CO₂ factor (kg/kWh)": "Emissions per kWh of grid electricity (organisers' reference "
    "value 0.3).",
}

HEAD = """<script>
// ⓘ after each settings/inputs label, explanation on hover (Gradio labels have no tooltip slot)
(() => {
  const tips = __TIPS__;
  const own = (el) => [...el.childNodes].filter(n => n.nodeType === 3).map(n =>
  n.textContent).join('').trim();
  const mark = () => document.querySelectorAll('#gd-left span, #gd-left label, #gd-left div')
    .forEach(el => {
      const t = tips[own(el)];  // the label's own text, even next to an icon (file fields)
      if (!t || el.dataset.tip) return;
      el.dataset.tip = '1';
      const i = document.createElement('span');
      i.className = 'gd-info'; i.textContent = 'i'; i.setAttribute('data-tip', t); i.tabIndex = 0;
      el.appendChild(i);
    });
  new MutationObserver(mark).observe(document.documentElement, {childList: true, subtree: true});
  // the tooltip is one fixed layer on <body>, so panel edges cannot clip it
  let tip = null;
  const show = (e) => {
    const i = e.target.closest && e.target.closest('.gd-info'); if (!i) return;
    tip = tip || Object.assign(document.createElement('div'), {className: 'gd-tip'});
    tip.textContent = i.getAttribute('data-tip'); document.body.appendChild(tip);
    const r = i.getBoundingClientRect(), w = Math.min(300, window.innerWidth - 24);
    tip.style.width = w + 'px';
    tip.style.left = Math.max(12, Math.min(r.right + 8, window.innerWidth - w - 12)) + 'px';
    tip.style.top = Math.min(r.top - 4, window.innerHeight - tip.offsetHeight - 12) + 'px';
  };
  const hide = (e) => { if (tip && e.target.closest && e.target.closest('.gd-info'))
  tip.remove(); };
  document.addEventListener('mouseover', show); document.addEventListener('focusin', show);
  document.addEventListener('mouseout', hide); document.addEventListener('focusout', hide);
})();
</script>""".replace("__TIPS__", json.dumps(TIPS))


def serve(port: int = 7860):
    """Launch the cockpit on 127.0.0.1:port (SSH forwards it)."""
    build_app().queue().launch(
        server_name="127.0.0.1",
        server_port=port,
        css=CSS,
        theme=cockpit_theme(),
        head=HEAD,
        show_error=True,
    )


def main():
    """Launch locally (VS Code / SSH forwards the port)."""
    serve(7860)


if __name__ == "__main__":
    main()
