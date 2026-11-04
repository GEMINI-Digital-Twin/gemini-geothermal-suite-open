"""The code plan of the design agent: brief parsing, return sweeps, checks, repair moves, alternatives and their sentences."""
import math
import re

import AI02_tools as tools
import AI04_check as checker
from geo import lifetime
from geo.common import Q_MAX_M3H
from geo.well import ESP_DEPTH_M

brief_peak = checker.brief_peak


brief_site = checker.brief_site
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


# repair move per failing check row: (input it changes, unit, how)
MOVES = {"free gas at ESP intake": ("esp_depth_m", "m", "+300 m, cap 1250 m"),
         "SodM injection pressure": ("n_doublets", "doublets", "+1, cap the brief's maximum"),
         "capacity covers the peak": ("n_doublets", "doublets", "+1, cap the brief's maximum"),
         "thermal breakthrough": ("spacing_m", "m", "spacing for 30 yr at 300 m3/h, rounded up to 50 m"),
         "doublet interference": ("doublet_spacing_m", "m", "x 1.5, cap 5000 m")}
START = {"esp_depth_m": ESP_DEPTH_M, "spacing_m": lifetime.SPACING_M}   # tool defaults when the brief gives no value


def moved(key, now, max_n):
    """The new value of key after one move from now."""
    if key == "esp_depth_m":
        return min(now + 300.0, 1250.0)
    if key == "n_doublets":
        return min(now + 1, max_n)
    if key == "spacing_m":
        return max(now, 50.0 * math.ceil(lifetime.spacing_for_yr(30, Q_MAX_M3H) / 50.0))
    return min(now * 1.5, 5000.0)


def failing(checks_result):
    """[(row name without number and tag, value text, limit text)] for the FAIL rows of a checks result."""
    rows = []
    for k, v in checks_result.items():
        if isinstance(v, str) and "-> FAIL" in v:
            value, rest = v.split(" (limit ", 1)
            rows.append((re.sub(r"^\d+ |\s*\[[^\]]*\]$", "", k), value, rest.rsplit(") -> ", 1)[0]))
    return rows


FIRST_NUM = re.compile(r"-?\d+(?:\.\d+)?\s*(?:bar|yr|GWh|MW|m3/h|K|m)\b")


def short(value, limit):
    """'45.2 bar against limit 62.5 bar' from a check row's value and limit text (the full row stays in the checks result)."""
    v, lim = FIRST_NUM.search(value), FIRST_NUM.search(limit)
    return f"{v.group(0)} against limit {lim.group(0)}" if v and lim else f"{value} (limit {limit})"


def repair(design, life, out, max_n):
    """Up to 2 moves on the first FAIL row in MOVES; design and life change in place so later tools see the moved value."""
    steps = []
    for _ in range(2):
        chk = next(r["result"] for r in reversed(out) if r["name"] == "checks")
        hit = next(((row, value, limit) for row, value, limit in failing(chk) if row in MOVES), None)
        if hit is None:
            break
        row, value, limit = hit
        key, unit, _ = MOVES[row]
        where = life if key in ("spacing_m", "doublet_spacing_m") else design
        now = where.get(key, START.get(key, life.get("spacing_m", lifetime.SPACING_M)))
        new = moved(key, now, max_n)
        if new == now:   # at its cap: nothing left to move
            break
        where[key] = new
        res = call("checks", dict(design))
        out.append({"name": "checks", "args": dict(design), "result": res})
        esp = design.get("esp_depth_m", ESP_DEPTH_M)
        steps.append({"candidate": name(design["n_doublets"], design["t_return_c"]) + f", ESP {esp:g} m"
                      + "".join(f", {k} {v:g} m" for k, v in life.items()),
                      "n_doublets": design["n_doublets"], "t_return_c": design["t_return_c"],
                      "verdict": "repaired" if res.get("n_fail", 1) == 0 else "still failing",
                      "reason": f"{row}: {short(value, limit)}", "move": f"{key} {now:g} -> {new:g} {unit} [A, MOVES]",
                      "key": key, "from": now, "to": new, "checks_after": f"{res.get('n_pass')}/{res.get('n_rows')}", "tag": "[C]"})
    return steps


def plan(brief):
    """The code plan's tool calls: site, demand, sweeps, checks, repair moves, years, economics, alternatives, trace."""
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
    moves = repair(design, life, out, max_n)
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
    trace = iterations(sweeps, chosen)
    by = {}
    for st in trace:
        if st["verdict"] == "rejected":
            by[st["reason"]] = by.get(st["reason"], 0) + 1
    out.append({"name": "design_iterations", "args": {},
                "result": {"tried": len(trace), "rejected": sum(by.values()), "not_needed": sum(st["verdict"] == "not needed" for st in trace),
                           "by_reason": by, "moves": len(moves), "chosen": name(n, t), "n_doublets": n, "t_return_c": t,
                           "steps": trace + moves, "tag": "[C]"}})

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
    row = next(r["result"] for r in out if r["name"] == "return_sweep" and r["result"].get("n_doublets") == n)["by_return_C"][str(t)]
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
            "heat served [A]; so demand_met is true" if ok else
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
            + "\nFormat: reasoning is a JSON list of 3 to 12 separate strings, one sentence per string, each with its own tag; "
              "never join sentences with ';' into one string."
            + "\n" + iteration_lines(it, out)
            + gas_lifetime(out)
            + "\nRejected alternatives (say each in rejected_alternatives with its number and tag, copying these sentences):\n"
            + "\n".join(f"- {x}" for x in rejected(out, n, t)))


SHORT = {"unmet heat": "unmet heat", "peak margin": "peak margin", "boiler share": "boiler share",
         "needs boiler energy": "boiler energy", "a lower return meets the rule": "higher return"}
SAY = {"esp_depth_m": "ESP moved from {a:g} to {b:g} m", "n_doublets": "doublet count rose from {a:g} to {b:g}",
       "spacing_m": "producer-injector spacing went from {a:g} to {b:g} m", "doublet_spacing_m": "doublet spacing went from {a:g} to {b:g} m"}
def iteration_lines(it, out):
    """The copy-ready 'Design iterations' sentence and one sentence per repair move."""
    why = ", ".join(f"{k} {SHORT[r]}" for r, k in it["by_reason"].items())
    s = ("Design iterations (copy as one reasoning string of its own, word for word, ending with its [C] tag): "
         f"Tried {it['tried']} designs, rejected {it['rejected']}"
         + (f": {why}" if why else "") + (f"; {it['not_needed']} not needed" if it["not_needed"] else "")
         + f"; chose {it['chosen']} [C].")
    for st in (x for x in it["steps"] if x.get("move")):
        what = st["reason"].replace(": ", ", ", 1)
        verb = "repaired" if st["verdict"] == "repaired" else "still failing after a move"
        s += (f"\nViolation {verb} (copy as one reasoning string of its own, word for word, ending with its [C] tag): "
              f"Plan {'repaired' if st['verdict'] == 'repaired' else 'tried to repair'} "
              f"a violation: {what}, so the {SAY[st['key']].format(a=st['from'], b=st['to'])}, checks now {st['checks_after']} [C].")
    last = next(r for r in reversed(out) if r["name"] == "checks")
    if it["moves"]:
        s += (f"\nThe answer describes the design after the move: checks_passed is {last['result']['n_pass']}/{last['result']['n_rows']} "
              "(the last checks result, not the first).")
    return s


def gas_lifetime(out):
    """One line each on the plan's gas and lifetime results, for the model to carry into reasoning."""
    g = next((r["result"] for r in out if r["name"] == "gas_point" and "error" not in r["result"]), None)
    l = next((r["result"] for r in out if r["name"] == "lifetime_point" and "error" not in r["result"]), None)
    s = ""
    if g:
        free = "free gas" if g["free_gas_at_intake"] or g["p_esp_intake_bar"] < g["p_bubble_log10_reading_bar"] else "no free gas"
        s += (f"\nGas (one reasoning string, its tag included): ESP at {g['esp_depth_m']:g} m: intake {g['p_esp_intake_bar']} bar, "
              f"bubble point {g['p_bubble_bar']} (log10 {g['p_bubble_log10_reading_bar']}) bar, {free}; {g['gas_Mm3_per_yr']} Mm3 gas, "
              f"{g['CH4_GWh_LHV_per_yr']} GWh CH4 per doublet-year [C, L, A].")
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
