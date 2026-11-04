"""The code plan of the design agent: brief parsing, return sweeps, checks, the repair loop, alternatives and their sentences."""
import re

import AI01_log as log
import AI02_tools as tools
import AI03_moves as moves_
import AI04_check as checker

brief_peak, brief_site, brief_priority = checker.brief_peak, checker.brief_site, checker.brief_priority
SITE_DEFAULTS = {"depth_m": 2500.0, "supply_heat_c": 100.0, "supply_cold_c": 20.0}   # the challenge site


def pick(sweeps):
    """Smallest n whose best return meets checker.meets_rule; else the one with the least boiler."""
    row = lambda s: s["by_return_C"][str(s["best_return_c"])]
    sweeps = [s for s in sweeps if "error" not in s]
    ok = [s for s in sweeps if checker.meets_rule(row(s))]
    s = ok[0] if ok else min(sweeps, key=lambda s: row(s)["boiler_GWh"])
    return s, row(s), bool(ok)


def brief_max_n(brief):
    m = re.search(r"(?:up to|at most|max(?:imum)?)\s+(\d)\s+doublets", brief, re.I)
    return min(3, int(m.group(1))) if m else 3


def brief_inputs(brief):
    """Peaks (heat, cold), the site with defaults filled in, and what the brief gave (None where it gave nothing)."""
    ph, pc = brief_peak(brief, "heat"), brief_peak(brief, "cool")
    found = brief_site(brief)
    site = {k: (v if v is not None else d) for (k, d), v in zip(SITE_DEFAULTS.items(), found)}
    return ph, pc, site, found


def call(name, args):
    """A tool result, or {"error": ...} when the tool rejects its arguments."""
    try:
        return tools.call(name, {**SITE_DEFAULTS, **args} if name == "site_inputs" else args)
    except ValueError as e:
        return {"error": str(e)}


def name(n, t):
    return f"{n} doublet{'s' if n > 1 else ''} at {t:g} C"


def verdict(row, n, t, chosen):
    """(verdict, reason, number, unit) for swept candidate (n, t) against the chosen one; the rule itself is in AI04."""
    nc, tc = chosen
    fails = checker.rule_failures(row)
    ok = ("meets the rule", row["boiler_GWh"], "GWh")
    if (n, t) == (nc, tc):
        return ("chosen",) + (fails[0] if fails else ok)
    if n > nc:                                       # the plan stopped at the chosen count
        return ("not needed",) + (fails[0] if fails else ok)
    if fails:
        return ("rejected",) + fails[0]
    if n == nc and t > tc:
        return "rejected", "a lower return meets the rule", tc, "C"
    return "rejected", "needs boiler energy", row["boiler_GWh"], "GWh"   # meets the rule, but the chosen return needs less boiler


def iterations(sweeps, chosen):
    """One step per swept candidate, in the order tried."""
    steps = []
    for s in sorted(sweeps, key=lambda s: s["n_doublets"]):
        for t in tools.SWEEP_C:
            v, why, x, unit = verdict(s["by_return_C"][str(t)], s["n_doublets"], t, chosen)
            steps.append({"candidate": name(s["n_doublets"], t), "n_doublets": s["n_doublets"], "t_return_c": t,
                          "verdict": v, "reason": why, "number": f"{x:g} {unit}", "tag": "[C]"})
    return steps


def optimised(design, out, brief, max_n):
    """Optimise from the repaired design; the design moves to the front row best on the brief's priority. Returns the front steps."""
    pr = brief_priority(brief)
    args = {k: v for k, v in design.items() if k not in ("n_doublets", "t_return_c")}   # peaks, depth, ESP depth
    res = call("optimise_point", {**args, "priority": pr, "max_doublets": max_n})
    out.append({"name": "optimise_point", "args": {**args, "priority": pr, "max_doublets": max_n}, "result": res})
    best = res.get("best_on_priority") if "error" not in res else None
    if not best:   # nothing feasible: the sweep's choice stands
        return []
    design.update({"n_doublets": best["n"], "t_return_c": best["t_return_c"], "esp_depth_m": best["esp_depth_m"]})
    heat = {k: v for k, v in design.items() if k not in ("n_doublets", "t_return_c", "peak_cold_MW")}
    for p in res["front"]:   # every front row gets the year tools, so the model may choose any row and the checker can verify it
        d = {"n_doublets": p["n"], "t_return_c": p["t_return_c"], **args, "esp_depth_m": p["esp_depth_m"]}
        sweep = {"n_doublets": p["n"], **heat, "esp_depth_m": p["esp_depth_m"], "extra_return_c": p["t_return_c"]}
        out.append({"name": "return_sweep", "args": sweep, "result": call("return_sweep", sweep)})
        for k in ("checks", "heating_year", "cooling_year", "economics"):
            a = {k2: v for k2, v in d.items() if k2 != "peak_cold_MW"} if k == "heating_year" else d
            out.append({"name": k, "args": a, "result": call(k, a)})
    out.append({"name": "checks", "args": dict(design), "result": call("checks", dict(design))})   # the chosen design last
    return [{"candidate": name(p["n"], p["t_return_c"]) + f", ESP {p['esp_depth_m']:g} m", "n_doublets": p["n"],
             "t_return_c": p["t_return_c"], "esp_depth_m": p["esp_depth_m"],
             "verdict": "chosen" if (p["n"], p["t_return_c"]) == (best["n"], best["t_return_c"]) else "on the front",
             "reason": p["verdict"], "number": f"{p['lcoh_EUR_MWh']} EUR/MWh, {p['co2_total_kt']} kt CO2", "front": True, "tag": "[C]"}
            for p in res["front"]]


def plan(brief, chat=log.chat, records=None, exchanges=None):
    """The code plan's tool calls: site, demand, sweeps, checks, the repair loop, optimiser, years, economics, alternatives, trace.

    chat, records and exchanges go to the repair loop (AI03_moves): the model picks the moves, the run file shows the exchange.
    """
    ph, pc, _, found = brief_inputs(brief)
    esp = checker.brief_esp(brief)
    site = {k: v for k, v in zip(SITE_DEFAULTS, found) if v is not None}
    print(f"brief peaks: heat {ph} MW, cold {pc} MW, depth {found[0]} m, ESP {esp} m")
    dep = {} if found[0] is None else {"depth_m": found[0]}   # the brief's depth reaches every tool
    well = {**dep, **({} if esp is None else {"esp_depth_m": esp})}
    heat = {**well, **({} if ph is None else {"peak_heat_MW": ph})}
    peaks = {**heat, **({} if pc is None else {"peak_cold_MW": pc})}
    max_n = brief_max_n(brief)
    steps = [("site_inputs", site), ("demand_summary", {k: v for k, v in peaks.items() if k not in well})]
    steps += [("return_sweep", {"n_doublets": n, **heat}) for n in range(1, max_n + 1)]
    out = [{"name": k, "args": a, "result": call(k, a)} for k, a in steps]
    sweeps = [r["result"] for r in out if r["name"] == "return_sweep" and "error" not in r["result"]]
    s, _, _ = pick(sweeps)
    chosen = (s["n_doublets"], s["best_return_c"])
    design, life = {"n_doublets": chosen[0], "t_return_c": chosen[1], **peaks}, {}
    out.append({"name": "checks", "args": dict(design), "result": call("checks", dict(design))})
    moves = moves_.loop(brief, design, life, out, max_n, chat, records, exchanges)
    front = optimised(design, out, brief, max_n)
    n, t = design["n_doublets"], design["t_return_c"]
    peaks = {k: v for k, v in design.items() if k not in ("n_doublets", "t_return_c")}   # the moved inputs from here on
    heat = {k: v for k, v in peaks.items() if k != "peak_cold_MW"}
    well = {k: v for k, v in heat.items() if k != "peak_heat_MW"}
    cost = [("economics", {"n_doublets": m, "t_return_c": t, **peaks}) for m in (n, n + 1) if m <= 3]   # what the next doublet costs
    alts = [("layout_compare", {"n_doublets": n, "t_return_c": t, **peaks}), ("storage_point", {"n_doublets": n, "t_return_c": t, **heat})]
    for k, a in (*cost, *alts, ("heating_year", {"n_doublets": n, "t_return_c": t, **heat}),
                 ("cooling_year", {"t_return_c": t, "n_doublets": n, **peaks}), ("injector_point", {"q_m3h": 300, **dep}),
                 ("gas_point", {"q_m3h": 300, **well}), ("lifetime_point", {"n_doublets": n, "t_return_c": t, **heat, **life})):
        out.append({"name": k, "args": a, "result": call(k, a)})
    rep = {"n_doublets": n, "t_return_c": t, **{k: design[k] for k in ("depth_m", "esp_depth_m") if k in design}}
    out.append({"name": "gemini_replay", "args": rep, "result": call("gemini_replay", rep)})   # GEMINI's own solver on the design
    trace = iterations(sweeps, (n, t))
    by = {}
    for st in trace:
        if st["verdict"] == "rejected":
            by[st["reason"]] = by.get(st["reason"], 0) + 1
    out.append({"name": "design_iterations", "args": {},
                "result": {"tried": len(trace), "rejected": sum(by.values()), "not_needed": sum(st["verdict"] == "not needed" for st in trace),
                           "by_reason": by, "moves": len([m for m in moves if m.get("move")]),
                           "model_moves": len([m for m in moves if m.get("move") and m["by"] == "model"]),
                           "code_moves": len([m for m in moves if m.get("move") and m["by"] == "code"]),
                           "stopped": any(m["verdict"] == "stopped" for m in moves), "chosen": name(n, t), "n_doublets": n, "t_return_c": t,
                           "optimised": len(front), "steps": trace + moves + front, "tag": "[C]"}})

    econ = {r["args"]["n_doublets"]: r["result"] for r in out if r["name"] == "economics" and "error" not in r["result"]}
    if n in econ and n + 1 in econ:   # computed from two tool results so the checker can trace it
        out.append({"name": "economics_delta", "args": {"from_n": n, "to_n": n + 1},
                    "result": {"delta_lcoh_EUR_MWh": round(econ[n + 1]["lcoh_EUR_MWh"] - econ[n]["lcoh_EUR_MWh"], 2),
                               "delta_capex_MEUR": round(econ[n + 1]["capex_total_MEUR"] - econ[n]["capex_total_MEUR"], 2), "tag": "[C]"}})
    return out


def plan_message(brief, out):
    """The plan's choice in words, from the tool results of plan()."""
    ph, pc, site, found = brief_inputs(brief)
    _, _, ok = pick([r["result"] for r in out if r["name"] == "return_sweep"])
    it = next(r["result"] for r in out if r["name"] == "design_iterations")
    n, t = it["n_doublets"], it["t_return_c"]   # the design after any repair move
    key = str(int(t)) if float(t).is_integer() else str(t)
    row = next(r["result"]["by_return_C"][key] for r in out if r["name"] == "return_sweep" and r["result"].get("n_doublets") == n
               and key in r["result"].get("by_return_C", {}))
    scale = " ".join(f"{name.capitalize()} demand scaled to the brief's {v} MW peak." if v is not None else
                     f"No {name} peak found in the brief, so the {name} demand file is used as is ({d} MW)."
                     for name, v, d in (("heating", ph, 30.0), ("cooling", pc, 10.0)))
    miss = [f"{k} (default {site[k]:g})" for k, v in zip(site, found) if v is None]
    site_msg = ("Site from the brief: " + ", ".join(f"{k} {v:g}" for k, v in site.items()) + "."
                + (f" Not found in the brief, defaults used: {', '.join(miss)}." if miss else ""))
    si = out[0]["result"]
    if "error" in si:
        site_msg += f" site_inputs rejected these inputs: {si['error']}. The design cannot be trusted for them [C]."
    elif not si["supported"]:
        site_msg += f" {si['message']}. The design cannot be trusted for these inputs [D, A]."
    rule = ("the smallest number of doublets whose best_return_c leaves no heat unmet with boiler energy at most 5 % of the "
            "heat served, then the optimiser's front row best on the brief's priority [A]; so demand_met is true" if ok else
            f"the demand cannot be met with up to {brief_max_n(brief)} doublets at any return; least-boiler option shown; "
            "so demand_met is false")
    econ = {r["args"]["n_doublets"]: r["result"]["lcoh_EUR_MWh"] for r in out if r["name"] == "economics" and "error" not in r["result"]}
    lcoh = "; ".join(f"with {m} doublets {v} EUR/MWh" for m, v in econ.items())
    if n in econ and n + 1 in econ:
        lcoh += (f"; so the {({2: 'second', 3: 'third'}[n + 1])} doublet adds {round(econ[n + 1] - econ[n], 2)} EUR/MWh "
                 "(say this, not the n+1 LCoH, as 'what the next doublet costs')")
    return (f"{site_msg}\n{scale}\nPlan choice: {n} doublets at a {t} C return, {rule}. Boiler energy there: "
            f"{row['boiler_GWh']} GWh of {row['served_GWh']} GWh served ({row['boiler_share_pct']} %), unmet {row['unmet_GWh']} GWh [C]"
            + ("; so boiler_needed_for_energy is true" if row["boiler_GWh"] > 0.01 else "") + "."
            + (f"\nLCoH {lcoh} [C]." if lcoh else "")
            + "\nFormat: reasoning is a JSON list of 3 to 20 separate strings, one sentence per string, each with its own tag; "
              "never join sentences with ';' into one string."
            + "\n" + iteration_lines(it, out)
            + pareto_lines(out)
            + gas_lifetime(out)
            + verification_line(out)
            + "\nRejected alternatives (say each in rejected_alternatives with its number and tag, copying these sentences):\n"
            + "\n".join(f"- {x}" for x in rejected(out, n, t)))


SHORT = {"needs boiler energy": "boiler energy", "a lower return meets the rule": "higher return"}   # shorter rejection reasons
SAY = {"esp_depth_m": "ESP moved from {a:g} to {b:g} m", "n_doublets": "doublet count rose from {a:g} to {b:g}",
       "spacing_m": "producer-injector spacing went from {a:g} to {b:g} m", "doublet_spacing_m": "doublet spacing went from {a:g} to {b:g} m"}


def iteration_lines(it, out):
    """The copy-ready 'Design iterations' sentence and one sentence per repair move."""
    why = ", ".join(f"{k} {SHORT.get(r, r)}" for r, k in it["by_reason"].items())
    s = ("Design iterations (copy as one reasoning string of its own, word for word, ending with its [C] tag): "
         f"Tried {it['tried']} designs, rejected {it['rejected']}"
         + (f": {why}" if why else "") + (f"; {it['not_needed']} not needed" if it["not_needed"] else "")
         + f"; chose {it['chosen']} [C].")
    for st in (x for x in it["steps"] if x.get("move")):
        what = st["reason"].replace(": ", ", ", 1)
        verb = "repaired" if st["verdict"] == "repaired" else "still failing after a move"
        s += (f"\nViolation {verb} (copy as one reasoning string of its own, word for word, ending with its [C] tag): "
              f"{st['by'].capitalize()}'s move {'repaired' if st['verdict'] == 'repaired' else 'left'} "
              f"a violation: {what}, so the {SAY[st['key']].format(a=st['from'], b=st['to'])}, checks now {st['checks_after']} [C].")
    last = next(r for r in reversed(out) if r["name"] == "checks")
    if it["moves"]:
        s += (f"\nThe answer describes the design after the move: checks_passed is {last['result']['n_pass']}/{last['result']['n_rows']} "
              "(the last checks result, not the first).")
    if it.get("stopped"):
        st = next(x for x in it["steps"] if x["verdict"] == "stopped")
        s += (f"\nRepair stopped (copy as one reasoning string of its own, word for word, ending with its [C] tag): "
              f"The model stopped the repair at checks {st['checks_after']}; its reason is in the trace; the optimiser then chose the "
              f"design with checks {last['result']['n_pass']}/{last['result']['n_rows']} [C].")
    return s


def pareto_lines(out):
    """The front, the priority and the decision the model has to make, for the plan message."""
    o = next((r["result"] for r in out if r["name"] == "optimise_point" and "error" not in r["result"]), None)
    if not o or not o["front"]:
        return ""
    b = o["best_on_priority"]
    return (f"\nPareto front (copy as one reasoning string of its own, word for word, ending with its [C] tag): "
            f"Optimiser front of {len(o['front'])} designs from {o['n_evaluated']} tried, priority {o['priority']}, best: "
            f"{b['n']} doublets, {b['t_return_c']:g} C, ESP {b['esp_depth_m']:g} m, LCoH {b['lcoh_EUR_MWh']} EUR/MWh, "
            f"CO2 {b['co2_total_kt']} kt [C]."
            "\nThe other front rows are in the optimise_point result; name them only in trade_off, not in reasoning."
            "\ntrade_off is 'LCoH <row lcoh_EUR_MWh> EUR/MWh, CO2 <row co2_total_kt> kt, <row versus> [C]' with the chosen row's "
            "own values and its versus phrase word for word (the code did the subtraction)."
            "\nDecision: chosen_design copies one front row (n, t_return_c, esp_depth_m) and the answer's n_doublets and t_return_c "
            "follow it; the row best on the priority is the default; another row is allowed only within 5 % of the best on the "
            "priority objective. trade_off is one sentence with the chosen row's LCoH and CO2 and what it gives up against the "
            "other end of the front, each number tagged [C].")


def verification_line(out):
    """The gemini_replay verdict for the model, with the exact gemini_verification string (first sentence + any shortfall)."""
    r = next((r["result"] for r in out if r["name"] == "gemini_replay"), None)
    if r is None:
        return ""
    verdict = r.get("verdict") or f"gemini_replay returned an error: {r.get('error')}"
    keep = [s for i, s in enumerate(verdict.split(". ")) if i == 0 or "reaches only" in s]
    text = ". ".join(x.rstrip(".") for x in keep) + "."
    return ("\nGEMINI verification (gemini_replay verdict): " + verdict
            + f'\ngemini_verification is exactly this string: "{text}" Do not repeat it in reasoning; one reasoning item may say '
              f"that GEMINI's own solver re-ran the design on {r.get('n_days', 3)} days [C].")


def gas_lifetime(out):
    """One line each on the plan's gas, gas handling, CO2 and lifetime results, for the model to carry into reasoning."""
    g = next((r["result"] for r in out if r["name"] == "gas_point" and "error" not in r["result"]), None)
    l = next((r["result"] for r in out if r["name"] == "lifetime_point" and "error" not in r["result"]), None)
    s = ""
    if g:
        free = "free gas" if g["free_gas_at_intake"] or g["p_esp_intake_bar"] < g["p_bubble_log10_reading_bar"] else "no free gas"
        s += (f"\nGas (one reasoning string, its tag included): ESP at {g['esp_depth_m']:g} m: intake {g['p_esp_intake_bar']} bar, "
              f"bubble point {g['p_bubble_bar']} (log10 {g['p_bubble_log10_reading_bar']}) bar, {free}; {g['gas_Mm3_per_yr']} Mm3 gas, "
              f"{g['CH4_GWh_LHV_per_yr']} GWh CH4 per doublet-year [C, L, A].")
    it = next((r["result"] for r in out if r["name"] == "design_iterations"), {})
    e = next((r["result"] for r in out if r["name"] == "economics" and "error" not in r["result"]
              and r["args"].get("n_doublets") == it.get("n_doublets")), None)
    if g and "gas_handling" in g:
        how = {"engine": "Gas engine", "flare": "Flare", "vent": "Venting", "boiler": "Site boiler", "reinject": "Reinjection"}
        s += (f"\nGas handling and CO2 (one reasoning string, word for word, its tag included): {how[g['gas_handling']]}: "
              f"{g['handling_CO2_kt_per_yr']} kt CO2/yr, {g['handling_electricity_GWh_per_yr']} GWh electricity per doublet against its "
              f"{g['esp_GWh_per_yr']} GWh ESP load"
              + (f"; plant CO2 {e['co2_total_kt']} kt/yr, {e['co2_electricity_kt']} kt from grid electricity" if e and "co2_total_kt" in e else "")
              + " [C, D, A].")
    if l:
        s += (f"\nLifetime (say in reasoning): thermal breakthrough after {l['t_bt_mean_flow_yr']} yr at the mean running flow "
              f"{l['q_mean_running_m3h']} m3/h and {l['spacing_m']} m spacing; "
              f"doublet interference {l['interference_worst_injector_bar']} bar leaves "
              f"a SodM margin of {l['sodm_margin_after_interference_bar']} bar [C, L, A].")
    return s


def rejected(out, n, t):
    """One copy-ready sentence per alternative the plan priced and did not choose."""
    res = lambda name, **a: next((r["result"] for r in out if r["name"] == name and "error" not in r["result"]
                                  and all(r["args"].get(k) == v for k, v in a.items())), None)
    lines = []
    fewer = res("return_sweep", n_doublets=n - 1) if n > 1 else None
    if fewer:
        b = fewer["best_return_c"]; r = fewer["by_return_C"][str(b)]
        lines.append(f"Fewer doublets: {n - 1} doublet{'s' if n > 2 else ''} at {'their' if n > 2 else 'its'} best {b} C return "
                     f"leave{'' if n > 2 else 's'} {r['unmet_GWh']} GWh unmet, "
                     f"boiler share {r['boiler_share_pct']} % and peak margin {r['peak_margin_pct']} % [C].")
    delta = res("economics_delta")
    if n < 3 and delta:
        lines.append(f"A {({2: 'second', 3: 'third'})[n + 1]} doublet adds {delta['delta_lcoh_EUR_MWh']} EUR/MWh to the LCoH and "
                     f"{delta['delta_capex_MEUR']} MEUR of CAPEX when {n} already meet the heat [C].")
    lay = res("layout_compare")
    if lay:
        a, b = lay["A"], lay["B"]
        lines.append(f"The boiler-lift layout without heat pump costs {a['lcoh_EUR_MWh']} against {b['lcoh_EUR_MWh']} EUR/MWh, "
                     f"burns {a['gas_GWh']} GWh gas and emits {a['co2_kt']} kt CO2 [C].")
    st = res("storage_point")
    if st:
        lines.append(f"A storage tank instead of the {st['backup_boiler_MW']:g} MW backup boiler: "
                     f"a {st['outage_days']}-day winter outage of one doublet needs {st['tank_for_outage_MWh']:.0f} MWh, "
                     f"{st['tanks_needed']} tanks, {st['tank_cost_MEUR']} MEUR against {st['backup_boiler_MEUR']} MEUR [C, L, A].")
    sw = res("return_sweep", n_doublets=n)
    low = [x for x in tools.SWEEP_C if x < t] if sw else []
    if low:
        r = sw["by_return_C"][str(low[-1])]
        lines.append(f"A lower {low[-1]} C return needs {r['boiler_GWh']} GWh of boiler energy ({r['boiler_share_pct']} % of the heat) [C].")
    return lines
