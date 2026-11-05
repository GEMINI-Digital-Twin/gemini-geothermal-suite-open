"""Agentic design loop for the GEMINI GeoHackathon 2026.

    demand profiles ──► agent proposes a design (JSON)
                            │
                  schema check (ranges, types)  ──reject──► feedback
                            │
         GEMINI well/gas physics + HEX + heat pump + chillers, 365 days
                            │
             deterministic validator (16 checks, no AI involved)
                            │
     KPIs + violations + history ──► agent reasons and proposes again …

The LLM never decides whether a design passes: only the validator does.
Every proposal, its reasoning and its verdict are logged in agent_log.md.

Usage
-----
    python agent.py                         # Ollama, model qwen2.5:7b, 20 iterations
    python agent.py --model qwen2.5:3b --iterations 15
    python agent.py --offline               # rule-based agent, no LLM needed
    python agent.py --api-base https://api.openai.com/v1 --model gpt-4o-mini   # key in OPENAI_API_KEY

Outputs: agent_log.md, agent_history.csv, agent_best_design.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from plant_model import (_BASE_JSON, GEO_GRADIENT, GLR, RHO_CO2_N, SUPPLY_TEMP_HEATING, SURFACE_TEMP,
                         TOTAL_DAYS, GEO_OPERATING_DAYS, Assumptions, Design)
from dispatch import Plant, load_demand, summarize, validate

HERE = Path(__file__).resolve().parent

# name: (min, max, integer?, meaning)
VARS = {
    "n_doublets": (1, 3, True, "number of geothermal doublets (producer + injector)"),
    "well_depth_m": (2000, 3500, False, "well TVD in m; reservoir T = 12 + 30*depth/1000 C, p hydrostatic"),
    "hex_ua_kw_per_k": (100, 2000, False, "plate heat exchanger size UA per doublet, kW/K"),
    "esp_stages": (10, 60, True, "ESP pump stages (more stages = more lift = more flow)"),
    "backup_boiler_mw": (0, 40, False, "installed natural-gas backup boiler, MW heat at 100 C"),
    "electric_chiller_mw": (0, 15, False, "installed electric chiller, MW cooling at 20 C"),
    "absorption_chiller_mw": (0, 15, False, "installed absorption chiller (100 C heat driven), MW cooling"),
}


def to_design(v):
    return Design(n_doublets=int(v["n_doublets"]), well_depth_m=float(v["well_depth_m"]),
                  hex_ua_w_per_k=float(v["hex_ua_kw_per_k"]) * 1e3, esp_stages=int(v["esp_stages"]),
                  backup_boiler_mw=float(v["backup_boiler_mw"]),
                  electric_chiller_mw=float(v["electric_chiller_mw"]),
                  absorption_chiller_mw=float(v["absorption_chiller_mw"]))


def schema_check(raw):
    """Validate an agent proposal. Returns (clean_dict, errors)."""
    if not isinstance(raw, dict):
        return None, ["'design' must be a JSON object"]
    clean, errors = {}, []
    for k, (lo, hi, is_int, _) in VARS.items():
        if k not in raw:
            errors.append(f"missing '{k}'")
            continue
        try:
            x = float(raw[k])
        except (TypeError, ValueError):
            errors.append(f"'{k}' must be a number, got {raw[k]!r}")
            continue
        if math.isnan(x) or not lo <= x <= hi:
            errors.append(f"'{k}'={x:g} outside allowed range [{lo}, {hi}]")
            continue
        clean[k] = int(round(x)) if is_int else round(x, 3)
    extra = set(raw) - set(VARS)
    if extra:
        errors.append(f"unknown keys {sorted(extra)} ignored")
    return (clean if len(clean) == len(VARS) else None), errors


# ─────────────────────────── evaluation (GEMINI + validator) ────────────────
class Evaluator:
    def __init__(self, assumptions):
        self.a = assumptions
        self.dates, self.H, self.C = load_demand(HERE)
        self.cache = {}

    def __call__(self, v):
        key = tuple(v[k] for k in VARS)
        if key in self.cache:
            return dict(self.cache[key], repeated=True)
        d = to_design(v)
        t0 = time.time()
        try:
            df = Plant(d, self.a).simulate_year(self.dates, self.H, self.C)
        except RuntimeError as e:   # e.g. no well operating point inside 50-300 m3/h
            res = dict(feasible=False, failed=[f"Well hydraulics: {e}"], checks=[], kpi={})
            self.cache[key] = res
            return res
        s = summarize(df, d)
        checks = validate(df, d)
        act = df[df.geothermal_active]
        kpi = {
            "co2_t_per_year": s["co2_t_per_year"],
            "geothermal_share_pct": s["geothermal_chain_share_pct"],
            "backup_boiler_share_pct": s["backup_boiler_share_pct"],
            "net_electricity_MWh": s["net_electricity_MWh"],
            "unmet_heating_MWh": s["unmet_heating_MWh"],
            "unmet_cooling_MWh": s["unmet_cooling_MWh"],
            "max_heating_shortfall_MW": round(float((df.heating_demand_MW - df.heating_delivered_MW).max()), 2),
            "max_cooling_shortfall_MW": round(float((df.cooling_demand_MW - df.cooling_delivered_MW).max()), 2),
            "peak_backup_boiler_used_MW": s["peak_backup_boiler_MW"],
            "peak_electric_chiller_used_MW": s["peak_electric_chiller_MW"],
            "peak_absorption_chiller_used_MW": s["peak_absorption_chiller_MW"],
            "reservoir_T_C": s["reservoir_T_C"],
            "flow_range_m3h": [round(float(act.flow_per_doublet_m3h.min()), 1),
                               round(float(act.flow_per_doublet_m3h.max()), 1)],
            "max_brine_cooling_C": s["max_brine_cooling_C"],
            "mean_hp_COP": s["mean_hp_COP"],
            "maintenance_block": s["maintenance_block"],
            "sim_seconds": round(time.time() - t0, 1),
        }
        res = dict(feasible=all(ok for _, ok, _ in checks),
                   failed=[f"{n}: {det}" for n, ok, det in checks if not ok],
                   checks=[(n, ok, det) for n, ok, det in checks], kpi=kpi)
        self.cache[key] = res
        return res


# ─────────────────────────── prompts ────────────────────────────────────────
def demand_brief(dates, H, C):
    ih, ic = H.argmax(), C.argmax()
    return (f"Heating: 365 daily values, peak {H.max():.1f} MW on {dates[ih]}, minimum {H.min():.1f} MW, "
            f"annual {H.sum() * 24 / 1000:.2f} GWh. Cooling: peak {C.max():.1f} MW on {dates[ic]}, "
            f"annual {C.sum() * 24 / 1000:.2f} GWh, zero in winter.")


SYSTEM = """You are a geothermal plant design engineer working in a loop with a simulator.
Goal: design a deep-geothermal district heating AND cooling plant for 2027.

Plant: 1-3 doublets (producer well with electric submersible pump + injector), separator
(produced gas 80% CH4 / 20% CO2 is burned on site), plate heat exchanger, heat pump lifting
district water from 40 C return to 100 C supply, absorption + electric chillers for 20 C
cooling, natural-gas backup boiler. A dispatcher operates the plant day by day at lowest CO2;
geothermal runs 330 days (one 35-day maintenance block chosen automatically) - on those 35 days
only the backup boiler and the electric chiller serve the demand.

Hard rules checked by an independent validator after every simulation:
flow 50-300 m3/h per active doublet, brine cooling <= 40 C (producer to injector),
pump efficiency 70%, produced = injected volume, 100 C heating and 20 C cooling supply,
heating AND cooling demand met every single day, exactly 330 geothermal days,
energy, electricity and gas balances closed.

Objective, in this order:
 1. every check PASSES (no unmet heating or cooling on any day);
 2. lowest annual CO2 emissions;
 3. if CO2 is about equal, the smaller plant (fewer doublets, smaller boiler and chillers),
    because no cost data is given.

Design variables (all required, numbers only):
{vars}

Engineering facts (use them):
- Geothermal heat is almost CO2-free; every MWh from the backup gas boiler emits {gas_kg_mwh:.0f} kg CO2.
  So MORE geothermal capacity (more doublets) normally LOWERS CO2. Fewer doublets makes the
  plant smaller but RAISES CO2 - only remove a doublet if CO2 stays about the same.
- Hotter (deeper) brine raises heat-pump COP; below about {depth_no_hp:.0f} m the brine reaches the
  heat exchanger above 100 C, so the heat exchanger alone can heat the water to 100 C.
- Produced gas releases {brine_co2:.2f} kg CO2 per m3 of brine: a fixed cost of producing brine.
- The backup boiler and the electric chiller alone must cover the demand during the {maint}-day
  maintenance block (it can fall in summer, with up to {peak_cool:.1f} MW cooling) and any peak
  geothermal cannot cover. Size them from "peak_..._used_MW" plus 5-10 %.
- The absorption chiller turns spare summer geothermal heat into cooling.
- Change one or two variables per step so you learn what each one does.
- NEVER propose a design that is already in the history.

Reply with ONE JSON object and nothing else:
{{"reasoning": "<max 80 words: what you learned from the last result and why this change>",
  "design": {{"n_doublets": ..., "well_depth_m": ..., "hex_ua_kw_per_k": ..., "esp_stages": ...,
             "backup_boiler_mw": ..., "electric_chiller_mw": ..., "absorption_chiller_mw": ...}}}}
or, only when the best design so far passes every check and you cannot improve it:
{{"reasoning": "<why you stop>", "action": "finish"}}"""


def vars_text():
    return "\n".join(f"- {k}: {lo}-{hi}{' (integer)' if i else ''}  {m}" for k, (lo, hi, i, m) in VARS.items())


def prompt_facts(a, C):
    """Numbers quoted in the system prompt, computed from the model - not typed in."""
    comp = _BASE_JSON["components"]
    drops = comp["separator"]["parameters"]["temperature_drop"] + comp["filter_a"]["parameters"]["temperature_drop"]
    t_res_needed = SUPPLY_TEMP_HEATING + drops + a.wellbore_heat_loss_c
    return dict(gas_kg_mwh=a.gas_ef_kg_per_gj * 3.6 / a.backup_boiler_eff,
                brine_co2=GLR * RHO_CO2_N,            # every CH4 and CO2 molecule leaves as CO2
                depth_no_hp=(t_res_needed - SURFACE_TEMP) / GEO_GRADIENT * 1000.0,
                maint=TOTAL_DAYS - GEO_OPERATING_DAYS, peak_cool=float(C.max()))


def untried_directions(hist, best):
    tried = [h["design"] for h in hist if h.get("design") is not None]
    out = []
    for k, (lo, hi, _, _) in VARS.items():
        b = best["design"][k]
        if b < hi and not any(d[k] > b for d in tried):
            out.append(f"higher {k}")
        if b > lo and not any(d[k] < b for d in tried):
            out.append(f"lower {k}")
    return out


def history_text(hist):
    if not hist:
        return "(no designs tried yet)"
    rows = []
    for h in hist:
        if h.get("design") is None:
            rows.append(f"#{h['iter']}: rejected proposal ({'; '.join(h['errors'])})")
            continue
        d = h["design"]
        verdict = "PASS" if h["feasible"] else "FAIL"
        co2 = h["kpi"].get("co2_t_per_year", "-")
        rows.append(f"#{h['iter']}: " + ", ".join(f"{k}={d[k]}" for k in VARS) + f" -> {verdict}, CO2 {co2} t")
    return "\n".join(rows)


def user_prompt(brief, hist, best):
    parts = [f"Demand: {brief}", "", "Designs tried so far:", history_text(hist)]
    last = hist[-1] if hist else None
    if last and last.get("design") is not None:
        parts += ["", f"Result of the last design (#{last['iter']}):",
                  "Validator: " + ("ALL CHECKS PASS" if last["feasible"] else "FAILED -> " + " | ".join(last["failed"])),
                  "KPIs: " + json.dumps(last["kpi"])]
    elif last:
        parts += ["", "Your last reply was rejected: " + "; ".join(last["errors"]) + ". Correct it."]
    if best:
        parts += ["", f"Best passing design so far: #{best['iter']} with CO2 {best['kpi']['co2_t_per_year']} t."]
        if last and last.get("design") is not None and last is not best:
            changed = [f"{k} {best['design'][k]} -> {last['design'][k]}" for k in VARS
                       if best["design"][k] != last["design"][k]]
            co2 = last["kpi"].get("co2_t_per_year")
            if changed and co2 is not None:
                delta = co2 - best["kpi"]["co2_t_per_year"]
                parts.append(f"Effect of your last change versus the best design: {', '.join(changed)} "
                             f"=> CO2 {delta:+.0f} t, {'PASS' if last['feasible'] else 'FAIL'}.")
        untried = untried_directions(hist, best)
        if untried:
            parts.append("Directions never tried yet from the best design: " + ", ".join(untried) + ".")
    else:
        parts += ["", "No design has passed all checks yet."]
    parts += ["", "Propose the next design as JSON."]
    return "\n".join(parts)


def parse_reply(text):
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e <= s:
        raise ValueError("no JSON object in reply")
    return json.loads(text[s:e + 1])


# ─────────────────────────── LLM back-ends ──────────────────────────────────
class OllamaLLM:
    def __init__(self, model, host):
        self.model, self.host = model, host.rstrip("/")
        self.name = f"Ollama {model}"

    def __call__(self, system, user):
        body = json.dumps({"model": self.model, "stream": False, "format": "json",
                           "options": {"temperature": 0.3},
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}]}).encode()
        req = urllib.request.Request(self.host + "/api/chat", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read())["message"]["content"]


class OpenAICompatLLM:
    def __init__(self, model, base, key):
        self.model, self.base, self.key = model, base.rstrip("/"), key
        self.name = f"{model} via {base}"

    def __call__(self, system, user):
        body = json.dumps({"model": self.model, "temperature": 0.3,
                           "response_format": {"type": "json_object"},
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}]}).encode()
        req = urllib.request.Request(self.base + "/chat/completions", body,
                                     {"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"})
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]


class RuleAgent:
    """Deterministic engineer used with --offline (and as a reference policy).

    Starts from a deliberately small plant (GEMINI-example-like), repairs
    violations, then tries one improvement move at a time and keeps it only
    if the validator passes and CO2 drops; finally right-sizes equipment.
    """
    name = "rule-based agent (offline)"
    MOVES = ("n_doublets", "well_depth_m", "hex_ua_kw_per_k", "esp_stages", "absorption_chiller_mw", "right_size")

    def __init__(self):
        self.tried = set()

    def propose(self, hist, best):
        if not hist:
            return ("Start small, like the GEMINI example: one doublet at the reservoir midpoint, "
                    "small HEX and pump, small backup units. The validator will tell what is missing.",
                    dict(n_doublets=1, well_depth_m=2500, hex_ua_kw_per_k=250, esp_stages=10,
                         backup_boiler_mw=5, electric_chiller_mw=5, absorption_chiller_mw=0))
        last = hist[-1]
        if not last["feasible"]:
            d, k = dict(last["design"]), last["kpi"]
            why = []
            if k.get("max_heating_shortfall_MW", 0) > 0:
                d["backup_boiler_mw"] = min(40, math.ceil(d["backup_boiler_mw"] + k["max_heating_shortfall_MW"] + 0.5))
                why.append(f"heating short by {k['max_heating_shortfall_MW']} MW -> enlarge backup boiler")
            if k.get("max_cooling_shortfall_MW", 0) > 0:
                d["electric_chiller_mw"] = min(15, math.ceil(d["electric_chiller_mw"] + k["max_cooling_shortfall_MW"] + 0.5))
                why.append(f"cooling short by {k['max_cooling_shortfall_MW']} MW -> enlarge electric chiller")
            if why:
                return "; ".join(why) + ".", d
            if best:  # failure we cannot repair locally: go back to the best design
                return "Violation not related to equipment size; revert to best passing design.", dict(best["design"])
            return "Unrepairable start; try a larger plant.", dict(last["design"], n_doublets=3, esp_stages=40)
        base = dict(best["design"])
        for move in self.MOVES:
            if (move, tuple(base.values())) in self.tried:
                continue
            self.tried.add((move, tuple(base.values())))
            d = dict(base)
            if move == "n_doublets" and d["n_doublets"] < 3:
                d["n_doublets"] += 1
                return "Passing; add a doublet to raise geothermal capacity and cut backup gas.", d
            if move == "well_depth_m" and d["well_depth_m"] < 3500:
                d["well_depth_m"] = min(3500, d["well_depth_m"] + 500)
                return "Go 500 m deeper: +15 C brine, higher heat-pump COP or no heat pump at all.", d
            if move == "hex_ua_kw_per_k" and d["hex_ua_kw_per_k"] < 2000:
                d["hex_ua_kw_per_k"] = min(2000, d["hex_ua_kw_per_k"] * 2)
                return "Double the heat-exchanger size: more direct heat, less heat-pump work.", d
            if move == "esp_stages" and d["esp_stages"] < 60:
                d["esp_stages"] = min(60, d["esp_stages"] + 20)
                return "More ESP stages: higher reachable flow on peak days.", d
            if move == "absorption_chiller_mw" and d["absorption_chiller_mw"] < 15:
                d["absorption_chiller_mw"] = min(15, d["absorption_chiller_mw"] + 5)
                return "Add absorption-chiller capacity: summer geothermal heat can make cooling.", d
            if move == "right_size":
                k = best["kpi"]
                new = dict(d,
                           backup_boiler_mw=math.ceil(k["peak_backup_boiler_used_MW"] * 1.05 * 2) / 2,
                           electric_chiller_mw=math.ceil(k["peak_electric_chiller_used_MW"] * 1.05 * 2) / 2,
                           absorption_chiller_mw=math.ceil(k["peak_absorption_chiller_used_MW"] * 1.05 * 2) / 2)
                if new != d:
                    return "Right-size boiler and chillers to 105 % of their real peak use.", new
        return None, None   # nothing left to try


# ─────────────────────────── main loop ──────────────────────────────────────
def better(a, b):
    """a better than b (both feasible): lower CO2, ties -> smaller plant."""
    if b is None:
        return True
    ca, cb = a["kpi"]["co2_t_per_year"], b["kpi"]["co2_t_per_year"]
    if ca < cb - 0.5:
        return True
    size = lambda h: (h["design"]["n_doublets"], h["design"]["backup_boiler_mw"]
                      + h["design"]["electric_chiller_mw"] + h["design"]["absorption_chiller_mw"])
    return abs(ca - cb) <= 0.5 and size(a) < size(b)


def run(args):
    a = Assumptions()
    ev = Evaluator(a)
    brief = demand_brief(ev.dates, ev.H, ev.C)
    system = SYSTEM.format(vars=vars_text(), **prompt_facts(a, ev.C))
    if args.offline:
        llm, rules = None, RuleAgent()
        agent_name = rules.name
    elif args.api_base:
        key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY", "")
        llm, rules = OpenAICompatLLM(args.model, args.api_base, key), None
        agent_name = llm.name
    else:
        llm, rules = OllamaLLM(args.model, args.host), None
        agent_name = llm.name

    hist, best = [], None
    log = [f"# Agent log — GEMINI GeoHackathon 2026", "",
           f"Agent: **{agent_name}** · started {time.strftime('%Y-%m-%d %H:%M')} · max {args.iterations} iterations",
           "", f"Demand: {brief}", "",
           "The validator (not the agent) decides PASS/FAIL. Each entry: the agent's reasoning, its design, "
           "the verdict.", ""]
    print(f"Agent: {agent_name}\n{brief}\n")

    for it in range(1, args.iterations + 1):
        t0 = time.time()
        reasoning, raw, action = "", None, None
        if rules:
            reasoning, raw = rules.propose(hist, best)
            if raw is None:
                action, reasoning = "finish", "All improvement moves tried around the best design; stop."
        else:
            try:
                reply = llm(system, user_prompt(brief, hist, best))
                msg = parse_reply(reply)
                reasoning = str(msg.get("reasoning", ""))[:600]
                action = msg.get("action")
                raw = msg.get("design")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                print(f"\nCannot reach the LLM ({e}).\nIs Ollama running and is the model pulled? "
                      f"Try: ollama pull {args.model}   or run: python agent.py --offline")
                if not hist:
                    print("Nothing was run; existing agent files are left unchanged.")
                    return
                break
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                hist.append(dict(iter=it, design=None, errors=[f"unreadable reply: {e}"], feasible=False, kpi={}))
                log += [f"## Iteration {it} — rejected", f"Unreadable reply: {e}", ""]
                print(f"[{it:2d}] unreadable reply ({e})")
                continue

        if action == "finish":
            untried = untried_directions(hist, best) if best else []
            if best and untried and it < args.iterations and not rules:
                msg = "finish refused: directions never tried from the best design: " + ", ".join(untried)
                hist.append(dict(iter=it, design=None, errors=[msg], feasible=False, kpi={}, reasoning=reasoning))
                log += [f"## Iteration {it} — finish refused", f"> {reasoning}", "", msg + ".", ""]
                print(f"[{it:2d}] {msg}")
                continue
            if best:
                log += [f"## Iteration {it} — agent stops", f"> {reasoning}", ""]
                print(f"[{it:2d}] agent stops: {reasoning}")
                break
            reasoning += " [finish refused: no passing design yet]"
            hist.append(dict(iter=it, design=None, errors=["cannot finish: no design passes all checks yet"],
                             feasible=False, kpi={}))
            log += [f"## Iteration {it} — finish refused", f"> {reasoning}", ""]
            continue

        clean, errors = schema_check(raw)
        if clean is None:
            hist.append(dict(iter=it, design=None, errors=errors, feasible=False, kpi={}, reasoning=reasoning))
            log += [f"## Iteration {it} — proposal rejected by schema check", f"> {reasoning}", "",
                    "Errors: " + "; ".join(errors), ""]
            print(f"[{it:2d}] rejected: {'; '.join(errors)}")
            continue

        twin = next((p for p in hist if p.get("design") == clean), None)
        if twin is not None:
            msg = (f"identical to design #{twin['iter']} (already simulated: "
                   f"{'PASS' if twin['feasible'] else 'FAIL'}, CO2 {twin['kpi'].get('co2_t_per_year')} t) - "
                   f"propose a design that is NOT in the history")
            hist.append(dict(iter=it, design=None, errors=[msg], feasible=False, kpi={}, reasoning=reasoning))
            log += [f"## Iteration {it} — repeat rejected", f"> {reasoning}", "", f"Rejected: {msg}.", ""]
            print(f"[{it:2d}] repeat of #{twin['iter']} rejected")
            continue

        res = ev(clean)
        h = dict(iter=it, design=clean, reasoning=reasoning, feasible=res["feasible"],
                 failed=res["failed"], kpi=res["kpi"], repeated=res.get("repeated", False))
        hist.append(h)
        improved = res["feasible"] and better(h, best)
        if improved:
            best = h
        verdict = "PASS" if res["feasible"] else "FAIL"
        co2 = res["kpi"].get("co2_t_per_year", "-")
        print(f"[{it:2d}] {verdict}  CO2 {co2:>8}  {to_design(clean).label()}"
              f"{'  <- new best' if improved else ''}{'  (repeat)' if h['repeated'] else ''}  ({time.time()-t0:.0f}s)")
        log += [f"## Iteration {it} — {verdict}{' — new best' if improved else ''}",
                f"> {reasoning}", "",
                "| " + " | ".join(VARS) + " |", "|" + "---|" * len(VARS),
                "| " + " | ".join(str(clean[k]) for k in VARS) + " |", "",
                f"CO₂ **{co2} t/yr** · geothermal share {res['kpi'].get('geothermal_share_pct', '-')} % · "
                f"unmet heat {res['kpi'].get('unmet_heating_MWh', '-')} MWh · "
                f"unmet cooling {res['kpi'].get('unmet_cooling_MWh', '-')} MWh", ""]
        if res["failed"]:
            log += ["Violations found by the validator:"] + [f"- {f}" for f in res["failed"]] + [""]

    # ── outcome ──
    rows = [dict(iter=h["iter"], **(h["design"] or {}), feasible=h["feasible"],
                 co2_t_per_year=h["kpi"].get("co2_t_per_year"), failed="; ".join(h.get("failed", h.get("errors", []))),
                 reasoning=h.get("reasoning", "")) for h in hist]
    pd.DataFrame(rows).to_csv(HERE / "agent_history.csv", index=False)
    if best:
        d = to_design(best["design"])
        (HERE / "agent_best_design.json").write_text(json.dumps(
            {"design": asdict(d), "assumptions": asdict(a), "agent": agent_name, "iteration": best["iter"],
             "co2_t_per_year": best["kpi"]["co2_t_per_year"], "reasoning": best["reasoning"]}, indent=2))
        log += ["## Result", f"Best passing design: iteration {best['iter']} — {d.label()}",
                f"CO₂ {best['kpi']['co2_t_per_year']} t/yr, geothermal share {best['kpi']['geothermal_share_pct']} %.",
                "", "Run `python run_full_year.py` to simulate and report it in full."]
        bench = HERE / "design_comparison.csv"
        if bench.exists():
            ref = pd.read_csv(bench)
            ref = ref[ref.feasible].co2_t_per_year.min()
            gap = 100 * (best["kpi"]["co2_t_per_year"] - ref) / ref
            log += ["", f"Benchmark: exhaustive grid search (optimize_design.py) best = {ref:.1f} t/yr; "
                        f"agent is {gap:+.1f} % from it after {len(hist)} iterations."]
        print(f"\nBest: iteration {best['iter']}  {d.label()}  CO2 {best['kpi']['co2_t_per_year']} t/yr")
    else:
        log += ["## Result", "No design passed all checks — run more iterations."]
        print("\nNo passing design found — try more --iterations or --offline.")
    (HERE / "agent_log.md").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("Written: agent_log.md | agent_history.csv" + (" | agent_best_design.json" if best else ""))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default="qwen2.5:7b")
    p.add_argument("--host", default="http://localhost:11434", help="Ollama server")
    p.add_argument("--api-base", default=None, help="OpenAI-compatible endpoint instead of Ollama")
    p.add_argument("--iterations", type=int, default=20)
    p.add_argument("--offline", action="store_true", help="rule-based agent, no LLM")
    run(p.parse_args())


if __name__ == "__main__":
    main()
