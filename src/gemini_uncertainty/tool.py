"""Agent tool wrapper: one JSON-in / JSON-out call for the uncertainty study.

``TOOL_SPEC`` follows the common function-calling schema (name,
description, JSON-schema ``parameters``) so it can be registered with an
Ollama / OpenAI-compatible tool-calling loop as is. ``run_tool`` validates
the arguments, runs the study and returns only small, JSON-safe numbers
(the agent never sees a DataFrame), plus the files it wrote.
"""

import json
from pathlib import Path

import numpy as np

from gemini_design.challenge import load_demand
from gemini_uncertainty.parameters import PARAMETERS, describe_parameters, get_parameters
from gemini_uncertainty.study import (
    base_case,
    compare,
    design_from_name,
    monte_carlo,
    summarise,
    tornado,
)

MAX_SAMPLES = 1000
DEFAULT_INPUTS = Path(__file__).resolve().parents[2] / "simulator_examples" / "hackathon_inputs"

TOOL_SPEC = {
    "name": "assess_design_uncertainty",
    "description": (
        "Monte Carlo + tornado uncertainty and techno-economic assessment of one or more "
        "heating/cooling plant designs. Each sample re-runs the physics-checked 365-day "
        "dispatch with sampled permeability, temperature gradient, reservoir thickness, skin, "
        "heating/cooling demand scale, electricity/gas/CO2 prices, grid CO2 intensity, well "
        "and surface CAPEX factors and discount rate (all with cited sources). Returns, per "
        "design, the probability of meeting all demand, P10/P50/P90 levelised cost "
        "(EUR/MWh) and CO2 (kt/yr), and pairwise 'how often is A cheaper than B'. Use it "
        "after screening, on the 2-6 best designs, before recommending one. "
        "Cost: about 0.25 s per design per sample on 4 cores."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "designs": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 8,
                "description": (
                    "Design names like '2D-3100m-boiler-electric', "
                    "'1D-2800m-boiler-electric-chp' or '2D-3100m-boiler-absorption+C12' "
                    "(+C<MW> resizes the chiller, +B<MW> the boiler)."
                ),
            },
            "n_samples": {
                "type": "integer",
                "minimum": 8,
                "maximum": MAX_SAMPLES,
                "default": 100,
                "description": "Latin-hypercube samples shared by all designs.",
            },
            "seed": {"type": "integer", "default": 2027},
            "tornado_design": {
                "type": "string",
                "description": "Optional design to run a P10/P90 one-at-a-time tornado on.",
            },
            "fix_parameters": {
                "type": "array",
                "items": {"type": "string", "enum": [p.name for p in PARAMETERS]},
                "description": "Parameters to hold at their base value (removed from sampling).",
            },
            "override_distributions": {
                "type": "object",
                "description": (
                    "Replace a distribution, e.g. {'permeability_md': {'dist': 'lognormal', "
                    "'args': [150, 60, 300]}}. Triangular args: low, mode, high; normal: "
                    "mean, sd, low clip, high clip; lognormal: median, P10, P90."
                ),
            },
            "output_dir": {
                "type": "string",
                "description": "Optional folder for CSV results; nothing is written if absent.",
            },
        },
        "required": ["designs"],
    },
}


def _clean(value):
    """Make numpy scalars and NaN JSON-safe."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (np.floating, float)):
        return None if np.isnan(value) else round(float(value), 4)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def run_tool(arguments, demand=None, workers=None):
    """Run ``assess_design_uncertainty`` and return a JSON-safe result dict.

    Errors in the arguments come back as ``{"error": ...}`` so the agent
    can correct itself instead of crashing the loop.
    """
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    try:
        designs = [design_from_name(n) for n in arguments["designs"]]
        n = int(arguments.get("n_samples", 100))
        if not 8 <= n <= MAX_SAMPLES:
            raise ValueError(f"n_samples must be between 8 and {MAX_SAMPLES}, got {n}")
        params = get_parameters(overrides=arguments.get("override_distributions"))
        fixed = set(arguments.get("fix_parameters") or [])
        unknown = fixed - {p.name for p in params}
        if unknown:
            raise KeyError(f"Unknown parameter(s) to fix: {sorted(unknown)}")
        sampled = tuple(p for p in params if p.name not in fixed)
    except (KeyError, ValueError, TypeError) as err:
        return {"error": str(err), "hint": "Check the tool schema and design-name format."}

    demand = demand if demand is not None else load_demand(DEFAULT_INPUTS)
    seed = int(arguments.get("seed", 2027))
    results, _ = monte_carlo(designs, demand, n, seed, sampled, workers)
    summary = summarise(results)
    base = base_case(designs, demand, params, workers)
    names = [d.name for d in designs]
    reference = summary["design"].iloc[0]
    comparisons = [compare(results, reference, other) for other in names if other != reference]

    out = {
        "n_samples": n,
        "seed": seed,
        "sampled_parameters": [p.name for p in sampled],
        "fixed_parameters": sorted(fixed),
        "base_case": base[
            ["design", "demand_met", "lcoe_eur_per_mwh", "co2_t_per_year", "capex_meur"]
        ].to_dict("records"),
        "summary": summary.to_dict("records"),
        "best_by_reliability_then_cost": reference,
        "paired_comparisons": comparisons,
        "notes": [
            "p_demand_met counts samples where every day's heating and cooling demand is met "
            "and every hard constraint holds.",
            "Levelised cost = (CAPEX x CRF + 2% fixed O&M + energy and CO2 cost) / delivered "
            "heat + cooling, real 2026 EUR.",
        ],
    }
    if arguments.get("tornado_design"):
        t_design = design_from_name(arguments["tornado_design"])
        table = tornado(t_design, demand, params, workers=workers)
        out["tornado"] = (
            table[
                [
                    "parameter",
                    "input_low",
                    "input_high",
                    "lcoe_low",
                    "lcoe_high",
                    "lcoe_swing",
                    "co2_low",
                    "co2_high",
                ]
            ]
            .head(8)
            .to_dict("records")
        )
    if arguments.get("output_dir"):
        folder = Path(arguments["output_dir"])
        folder.mkdir(parents=True, exist_ok=True)
        results.to_csv(folder / "mc_results.csv", index=False)
        summary.to_csv(folder / "mc_summary.csv", index=False)
        describe_parameters(params).to_csv(folder / "parameters.csv", index=False)
        out["files"] = [
            str(folder / f) for f in ("mc_results.csv", "mc_summary.csv", "parameters.csv")
        ]
    return _clean(out)
