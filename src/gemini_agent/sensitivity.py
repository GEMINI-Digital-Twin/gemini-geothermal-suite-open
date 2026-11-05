"""Techno-economic sensitivity (tornado) and decision break-even points.

Every point is a full re-simulation (prices change the cost-optimal dispatch),
so tipping points are physically consistent, not just re-costed.

- ``tornado``: LCOE and CO2 response of a design to low/high values of the
  main uncertain inputs.
- ``break_even``: the value of one input at which two competing designs have
  equal LCOE ("when would this decision flip?").
"""

from __future__ import annotations

import copy

from scipy.optimize import brentq

from gemini_agent.physics.design import DesignSpec
from gemini_agent.physics.site import Brief, Demand
from gemini_agent.service import DesignService

# name: (kind, key, low, high, label)
PARAMS = {
    "well_cost_eur_per_m": ("econ", "well_per_m_eur", 1600.0, 2600.0, "Drilling cost (€/m)"),
    "electricity_eur_per_mwh": (
        "econ",
        "electricity_eur_per_mwh",
        100.0,
        220.0,
        "Electricity price (€/MWh)",
    ),
    "gas_eur_per_mwh": ("econ", "natural_gas_eur_per_mwh", 30.0, 70.0, "Gas price (€/MWh)"),
    "co2_eur_per_t": ("econ", "co2_eur_per_t", 60.0, 150.0, "CO₂ price (€/t)"),
    "discount_rate": ("econ", "discount_rate", 0.04, 0.08, "Discount rate (-)"),
    "heat_pump_capex_eur_per_mw": (
        "econ",
        "heat_pump_eur_per_mw_th",
        450e3,
        800e3,
        "Heat-pump CAPEX (€/MW)",
    ),
    "gradient_c_per_km": (
        "brief",
        ("reservoir", "geothermal_gradient_c_per_km"),
        27.0,
        33.0,
        "Geothermal gradient (°C/km)",
    ),
    "permeability_md": (
        "brief",
        ("reservoir", "permeability_md"),
        100.0,
        400.0,
        "Permeability (mD)",
    ),
    "demand_scale": ("demand", None, 0.9, 1.1, "Demand level (×)"),
}


def _service(base: DesignService, name: str, value: float) -> DesignService:
    kind, key, *_ = PARAMS[name]
    brief, demand = base.brief, base.demand
    if kind == "brief":
        raw = copy.deepcopy(base.brief.raw)
        raw[key[0]][key[1]] = value
        brief = Brief(raw=raw)
    if kind == "demand":
        demand = Demand(
            base.demand.dates,
            [h * value for h in base.demand.heating_mw],
            [c * value for c in base.demand.cooling_mw],
            base.demand.heating_supply_c,
            base.demand.cooling_supply_c,
        )
    svc = DesignService(brief, demand, weather=base.weather)
    if kind == "econ":
        svc.econ["values"][key] = value
    return svc


def evaluate_with(base: DesignService, spec: DesignSpec, name: str, value: float) -> dict:
    """LCOE / CO2 / feasibility of ``spec`` with one input changed."""
    ev = _service(base, name, value).evaluate(spec)
    return {
        "lcoe": ev.economics["lcoe_eur_per_mwh"],
        "co2_t": ev.kpis["co2_t"],
        "feasible": ev.checks["passed"],
    }


def tornado(base: DesignService, spec: DesignSpec, names: list[str] | None = None) -> dict:
    """Low/high response of LCOE and CO2 for each input; sorted by LCOE swing."""
    ref = base.evaluate(spec)
    rows = []
    for n in names or list(PARAMS):
        _, _, lo, hi, label = PARAMS[n]
        a, b = evaluate_with(base, spec, n, lo), evaluate_with(base, spec, n, hi)
        rows.append(
            {
                "input": n,
                "label": label,
                "low": lo,
                "high": hi,
                "lcoe_low": a["lcoe"],
                "lcoe_high": b["lcoe"],
                "co2_low": a["co2_t"],
                "co2_high": b["co2_t"],
                "feasible_low": a["feasible"],
                "feasible_high": b["feasible"],
                "lcoe_swing": abs(b["lcoe"] - a["lcoe"]),
            }
        )
    rows.sort(key=lambda r: -r["lcoe_swing"])
    return {
        "design_id": spec.key(),
        "base_lcoe": ref.economics["lcoe_eur_per_mwh"],
        "base_co2_t": ref.kpis["co2_t"],
        "rows": rows,
    }


def break_even(
    base: DesignService,
    spec_a: DesignSpec,
    spec_b: DesignSpec,
    name: str,
    lo: float | None = None,
    hi: float | None = None,
    metric: str = "lcoe",
) -> dict:
    """Value of input ``name`` at which designs A and B have equal ``metric``."""
    _, _, plo, phi, label = PARAMS[name]
    lo, hi = lo if lo is not None else plo, hi if hi is not None else phi

    def diff(v):
        return (
            evaluate_with(base, spec_a, name, v)[metric]
            - evaluate_with(base, spec_b, name, v)[metric]
        )

    d_lo, d_hi = diff(lo), diff(hi)
    out = {
        "input": name,
        "label": label,
        "range": [lo, hi],
        "a_minus_b_at_low": round(d_lo, 3),
        "a_minus_b_at_high": round(d_hi, 3),
    }
    if d_lo * d_hi > 0:
        out["break_even"] = None
        out["note"] = (
            "A is better over the whole range" if d_lo < 0 else "B is better over the whole range"
        )
    else:
        out["break_even"] = round(brentq(diff, lo, hi, xtol=(hi - lo) * 1e-3), 4)
    return out
