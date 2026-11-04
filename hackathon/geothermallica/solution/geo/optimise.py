"""Design optimiser: doublet count, network return and pump depth for the lowest cost of heat and the lowest CO2.
Objectives come from geo.cost.economics, feasibility from the 17 checks in geo.year and the rule in geo.rule.
Method: a coarse grid, then a pattern search that halves its steps around the best point, run for three weightings
of the two objectives; the Pareto front is every feasible design no other design beats on both. Parameter choices are
in the inline comments. Returns a dict with the front, the best design per objective, the count evaluated and a basis."""
import time

from geo import cost, lifetime, rule, year
from geo.common import DEPTH_M
from geo.well import ESP_DEPTH_M


def gwh(series):
    """GWh over the year from a daily MW series."""
    return float(series.sum() * 24 / 1000)


N_RANGE = (1, 2, 3)                              # doublets allowed by the brief
T_RANGE_C = (50.0, 70.0)                         # network return bounds, C; the range where the heat pump reaches 100 C
ESP_RANGE_M = (300.0, 1250.0)                    # pump setting depth bounds, m; the same limits as the design tools
T_STEP_C = 4.0                                   # coarse grid step for the return, C; four halvings end at 0.25 C
ESP_STEP_M = 250.0                               # coarse grid step for the pump depth, m; our choice
HALVINGS = 4                                     # times the pattern search halves both steps; our choice
WEIGHTS = ((1.0, 0.0), (0.5, 0.5), (0.0, 1.0))   # (cost of heat, CO2) weightings that seed the front; our choice
FRONT_MAX = 8                                    # rows of the front reported to the agent


def grid(lo, hi, step):
    """lo, lo + step, ... up to hi, with hi itself as the last value."""
    xs = [lo + i * step for i in range(int((hi - lo) / step) + 1)]
    return xs if xs[-1] == hi else xs + [hi]


def evaluate(n, t, esp, ph, pc, depth):
    """One design: objectives, the year row the rule reads, the failed checks and the breakthrough time."""
    d = year.heating_year(n, t, peak_heat_MW=ph, depth_m=depth, esp_depth_m=esp)
    cap = n * year.table(t, depth, esp_depth_m=esp).out_max
    row = {"unmet_GWh": gwh(d.unmet), "boiler_GWh": gwh(d.boiler), "served_GWh": gwh(d.demand - d.unmet),
           "boiler_share_pct": 100 * gwh(d.boiler) / max(gwh(d.demand - d.unmet), 1e-9),
           "peak_margin_pct": 100 * (cap / d.demand.max() - 1)}
    checks = year.checks(n, t, ph, pc, depth_m=depth, esp_depth_m=esp)
    fails = [r["name"] for r in checks if r["status"].startswith("FAIL")]
    fails += [f"rule: {why}" for why, _, _ in rule.rule_failures(row)]
    e = cost.economics(n, t, ph, pc, depth_m=depth, esp_depth_m=esp)
    q_mean = float(d.q_m3h[d.doublets_on > 0].mean())
    return {"n": n, "t_return_c": t, "esp_depth_m": esp, "lcoh_EUR_MWh": e["lcoh_EUR_MWh"],
            "co2_total_kt": e["co2_total_kt"], "t_bt_yr": lifetime.t_bt_yr(q_mean), "feasible": not fails, "fails": fails}


class Search:
    """Evaluations cached by rounded inputs, with the weighted objective and the pattern search."""

    def __init__(self, ph, pc, depth, esp_start):
        self.ph, self.pc, self.depth, self.esp_start, self.seen = ph, pc, depth, esp_start, {}

    def point(self, n, t, esp):
        key = (n, round(t, 3), round(esp, 1))
        if key not in self.seen:
            self.seen[key] = evaluate(n, key[1], key[2], self.ph, self.pc, self.depth)
        return self.seen[key]

    def scale(self):
        """(min, range) of each objective over the feasible designs seen, for the weighted objective."""
        ok = [p for p in self.seen.values() if p["feasible"]]
        out = []
        for k in ("lcoh_EUR_MWh", "co2_total_kt"):
            lo, hi = min(p[k] for p in ok), max(p[k] for p in ok)
            out.append((lo, hi - lo if hi > lo else 1.0))
        return out

    def key(self, p, w, scale):
        """Sort key: infeasible last, then the weighted normalised objective, ties to the pump depth nearest the start."""
        if not p["feasible"]:
            return (1, 0.0, 0.0)
        j = sum(wi * (p[k] - lo) / rng for wi, k, (lo, rng) in zip(w, ("lcoh_EUR_MWh", "co2_total_kt"), scale))
        return (0, round(j, 6), abs(p["esp_depth_m"] - self.esp_start))

    def pattern(self, n, w, start):
        """Halve the steps HALVINGS times; at each level move to a better neighbour until none is better."""
        best, scale, dt, de = start, self.scale(), T_STEP_C, ESP_STEP_M
        for _ in range(HALVINGS):
            dt, de = dt / 2, de / 2
            for _ in range(20):
                nb = [(best["t_return_c"] + a, best["esp_depth_m"] + b) for a, b in ((dt, 0), (-dt, 0), (0, de), (0, -de))]
                nb = [self.point(n, min(max(t, T_RANGE_C[0]), T_RANGE_C[1]), min(max(e, ESP_RANGE_M[0]), ESP_RANGE_M[1]))
                      for t, e in nb]
                cand = min(nb, key=lambda p: self.key(p, w, scale))
                if self.key(cand, w, scale) >= self.key(best, w, scale):
                    break
                best = cand
        return best


def beats(a, b):
    """True when design a is at least as good as b on both objectives and better on one."""
    return (a["lcoh_EUR_MWh"] <= b["lcoh_EUR_MWh"] and a["co2_total_kt"] <= b["co2_total_kt"]
            and (a["lcoh_EUR_MWh"] < b["lcoh_EUR_MWh"] or a["co2_total_kt"] < b["co2_total_kt"]))


def front(points):
    """The feasible designs no other feasible design beats on both objectives, cheapest first."""
    ok = [p for p in points if p["feasible"]]
    keep = [p for p in ok if not any(beats(q, p) for q in ok)]
    seen, out = set(), []
    for p in sorted(keep, key=lambda p: (p["lcoh_EUR_MWh"], p["co2_total_kt"])):
        k = (round(p["lcoh_EUR_MWh"], 2), round(p["co2_total_kt"], 3))
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def versus(p, other):
    """One phrase with the cost and CO2 differences of row p against the other end of the front."""
    if p is other:
        return "the only design on the front"
    dl, dc = p["lcoh_EUR_MWh"] - other["lcoh_EUR_MWh"], p["co2_total_kt"] - other["co2_total_kt"]
    return (f"{abs(dl):.2f} EUR/MWh {'cheaper' if dl <= 0 else 'dearer'} and {abs(dc):.3f} kt CO2 "
            f"{'less' if dc <= 0 else 'more'} than {other['n']} doublets at {other['t_return_c']:.2f} C")


def optimise(peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M, esp_start_m=ESP_DEPTH_M, n_max=3):
    """The front and the best design per objective for the brief's peaks, depth and starting pump depth."""
    t0 = time.time()
    s = Search(peak_heat_MW, peak_cold_MW, float(depth_m), float(esp_start_m))
    esps = sorted(set(grid(*ESP_RANGE_M, ESP_STEP_M) + [float(esp_start_m)]))
    for n in N_RANGE[:n_max]:
        for t in grid(*T_RANGE_C, T_STEP_C):
            for esp in esps:
                s.point(n, t, esp)
    if any(p["feasible"] for p in s.seen.values()):
        for w in WEIGHTS:
            for n in N_RANGE[:n_max]:
                scale = s.scale()
                start = min((p for p in s.seen.values() if p["n"] == n), key=lambda p: s.key(p, w, scale))
                if start["feasible"]:
                    s.pattern(n, w, start)
    fr = front(s.seen.values())
    def label(i):
        return "best cost of heat" if i == 0 else "best CO2" if i == len(fr) - 1 else "on the front"

    rows = [{**p, "verdict": label(i), "versus": versus(p, fr[-1] if i == 0 else fr[0])} for i, p in enumerate(fr)]
    def best(k):
        return min(rows, key=lambda p: p[k]) if rows else None

    secs = round(time.time() - t0, 1)
    return {"front": rows[:FRONT_MAX], "best_lcoh": best("lcoh_EUR_MWh"), "best_co2": best("co2_total_kt"),
            "n_evaluated": len(s.seen), "n_feasible": sum(p["feasible"] for p in s.seen.values()), "seconds": secs,
            "basis": (f"coarse grid n {N_RANGE[0]}-{N_RANGE[:n_max][-1]}, return {T_RANGE_C[0]:g}-{T_RANGE_C[1]:g} C "
                      f"step {T_STEP_C:g}, pump depth {ESP_RANGE_M[0]:g}-{ESP_RANGE_M[1]:g} m step {ESP_STEP_M:g} plus "
                      f"the start {esp_start_m:g} m; pattern search with {HALVINGS} halvings for weights {WEIGHTS} on "
                      f"min-max normalised objectives [A, our choice]; feasible = 17 checks pass and the doublet rule "
                      f"[C]; {len(s.seen)} designs in {secs} s")}


if __name__ == "__main__":
    r = optimise()
    print(f"{r['n_evaluated']} designs, {r['n_feasible']} feasible, {r['seconds']} s")
    for p in r["front"]:
        print(f"n {p['n']}  return {p['t_return_c']:5.2f} C  ESP {p['esp_depth_m']:6.1f} m  LCoH {p['lcoh_EUR_MWh']:6.2f}  "
              f"CO2 {p['co2_total_kt']:6.3f} kt  t_bt {p['t_bt_yr']:5.1f} yr  {p['verdict']}")
