"""Fixed tool sequence for an offline run (no LLM, 0 tokens).

Used to test the loop and tools, and as a fallback demo if no model is
reachable. It is NOT the agent's reasoning: real runs decide each step with
an LLM. The last step reads the comparison table and picks the candidate with
no hard violations and the least purchased energy.
"""

import json

from .llm_client import tool_call


def _pick_final(messages):
    table = None
    for m in reversed(messages):
        if m.get("role") == "tool" and '"candidates"' in (m.get("content") or ""):
            table = json.loads(m["content"])["candidates"]
            break
    ok = [r for r in table if r["hard_violations"] == 0]
    best = min(ok, key=lambda r: r["net_elec_gwh"] * 2.5 + r["nat_gas_gwh"])
    why = (f"Scripted pick: {best['id']} has no hard violations and the lowest purchased energy "
           f"(net electricity {best['net_elec_gwh']} GWh, natural gas {best['nat_gas_gwh']} GWh, "
           f"electricity weighted x2.5).")
    return tool_call("finish", {"candidate_id": best["id"], "justification": why})


def demo_script():
    base = {"max_flow_m3h": 300, "outage": "staggered", "boiler_capacity_mw": 10}
    return [
        tool_call("get_problem_brief", {}),
        tool_call("inspect_gemini_capabilities", {}),
        tool_call("load_supplementary_model", {"name": "annual_dispatch"}),
        tool_call("load_supplementary_model", {"name": "heat_pump"}),
        tool_call("load_supplementary_model", {"name": "sorption_chiller"}),
        tool_call("load_supplementary_model", {"name": "electric_chiller"}),
        tool_call("assess_resource", {"depth_m": 2500}),
        tool_call("assess_resource", {"depth_m": 3300}),
        tool_call("run_gemini_project", {"depth_m": 2500, "target_flow_m3h": 200}),
        tool_call("evaluate_design", {**base, "depth_m": 2500, "n_doublets": 2, "hp_capacity_mw": 8,
                                      "sorption_capacity_mw": 8, "elec_chiller_capacity_mw": 3,
                                      "label": "2 doublets 2500 m, small HP"}),
        tool_call("evaluate_design", {**base, "depth_m": 2500, "n_doublets": 2, "hp_capacity_mw": 15,
                                      "sorption_capacity_mw": 8, "elec_chiller_capacity_mw": 6,
                                      "label": "2 doublets 2500 m, HP 15 MW"}),
        tool_call("evaluate_design", {**base, "depth_m": 2500, "n_doublets": 3, "hp_capacity_mw": 12,
                                      "sorption_capacity_mw": 10, "elec_chiller_capacity_mw": 4,
                                      "label": "3 doublets 2500 m"}),
        tool_call("evaluate_design", {**base, "depth_m": 3300, "n_doublets": 2, "hp_capacity_mw": 4,
                                      "sorption_capacity_mw": 10, "elec_chiller_capacity_mw": 4,
                                      "label": "2 doublets 3300 m, small HP"}),
        tool_call("compare_candidates", {}),
        _pick_final,
    ]
