"""Fixed tool sequence for an offline run (no LLM, 0 tokens).

Tests the loop and tools, and serves as a fallback demo if no model is
reachable. It is NOT the agent's reasoning: real runs decide each step with
an LLM. The scripted pick is the robust candidate with the lowest P50 LCOH.
"""

import json

from .llm_client import tool_call

N_SAMPLES = 12  # small, to keep the offline run fast


def _tool_results(messages, key):
    out = []
    for m in messages:
        if m.get("role") == "tool" and f'"{key}"' in (m.get("content") or ""):
            out.append(json.loads(m["content"]))
    return out


def _best_robust(messages):
    rob = [r for r in _tool_results(messages, "feasible_share") if r.get("robust")]
    return min(rob, key=lambda r: r["P10_P50_P90 (P90 conservative)"]["lcoh"][1])


def _sensitivity_for_best(messages):
    return tool_call("return_temperature_sensitivity", {"candidate_id": _best_robust(messages)["id"]})


def _finish(messages):
    best = _best_robust(messages)
    p10, p50, p90 = best["P10_P50_P90 (P90 conservative)"]["lcoh"]
    why = (f"Scripted pick: {best['id']} is robust ({best['feasible_share']:.0%} feasible) with "
           f"the lowest P50 LCOH {p50} EUR/MWh (P10 {p10}, P90 {p90}). Warnings are "
           f"stated, not resolved: PVT validity above 100 C (constant brine properties) and N-1 "
           f"(one doublet tripping on the peak day; partly covered by the backup boiler).")
    return tool_call("finish", {"candidate_id": best["id"], "justification": why})


def demo_script():
    base = {"max_flow_m3h": 300, "outage": "staggered", "boiler_capacity_mw": 10, "spacing_m": 1600}
    return [
        tool_call("get_problem_brief", {}),
        tool_call("inspect_gemini_capabilities", {}),
        tool_call("load_supplementary_model", {"name": "annual_dispatch"}),
        tool_call("load_supplementary_model", {"name": "heat_pump"}),
        tool_call("load_supplementary_model", {"name": "absorption_chiller"}),
        tool_call("load_supplementary_model", {"name": "electric_chiller"}),
        tool_call("assess_resource", {"depth_m": 2500}),
        tool_call("assess_resource", {"depth_m": 3300}),
        tool_call("run_gemini_project", {"depth_m": 2500, "target_flow_m3h": 200}),
        tool_call("evaluate_design", {**base, "depth_m": 2500, "n_doublets": 2, "hp_capacity_mw": 15,
                                      "chiller_type": "absorption_rated", "sorption_capacity_mw": 8,
                                      "elec_chiller_capacity_mw": 3, "label": "2 x 2500 m, rated absorption"}),
        tool_call("evaluate_design", {**base, "depth_m": 2500, "n_doublets": 2, "hp_capacity_mw": 15,
                                      "chiller_type": "absorption_dh", "sorption_capacity_mw": 10,
                                      "elec_chiller_capacity_mw": 4, "label": "2 x 2500 m, DH-type absorption"}),
        tool_call("evaluate_design", {**base, "depth_m": 3300, "n_doublets": 2, "hp_capacity_mw": 4,
                                      "chiller_type": "absorption_dh", "sorption_capacity_mw": 10,
                                      "elec_chiller_capacity_mw": 4, "label": "2 x 3300 m, DH-type absorption"}),
        tool_call("evaluate_design", {**base, "depth_m": 2500, "n_doublets": 3, "spacing_m": 1000,
                                      "hp_capacity_mw": 12, "chiller_type": "absorption_rated",
                                      "sorption_capacity_mw": 10, "elec_chiller_capacity_mw": 4,
                                      "label": "3 x 2500 m, 1000 m spacing"}),
        tool_call("compare_candidates", {}),
        tool_call("robustness_check", {"candidate_id": "D2", "n_samples": N_SAMPLES}),
        tool_call("robustness_check", {"candidate_id": "D3", "n_samples": N_SAMPLES}),
        _sensitivity_for_best,
        _finish,
    ]
