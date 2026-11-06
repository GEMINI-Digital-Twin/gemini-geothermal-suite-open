"""GEMINI hackathon task 2: challenge constraint checker.

``check_constraints(case, limits)`` returns an explicit PASS / FAIL / MISSING
record, with the value and limit, for every hard constraint in
inputs/requirements.pdf p.2. A case is feasible only if every record PASSes;
MISSING means the quantity has not been modeled yet (e.g. cooling supply
before task 5) and is never treated as compliant.

Case schema (plain dict, so the checker is independent of the simulator)::

    {
      "n_doublets": int,
      "doublets": [
        {"name": str, "active": bool,
         "production_m3h": float, "injection_m3h": float,
         "T_production_C": float, "T_injection_C": float,     # producer / injector wellhead
         "pumps": [{"name": str, "flow_m3s": float, "dp_pa": float, "power_w": float}]},
        ...
      ],
      "heating_supply_C": float | None,
      "cooling_supply_C": float | None,
    }
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHALLENGE_PATH = ROOT / "inputs" / "challenge_inputs.json"

PASS, FAIL, MISSING = "PASS", "FAIL", "MISSING"

# ASSUMED checker tolerances (see CLAUDE.md); the limits themselves are OFFICIAL.
SUPPLY_TEMPERATURE_TOLERANCE_K = 0.5
VOLUME_BALANCE_REL_TOLERANCE = 1e-6
PUMP_EFFICIENCY_ABS_TOLERANCE = 1e-3
FLOW_TOLERANCE_M3H = 0.01  # nodal-solve round-off on a dispatched flow
BRINE_DT_TOLERANCE_K = 1e-3  # root-finder round-off when the brine is cooled exactly to the cap


def load_limits(path: Path = CHALLENGE_PATH) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)["constraints"]


def check_constraints(case: dict, limits: dict) -> dict:
    """Check one design case against every challenge constraint."""
    results = []

    def add(check, scope, status, value, limit, reason):
        results.append(
            {"check": check, "scope": scope, "status": status, "value": value, "limit": limit, "reason": reason}
        )

    # Doublet count (integer design variable, 1-3).
    n = case["n_doublets"]
    n_min, n_max = limits["minimum_doublets"], limits["maximum_doublets"]
    if not isinstance(n, int) or isinstance(n, bool):
        add("doublet_count", "plant", FAIL, n, f"integer {n_min}-{n_max}", f"doublet count {n!r} is not an integer")
    elif not n_min <= n <= n_max:
        add("doublet_count", "plant", FAIL, n, f"{n_min}-{n_max}", f"{n} doublets is outside the allowed {n_min}-{n_max}")
    elif len(case["doublets"]) != n:
        add("doublet_count", "plant", FAIL, len(case["doublets"]), n, f"{len(case['doublets'])} doublet records for n_doublets={n}")
    else:
        add("doublet_count", "plant", PASS, n, f"{n_min}-{n_max}", f"{n} doublet(s) within {n_min}-{n_max}")

    q_min, q_max = limits["flow_min_when_on_m3_per_h_per_doublet"], limits["flow_max_m3_per_h_per_doublet"]
    dt_max = limits["maximum_brine_delta_T_C"]
    eta = limits["pump_efficiency"]

    for d in case["doublets"]:
        scope = d["name"]
        q_prod, q_inj = d["production_m3h"], d["injection_m3h"]

        # Flow 50-300 m3/h while active; zero flow while off.
        if d.get("active", True):
            if q_min - FLOW_TOLERANCE_M3H <= q_prod <= q_max + FLOW_TOLERANCE_M3H:
                add("flow_range", scope, PASS, q_prod, f"{q_min}-{q_max} m3/h", f"{q_prod:.2f} m3/h within {q_min}-{q_max} m3/h")
            elif q_prod > q_max:
                add("flow_range", scope, FAIL, q_prod, f"<= {q_max} m3/h", f"{q_prod:.2f} m3/h exceeds the {q_max} m3/h hard cap")
            else:
                add("flow_range", scope, FAIL, q_prod, f">= {q_min} m3/h", f"{q_prod:.2f} m3/h is below the {q_min} m3/h minimum stable flow while active")
        elif q_prod != 0 or q_inj != 0:
            add("flow_range", scope, FAIL, q_prod, "0 m3/h when off", f"inactive doublet still flows {q_prod:.2f} m3/h")
        else:
            add("flow_range", scope, PASS, 0.0, "0 m3/h when off", "inactive, no flow")

        # Equal produced / injected liquid volume.
        imbalance = q_prod - q_inj
        if abs(imbalance) <= VOLUME_BALANCE_REL_TOLERANCE * max(abs(q_prod), 1.0):
            add("volume_balance", scope, PASS, imbalance, "0 m3/h", f"production {q_prod:.2f} = injection {q_inj:.2f} m3/h")
        else:
            add("volume_balance", scope, FAIL, imbalance, "0 m3/h", f"production {q_prod:.2f} != injection {q_inj:.2f} m3/h (imbalance {imbalance:+.2f} m3/h)")

        # Brine cooling producer -> injector, 0-40 K.
        if not d.get("active", True):
            add("brine_dT", scope, PASS, None, f"<= {dt_max} K", "inactive, not applicable")
        else:
            dt = d["T_production_C"] - d["T_injection_C"]
            if 0 <= dt <= dt_max + BRINE_DT_TOLERANCE_K:
                add("brine_dT", scope, PASS, dt, f"0-{dt_max} K", f"{dt:.2f} K within 0-{dt_max} K")
            elif dt > dt_max:
                add("brine_dT", scope, FAIL, dt, f"<= {dt_max} K", f"{dt:.2f} K brine cooling exceeds the {dt_max} K cap")
            else:
                add("brine_dT", scope, FAIL, dt, ">= 0 K", f"injection is {-dt:.2f} K hotter than production")

        # Pump power must correspond to the 70% hydraulic efficiency: P = Q*dp/eta.
        for pump in d["pumps"]:
            pscope = f"{scope}.{pump['name']}"
            hydraulic_w = pump["flow_m3s"] * pump["dp_pa"]
            expected_w = hydraulic_w / eta
            if pump["power_w"] < 0 or pump["dp_pa"] < 0:
                add("pump_efficiency", pscope, FAIL, pump["power_w"], f"Q*dp/{eta}", "negative pump power or pressure rise")
            elif hydraulic_w == 0 and pump["power_w"] == 0:
                add("pump_efficiency", pscope, PASS, 0.0, f"Q*dp/{eta}", "no pressure rise needed, 0 W")
            elif pump["power_w"] == 0:
                add("pump_efficiency", pscope, FAIL, 0.0, f"{expected_w:.0f} W", f"0 W reported for {hydraulic_w:.0f} W hydraulic power")
            else:
                implied = hydraulic_w / pump["power_w"]
                if abs(implied - eta) <= PUMP_EFFICIENCY_ABS_TOLERANCE:
                    add("pump_efficiency", pscope, PASS, implied, eta, f"{pump['power_w'] / 1e3:.1f} kW = Q*dp/{eta} (implied eta {implied:.3f})")
                else:
                    add("pump_efficiency", pscope, FAIL, implied, eta, f"{pump['power_w'] / 1e3:.1f} kW implies eta {implied:.3f}, required {eta} -> expected {expected_w / 1e3:.1f} kW")

    # Supply temperatures to the demand.
    for check, key, target in (
        ("heating_supply_T", "heating_supply_C", limits["heating_supply_temperature_C"]),
        ("cooling_supply_T", "cooling_supply_C", limits["cooling_supply_temperature_C"]),
    ):
        value = case.get(key)
        limit = f"{target} +/- {SUPPLY_TEMPERATURE_TOLERANCE_K} C"
        if value is None:
            add(check, "plant", MISSING, None, limit, "not modeled yet; cannot be shown compliant")
        elif abs(value - target) <= SUPPLY_TEMPERATURE_TOLERANCE_K:
            add(check, "plant", PASS, value, limit, f"{value:.2f} C meets {target} C")
        else:
            add(check, "plant", FAIL, value, limit, f"{value:.2f} C is {value - target:+.2f} K from the fixed {target} C supply")

    return {"feasible": all(r["status"] == PASS for r in results), "results": results}


def format_report(report: dict) -> str:
    lines = [f"{'STATUS':8} {'CHECK':18} {'SCOPE':26} REASON"]
    for r in report["results"]:
        lines.append(f"{r['status']:8} {r['check']:18} {r['scope']:26} {r['reason']}")
    failed = [r for r in report["results"] if r["status"] != PASS]
    verdict = "FEASIBLE" if report["feasible"] else f"REJECTED ({len(failed)} check(s) not passed)"
    lines.append(f"VERDICT: {verdict}")
    return "\n".join(lines)
