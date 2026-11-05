"""Deterministic constraint verifier.

Checks a simulated year against the brief's hard constraints and engineering
sanity limits. Returns machine-readable results; the agent may only report a
design whose checks all pass (the verifier has the final word, not the LLM).
"""

from __future__ import annotations

from gemini_agent.physics.plant import AnnualResult
from gemini_agent.physics.site import Brief

TOL_MW = 1e-3


def _plain(v):
    """Convert numpy scalars (np.float64 etc.) to plain Python for display/JSON."""
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        return v.item()
    return v


def check_design(res: AnnualResult, brief: Brief, lifetime_years: float = 30.0) -> dict:
    """Run all checks; returns {"passed": bool, "checks": [...], "violations": [...]}."""
    c = brief.constraints
    checks = []

    def add(name, ok, value, limit, detail=""):
        checks.append(
            {"check": name, "passed": bool(ok), "value": value, "limit": limit, "detail": detail}
        )

    flows = [d.flow_per_doublet_m3h for d in res.days if d.n_on > 0]
    add(
        "flow_within_50_300_m3h_per_active_doublet",
        all(
            c["min_flow_m3h_per_doublet"] - 1e-6 <= f <= c["max_flow_m3h_per_doublet"] + 1e-6
            for f in flows
        ),
        [round(min(flows), 1), round(max(flows), 1)] if flows else None,
        [c["min_flow_m3h_per_doublet"], c["max_flow_m3h_per_doublet"]],
    )
    max_dt = max((d.brine_dt_k for d in res.days), default=0.0)
    add(
        "brine_cooling_le_40K",
        max_dt <= c["max_brine_cooling_k"] + 1e-3,
        round(max_dt, 3),
        c["max_brine_cooling_k"],
    )

    unmet_days = [res.dates[i] for i, d in enumerate(res.days) if d.unmet_heat > TOL_MW]
    add(
        "heating_demand_met_all_365_days",
        not unmet_days,
        len(unmet_days),
        0,
        ", ".join(unmet_days[:5]),
    )
    unmet_c = [res.dates[i] for i, d in enumerate(res.days) if d.unmet_cool > TOL_MW]
    add("cooling_demand_met_all_365_days", not unmet_c, len(unmet_c), 0, ", ".join(unmet_c[:5]))

    op_days = res.operating_days()
    add(
        "geothermal_operating_days_le_330_per_doublet",
        all(n <= c["geothermal_operating_days"] for n in op_days),
        op_days,
        c["geothermal_operating_days"],
    )
    add(
        "production_equals_injection_volume",
        True,
        "by construction",
        "equal",
        "each doublet re-injects its own produced volume into the same reservoir",
    )
    add(
        "n_doublets_1_to_3",
        c["n_doublets_min"] <= res.spec.n_doublets <= c["n_doublets_max"],
        res.spec.n_doublets,
        [c["n_doublets_min"], c["n_doublets_max"]],
    )

    bt = res.doublet_map.get("breakthrough_years_at_max_flow")
    add(
        "thermal_breakthrough_after_lifetime",
        bt is None or bt >= lifetime_years,
        bt,
        lifetime_years,
        "Gringarten-Sauty doublet breakthrough at maximum flow and design spacing",
    )

    hp_days = [d for d in res.days if d.q_hp > 0]
    add(
        "heat_pump_cop_physical",
        all(1.0 < d.hp_cop < 20.0 for d in hp_days),
        (
            [round(min(d.hp_cop for d in hp_days), 2), round(max(d.hp_cop for d in hp_days), 2)]
            if hp_days
            else None
        ),
        "(1, 20)",
    )

    checks = [_plain(x) for x in checks]
    violations = [x for x in checks if not x["passed"]]
    return {
        "passed": not violations,
        "n_checks": len(checks),
        "checks": checks,
        "violations": violations,
    }
