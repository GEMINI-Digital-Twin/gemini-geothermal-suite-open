"""Plotly figures for the cockpit and the report.

Colour follows the entity in every chart (fixed categorical order of the
validated reference palette); limits use the reserved status colour plus a text
label; one y-axis per chart (two measures -> two charts).
"""

from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Validated categorical palette (light mode), fixed order -> fixed entity.
C = {  # geothermal heat leads in the ember accent; every other entity is a quiet, distinct tone
    "hex": "#c2410c",  # direct geothermal heat (HEX) - the accent
    "hp": "#e7a173",  # heat pump - light ember (geothermal heat, upgraded)
    "boiler": "#57534e",  # boiler - stone
    "abs": "#d4a24c",  # absorption chiller (geothermal-driven) - sand
    "ech": "#64748b",  # electric chiller - slate
    "pumps": "#0f766e",  # pumps - deep teal
    "gas": "#a8a29e",  # gas - light stone
}
INK, INK2, GRID, SURFACE = "#171717", "#525252", "#ececec", "#ffffff"
CRITICAL, GOOD = "#dc2626", "#16a34a"
FONT = "IBM Plex Sans, Segoe UI, Helvetica, Arial, sans-serif"


def _layout(fig, title, ytitle, height=320):
    fig.update_layout(
        title={"text": title, "x": 0.01, "font": {"size": 15, "color": INK}},
        height=height,
        margin={"l": 60, "r": 20, "t": 48, "b": 40},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"family": FONT, "color": INK2, "size": 12},
        hovermode="x unified",
        legend={
            "orientation": "h",
            "y": 1.02,
            "x": 1,
            "xanchor": "right",
            "yanchor": "bottom",
            "itemclick": False,  # a legend click would hide the series ("the plot disappeared")
            "itemdoubleclick": False,
        },
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, ticks="outside", tickcolor=GRID)
    fig.update_yaxes(title=ytitle, gridcolor=GRID, zeroline=False, linecolor=GRID)
    return fig


def _area(fig, x, y, name, color, row=None, col=None):
    if max(y, default=0.0) < 1e-6:  # a technology the design does not use: no empty legend entry
        return
    kw = {"row": row, "col": col} if row else {}
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            name=name,
            stackgroup="one",
            mode="lines",
            line={"width": 0.5, "color": "#ffffff"},
            fillcolor=color,
            hovertemplate="%{y:.2f} MW",
        ),
        **kw,
    )


def heat_supply(res):
    """Daily heat supply by source (stacked) vs demand."""
    x = res.dates
    fig = go.Figure()
    _area(fig, x, res.series("q_hex"), "Geothermal direct (HEX)", C["hex"])
    _area(fig, x, res.series("q_hp"), "Heat pump", C["hp"])
    _area(fig, x, res.series("q_boiler"), "Boiler", C["boiler"])
    fig.add_trace(
        go.Scatter(
            x=x,
            y=res.heat_mw,
            name="Heating demand",
            mode="lines",
            line={"color": INK, "width": 1.5, "dash": "dot"},
            hovertemplate="%{y:.2f} MW",
        )
    )
    unmet = res.series("unmet_heat")
    if max(unmet) > 1e-3:
        fig.add_trace(go.Bar(x=x, y=unmet, name="Unmet heat", marker_color=CRITICAL))
    return _layout(fig, "Heating supply by source (daily average)", "MW")


def cooling_supply(res):
    """Daily cooling supply by technology vs demand."""
    x = res.dates
    fig = go.Figure()
    _area(fig, x, res.series("q_abs_cool"), "Absorption chiller (geothermal)", C["abs"])
    _area(fig, x, res.series("q_ech_cool"), "Electric chiller", C["ech"])
    fig.add_trace(
        go.Scatter(
            x=x,
            y=res.cool_mw,
            name="Cooling demand",
            mode="lines",
            line={"color": INK, "width": 1.5, "dash": "dot"},
            hovertemplate="%{y:.2f} MW",
        )
    )
    unmet = res.series("unmet_cool")
    if max(unmet) > 1e-3:
        fig.add_trace(go.Bar(x=x, y=unmet, name="Unmet cooling", marker_color=CRITICAL))
    return _layout(fig, "Cooling supply by technology (daily average)", "MW")


def brine_operation(res):
    """Two stacked panels: brine temperatures (with 40 K rule) and flow per doublet."""
    x = res.dates
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        subplot_titles=("Brine temperatures (°C)", "Flow per active doublet (m³/h)"),
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=res.series("wellhead_t_c"),
            name="Producer wellhead",
            line={"color": C["hp"], "width": 2},
            hovertemplate="%{y:.1f} °C",
        ),
        1,
        1,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=res.series("injection_t_c"),
            name="Injection",
            line={"color": C["hex"], "width": 2},
            hovertemplate="%{y:.1f} °C",
        ),
        1,
        1,
    )
    floor = [t - 40 if t == t else None for t in res.series("wellhead_t_c")]
    fig.add_trace(
        go.Scatter(
            x=x,
            y=floor,
            name="40 K limit (min injection)",
            line={"color": CRITICAL, "width": 1.5, "dash": "dash"},
            hovertemplate="%{y:.1f} °C",
        ),
        1,
        1,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=res.series("flow_per_doublet_m3h"),
            name="Flow per doublet",
            line={"color": C["pumps"], "width": 2, "shape": "hv"},
            hovertemplate="%{y:.0f} m³/h",
        ),
        2,
        1,
    )
    for lim, lab in ((50, "min 50"), (300, "max 300")):
        fig.add_hline(
            y=lim,
            line={"color": CRITICAL, "width": 1, "dash": "dot"},
            row=2,
            col=1,
            annotation_text=lab,
            annotation_font_color=INK2,
        )
    _layout(fig, "Geothermal brine operation", None, height=500)
    fig.update_yaxes(title=None)
    fig.update_layout(
        legend={
            "orientation": "h",
            "y": -0.12,
            "x": 0,
            "xanchor": "left",
            "yanchor": "top",
            "itemclick": False,
            "itemdoubleclick": False,
        },
        margin={"b": 70},
    )
    return fig


def availability(res):
    """Doublet availability: planned maintenance windows and producing days."""
    fig = go.Figure()
    n = res.spec.n_doublets
    for j in range(n):
        a, b = res.windows[j]
        fig.add_trace(
            go.Bar(
                y=[f"Doublet {j + 1}"],
                x=[b - a],
                base=[a],
                orientation="h",
                marker_color=CRITICAL,
                name="Planned maintenance" if j == 0 else None,
                showlegend=j == 0,
                hovertemplate=f"Maintenance day {a}–{b - 1}<extra></extra>",
            )
        )
    on = [d.n_on for d in res.days]
    for j in range(n):
        days = []
        for i, d in enumerate(res.days):
            avail = [k for k in range(n) if not (res.windows[k][0] <= i < res.windows[k][1])]
            if j in avail[: d.n_on]:
                days.append(i)
        fig.add_trace(
            go.Scatter(
                x=days,
                y=[f"Doublet {j + 1}"] * len(days),
                mode="markers",
                marker={"symbol": "line-ns", "size": 10, "line": {"width": 1, "color": GOOD}},
                name="Producing" if j == 0 else None,
                showlegend=j == 0,
                hovertemplate="producing, day %{x}<extra></extra>",
            )
        )
    _ = on
    fig.update_layout(barmode="overlay")
    _layout(fig, "Doublet availability (330 operating days per source)", None, height=120 + 50 * n)
    fig.update_xaxes(title="Day of year", range=[0, 365])
    fig.update_layout(hovermode="closest")
    return fig


def sankey(res, econ=None):
    """Annual energy flows (GWh): sources -> conversion -> services."""
    k = res.kpis()
    g = lambda name: sum(res.series(name)) * 24 / 1000  # noqa: E731
    hp_el, pump_el = g("hp_el"), g("el_pumps")
    hp_src = k["heat_hp_gwh"] - hp_el
    chill_el = g("el_chillers")
    labels = [
        "Geothermal brine",
        "Electricity",
        "Gas",
        "Heat exchanger",
        "Heat pump",
        "Absorption chiller",
        "Electric chiller",
        "Boiler",
        "Heating 100 °C",
        "Cooling 20 °C",
        "Pumps",
        "Heat rejection",
    ]
    idx = {l: i for i, l in enumerate(labels)}
    links = [
        ("Geothermal brine", "Heat exchanger", k["heat_hex_gwh"]),
        ("Geothermal brine", "Heat pump", hp_src),
        ("Geothermal brine", "Absorption chiller", g("q_abs_gen")),
        ("Electricity", "Heat pump", hp_el),
        ("Electricity", "Pumps", pump_el),
        ("Electricity", "Electric chiller", chill_el),
        ("Gas", "Boiler", g("fuel_assoc_gas") + g("fuel_grid_gas")),
        ("Electricity", "Boiler", g("el_boiler")),
        ("Heat exchanger", "Heating 100 °C", k["heat_hex_gwh"]),
        ("Heat pump", "Heating 100 °C", k["heat_hp_gwh"]),
        ("Boiler", "Heating 100 °C", k["heat_boiler_gwh"]),
        ("Absorption chiller", "Cooling 20 °C", k["cool_absorption_gwh"]),
        ("Electric chiller", "Cooling 20 °C", k["cool_electric_gwh"]),
        ("Absorption chiller", "Heat rejection", g("q_abs_gen")),
    ]
    links = [(a, b, v) for a, b, v in links if v > 0.01]
    node_color = [
        C["hex"],
        C["pumps"],
        C["gas"],
        C["hex"],
        C["hp"],
        C["abs"],
        C["ech"],
        C["boiler"],
        INK2,
        INK2,
        C["pumps"],
        GRID,
    ]
    fig = go.Figure(
        go.Sankey(
            node={
                "label": labels,
                "color": node_color,
                "pad": 18,
                "thickness": 14,
                "line": {"color": SURFACE, "width": 2},
            },
            link={
                "source": [idx[a] for a, _, _ in links],
                "target": [idx[b] for _, b, _ in links],
                "value": [round(v, 3) for _, _, v in links],
                "color": "rgba(82,81,78,0.18)",
                "hovertemplate": "%{source.label} → %{target.label}: %{value:.2f} "
                "GWh<extra></extra>",
            },
        )
    )
    return _layout(fig, "Annual energy flows (GWh)", None, height=380)


def pareto(rows, chosen_key=None):
    """LCOE vs CO2 of evaluated designs; feasible vs infeasible, chosen highlighted."""
    fig = go.Figure()
    groups = (("Feasible", True, C["hex"]), ("Violates constraints", False, CRITICAL))
    for name, ok, color in groups:
        pts = [r for r in rows if r["passed"] == ok]
        if not pts:
            continue
        fig.add_trace(
            go.Scatter(
                x=[r["co2_t"] for r in pts],
                y=[r["lcoe"] for r in pts],
                mode="markers",
                name=name,
                marker={
                    "size": 10,
                    "color": color,
                    "line": {"color": SURFACE, "width": 2},
                    "symbol": "circle" if ok else "x",
                },
                text=[r["label"] for r in pts],
                hovertemplate="%{text}<br>CO₂ %{x:,.0f} t/yr · LCOE %{y:.1f} €/MWh<extra></extra>",
            )
        )
    if chosen_key:
        ch = [r for r in rows if r["key"] == chosen_key]
        if ch:
            fig.add_trace(
                go.Scatter(
                    x=[ch[0]["co2_t"]],
                    y=[ch[0]["lcoe"]],
                    mode="markers+text",
                    name="Selected",
                    marker={
                        "size": 16,
                        "color": "rgba(0,0,0,0)",
                        "line": {"color": INK, "width": 2},
                    },
                    text=["selected"],
                    textposition="top center",
                    textfont={"color": INK},
                    hoverinfo="skip",
                )
            )
    _layout(fig, "Design trade-off: cost vs emissions", "LCOE (€/MWh)", height=380)
    fig.update_xaxes(title="CO₂ emissions (t/yr)")
    fig.update_layout(hovermode="closest")
    return fig


def well_map(dmap):
    """GEMINI doublet performance vs flow: pumping power (one chart, one axis)."""
    f = dmap["flows_m3h"]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=f,
            y=dmap["producer_pump_kw"],
            name="Producer ESP",
            line={"color": C["hp"], "width": 2},
            mode="lines+markers",
            marker={"size": 8},
            hovertemplate="%{y:.0f} kW",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=f,
            y=dmap["injector_pump_kw"],
            name="Injection pump",
            line={"color": C["hex"], "width": 2},
            mode="lines+markers",
            marker={"size": 8},
            hovertemplate="%{y:.0f} kW",
        )
    )
    _layout(fig, "Doublet pumping power vs flow (GEMINI DPDT + IPR, η = 70 %)", "kW", height=300)
    fig.update_xaxes(title="Flow per doublet (m³/h)")
    return fig


def tornado(res):
    """LCOE swing per uncertain input (low/high bars around the base case)."""
    rows = list(reversed(res["rows"]))
    base = res["base_lcoe"]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=[r["label"] for r in rows],
            x=[r["lcoe_low"] - base for r in rows],
            base=base,
            orientation="h",
            name="input at low value",
            marker_color=C["hex"],
            customdata=[[r["low"], r["lcoe_low"]] for r in rows],
            hovertemplate="%{y}: %{customdata[0]:,} → %{customdata[1]:.1f} €/MWh<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            y=[r["label"] for r in rows],
            x=[r["lcoe_high"] - base for r in rows],
            base=base,
            orientation="h",
            name="input at high value",
            marker_color=C["hp"],
            customdata=[[r["high"], r["lcoe_high"]] for r in rows],
            hovertemplate="%{y}: %{customdata[0]:,} → %{customdata[1]:.1f} €/MWh<extra></extra>",
        )
    )
    fig.add_vline(
        x=base,
        line={"color": INK, "width": 1.5},
        annotation_text=f"base {base:.1f} €/MWh",
        annotation_font_color=INK2,
    )
    fig.update_layout(barmode="overlay", bargap=0.35)
    _layout(fig, "Sensitivity of LCOE (selected design)", None, height=360)
    fig.update_xaxes(title="LCOE (€/MWh)")
    fig.update_layout(hovermode="closest")
    return fig
