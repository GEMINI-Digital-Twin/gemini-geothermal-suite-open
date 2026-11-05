"""Plain-language "Steps taken" dropdown for the chat (one collapsible group per user turn).

Each model decision and the tool it ran become one numbered step: what the agent did, in words,
the key result, and -- expandable -- the exact arguments, the recorded fact ID, tokens and seconds.
Built from the same trace events the evidence appendix uses, so the UI shows what was logged.
"""

from __future__ import annotations

import html
import json
import re

WHAT = {
    "get_brief": "Read the design brief and its hard limits",
    "analyze_demand": "Analysed the 2027 heating and cooling demand",
    "list_gemini_models": "Checked which GEMINI models exist and which are missing",
    "fetch_weather": "Loaded site weather (ERA5) for the cooling towers",
    "reservoir_at_depth": "Looked up the reservoir at a depth",
    "well_performance": "Computed well flow, pump power and heat per doublet with GEMINI",
    "evaluate_design": "Simulated a design over a full year (365 days)",
    "search_designs": "Searched depths, doublets, heat pumps and cooling options",
    "compare_designs": "Compared designs side by side",
    "stress_test_design": "Stress-tested the design",
    "uncertainty_analysis": "Ran a Monte Carlo uncertainty analysis",
    "sensitivity_analysis": "Ranked the inputs that drive cost and CO2",
    "add_capacity_margin": "Added capacity margin and re-simulated",
    "break_even_analysis": "Found the break-even point between two options",
    "seasonal_balance": "Compared summer surplus with winter shortfall (storage potential)",
    "generate_model": "Generated and tested a new GEMINI model (Model Forge)",
    "run_model": "Ran a GEMINI model",
    "ask_user": "Asked you for a missing input",
    "check_numbers": "Checked every number in a draft against the fact ledger",
    "export_gemini_project": "Re-simulated the peak day in GEMINI's own solver",
    "save_design_package": "Saved the design package (spec, KPIs, daily CSV)",
    "verify_design": "Ran all robustness and verification checks",
    "write_todos": "Wrote or updated its plan",
    "read_file": "Read domain knowledge (a skill)",
    "task": "Delegated to a specialist",
}


def _result_line(tool: str, output: str) -> str:
    """One short, human-readable result of a tool call."""
    try:
        r = json.loads(output)
    except (ValueError, TypeError):
        return output[:160]
    if not isinstance(r, dict):
        return ""
    if "error" in r:
        return f"error: {str(r['error'])[:140]}"
    if tool == "verify_design":
        st = r.get("stress", {})
        return (
            f"stress tests {'passed' if all(v.get('survives') for v in st.values()) else 'FAILED: ' + ', '.join(r.get('failed', []))}, "  # noqa: E501
            f"GEMINI solver {'agrees' if r.get('gemini_solver', {}).get('consistent') else 'disagrees'}, "  # noqa: E501
            f"main cost drivers: {', '.join(r.get('sensitivity', {}).get('top_lcoe_drivers', []))}"
        )
    if tool == "search_designs" and r.get("top"):
        b = r["top"][0]
        return f"{r.get('designs_evaluated')} designs simulated; best: {b.get('label')} · {b.get('lcoe_eur_per_mwh')} €/MWh"  # noqa: E501
    if "label" in r:
        bits = [r["label"]]
        if "feasible" in r:
            bits.append(
                "feasible"
                if r["feasible"]
                else "NOT feasible: " + ", ".join(r.get("violations", []))
            )
        if "lcoe_eur_per_mwh" in r:
            co2 = r.get("co2_t_per_year", r.get("co2_t"))
            bits.append(
                f"{r['lcoe_eur_per_mwh']} €/MWh, {co2:,.0f} t CO₂/yr"
                if isinstance(co2, (int, float))
                else f"{r['lcoe_eur_per_mwh']} €/MWh"
            )
        return " · ".join(str(b) for b in bits)
    if r.get("scenario", "").startswith("demand_plus") and "feasible" in r:
        return f"{r['scenario']}: {'survives' if r['feasible'] else 'FAILS'}"
    if "survives" in r:
        return f"{r.get('scenario')}: {'survives' if r['survives'] else 'FAILS'} (unmet heat {r.get('unmet_heat_mw')} MW)"  # noqa: E501
    if "consistent" in r:
        return f"GEMINI solver {'agrees with' if r['consistent'] else 'DIFFERS from'} the screening"
    if "heating_peak_mw" in r:
        return (
            f"heating peak {r['heating_peak_mw']} MW on {r.get('heating_peak_date')}, cooling peak "
            f"{r.get('cooling_peak_mw')} MW"
        )
    if "temperature_c" in r and "depth_m" in r:
        return f"{r['temperature_c']} °C and {r.get('pressure_bar')} bar at {r['depth_m']:g} m"
    if "max_thermal_power_mw_at_40K" in r:
        return f"up to {r['max_thermal_power_mw_at_40K']} MW per doublet at a 40 °C brine temperature drop"  # noqa: E501
    if tool == "fetch_weather":
        return (
            "default site used (none given in the brief)"
            if "NOT SPECIFIED" in str(r.get("location"))
            else f"weather for {r.get('location')}"
        )
    if tool == "list_gemini_models":
        return "model coverage and gaps listed"
    if tool == "save_design_package":
        return "saved"
    if "question" in r:
        return f"asked: {r['question']}"[:200]
    if "probability_demand_fully_met" in r:
        lc = r.get("lcoe_eur_per_mwh", {})
        return (
            f"{r.get('samples')} samples · LCOE P10–P90 {lc.get('P10')}–{lc.get('P90')} €/MWh "
            f"· demand fully met "
            f"in {round(100 * r['probability_demand_fully_met'])} % of samples"
        )
    if "ranked_by_lcoe_swing" in r:
        return "biggest cost drivers: " + ", ".join(
            x["label"] for x in r["ranked_by_lcoe_swing"][:3]
        )
    if "answer" in r:
        return str(r["answer"])[:160]
    return ", ".join(
        f"{k}: {v}"
        for k, v in list(r.items())[:4]
        if k != "fact_id" and not isinstance(v, (dict, list))
    )[:160]


SPECIALIST = {
    "requirements-analyst": "Requirements analyst",
    "design-engineer": "Design engineer",
    "risk-verifier": "Risk & verification",
    "model-builder": "Model builder",
}
QUIET = {
    "read_file",
    "write_todos",
    "task",
    "ls",
    "edit_file",
    "write_file",
}  # outputs are not one-liners


def _report(out: str) -> str:
    """A specialist's report out of the framework's Command(...) wrapper."""
    m = re.search(r"content='(.*?)', name=", out, re.S) or re.search(
        r'content="(.*?)", name=', out, re.S
    )
    text = (m.group(1) if m else out).replace("\\n", "\n")
    return text[:900] + ("…" if len(text) > 900 else "")


def _args(a: dict) -> str:
    """Tool arguments as 'key = value' pairs instead of raw JSON."""
    out = []
    for k, v in (a or {}).items():
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x) for x in v)
        elif isinstance(v, dict):
            v = ", ".join(f"{kk} {vv}" for kk, vv in v.items())
        out.append(f"{k.replace('_', ' ')} = {v}")
    return " · ".join(out)[:240]


def _title(st: dict) -> str:
    icon = "<span class='gd-ok'>✓</span>" if st.get("done") else "<span class='gd-run'>•</span>"
    who = f"<span class='gd-who'>{st['who']}</span>" if st.get("who") else ""
    res = f" <span class='gd-res'>→ {html.escape(st['res'][:170])}</span>" if st.get("res") else ""
    return f"{icon} {who}{html.escape(st['title'])}{res}"


def step_messages(events: list[dict], parent_id: str) -> list[dict]:
    """Child chat messages, one per step, nested under the dropdown ``parent_id``: a green check when a  # noqa: E501
    step has finished, the specialist that ran it (deep profile), the result in one line,
    details inside.
    """
    steps, pending, unassigned = [], {}, {}
    for n, e in enumerate(events):
        if e["type"] == "llm":
            meta = f"model call · {e['prompt_tokens']:,} + {e['completion_tokens']} tokens · {e['latency_s']} s"  # noqa: E501
            if e["agent"] == "router":
                steps.append(
                    {
                        "title": "Router classified the message",
                        "res": str(e.get("content")),
                        "done": True,
                        "body": [meta],
                    }
                )
                continue
            if not e.get("tool_calls"):
                nxt = next((x for x in events[n + 1 :] if x["type"] != "llm"), None)
                report = nxt and nxt["type"] == "tool_end" and nxt.get("tool") == "task"
                steps.append(
                    {
                        "title": "Specialist reported back" if report else "Wrote the answer",
                        "done": True,
                        "body": [meta],
                    }
                )
                continue
            for tc in e["tool_calls"]:
                a, body = tc.get("args") or {}, []
                if tc["name"] == "read_file":
                    path = str(a.get("file_path", ""))
                    title = (
                        "Read domain knowledge · "
                        + path.split("/")[-2 if path.endswith("SKILL.md") else -1]
                    )
                elif tc["name"] == "task":
                    who = SPECIALIST.get(
                        a.get("subagent_type"), a.get("subagent_type", "a specialist")
                    )
                    title = f"Delegated to {who}: {str(a.get('description', ''))[:110]}"
                    body.append(f"task: {a.get('description', '')}")
                elif tc["name"] == "write_todos":
                    todos = a.get("todos") or []
                    title = f"Wrote its plan · {len(todos)} tasks"
                    body += [
                        f"- {t.get('content', t) if isinstance(t, dict) else t}" for t in todos
                    ]
                else:
                    title = WHAT.get(tc["name"], tc["name"])
                    if a:
                        body.append(_args(a))
                st = {"title": title, "body": body + [meta]}
                steps.append(st)
                pending.setdefault(tc["name"], []).append(st)
                unassigned.setdefault(tc["name"], []).append(st)
        elif e["type"] == "tool_start":
            st = (
                (unassigned.get(e.get("tool")) or [None]).pop(0)
                if unassigned.get(e.get("tool"))
                else None
            )
            if st is not None:
                st["who"] = SPECIALIST.get(e.get("agent"))
        elif e["type"] == "tool_end":
            out = e.get("output", "")
            st = (
                (pending.get(e.get("tool")) or [None]).pop(0)
                if pending.get(e.get("tool"))
                else None
            )
            if st is None:  # a tool run by another tool (verify_design's parts)
                continue
            st["done"] = True
            if e.get("tool") == "task":
                st["body"].append("report: " + _report(out))
                continue
            fid = out.split('"')[3] if out.startswith('{"fact_id":"') else ""
            st["res"] = "" if e.get("tool") in QUIET else _result_line(e.get("tool"), out)
            st["body"].append(
                f"tool ran {e['latency_s']} s"
                + (f" · recorded as fact <kbd>{fid}</kbd>" if fid else "")
            )
    return [
        {
            "role": "assistant",
            "content": "  \n".join(st["body"]),
            "metadata": {"title": _title(st), "parent_id": parent_id, "status": "done"},
        }
        for st in steps
    ]


def live_step(events: list[dict], parent_id: str) -> list[dict]:
    """While a turn runs: a last line saying the model is deciding the next step (a running tool already  # noqa: E501
    shows as the last step, marked with a dot)."""
    last = next(
        (e for e in reversed(events) if e["type"] in ("llm", "tool_start", "tool_end")), None
    )
    if last is not None and last["type"] == "tool_start":
        return []
    text = "Waiting for the model" if last is None else "Thinking about the next step"
    return [
        {
            "role": "assistant",
            "content": "",
            "metadata": {
                "title": f"<span class='gd-run'>•</span> <span class='gd-res'>{text}</span>",
                "parent_id": parent_id,
                "status": "pending",
            },
        }
    ]


def annotate_turn(children: list[dict], turn: dict, parent_id: str) -> list[dict]:
    """Mark a draft the verifier rejected, and close the list with the verifier's verdict."""
    first = turn.get("revised_from")
    if first:
        p = first["provenance"]
        why = (
            [c["detail"] for c in p.get("claim_issues", [])]
            + [f"untraceable {x:g}" for x in p["unsupported"]]
            + [f"{u['number']} written as '{u['unit_written']}'" for u in p["unit_mismatches"]]
        )
        for m in children:
            if m["metadata"]["title"].endswith("Wrote the answer"):
                m["metadata"]["title"] = (
                    "<span class='gd-warn'>↺</span> Wrote a first draft <span class='gd-res'>→ "
                    "rejected by the verifier, sent back once</span>"
                )
                m["content"] += "  \nrejected for: " + html.escape("; ".join(why))
                break
    p = turn["provenance"]
    ok = p.get("passed", True)
    mark = "<span class='gd-ok'>✓</span>" if ok else "<span class='gd-bad'>✗</span>"
    verdict = (
        f"{mark} Verifier · {p['numbers_checked']} numbers checked <span class='gd-res'>→ "
        + ("all traceable" if ok else "issues flagged")
        + "</span>"
    )
    return children + [
        {
            "role": "assistant",
            "content": "deterministic check, no model call",
            "metadata": {"title": verdict, "parent_id": parent_id, "status": "done"},
        }
    ]
