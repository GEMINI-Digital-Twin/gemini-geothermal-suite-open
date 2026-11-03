"""A steel heat-storage tank priced against the 16 MW backup boiler: what a tank must hold to replace it, and what it costs.

Two duties a tank could take over: (a) the peak with every doublet on (zero when the plan rule holds), (b) one doublet out
for OUTAGE_DAYS in winter (the boiler's real job, security of supply). Tank prices and sizes from research/04 lines 24-27
[L, DEA technology data for energy storage]. Daily data hide the hourly peak, so (a) is a lower bound [A].
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # run as python geo/storage.py

from geo import cost, year  # noqa: E402
from geo.common import DEPTH_M  # noqa: E402

TANK_EUR_MWH = 3000.0       # steel tank, EUR2015, range 2 200-8 000 [L, DEA technology data: energy storage]
TANK_UNIT_MWH = 175.0       # DEA standard unit, energy [L, DEA-S]
TANK_UNIT_MW = 2.9          # DEA standard unit, discharge power [L, DEA-S]
TANK_LOSS_PER_DAY = 0.002   # share of content lost per day [L, DEA-S]
OUTAGE_DAYS = 7             # unplanned winter outage of one doublet [A]


def _longest_run(mask, values):
    """Longest run of consecutive True days in mask and the sum of values over that run."""
    best, cur, best_sum, cur_sum = 0, 0, 0.0, 0.0
    for m, v in zip(mask, values):
        cur, cur_sum = (cur + 1, cur_sum + v) if m else (0, 0.0)
        if cur > best or (cur == best and cur_sum > best_sum):
            best, best_sum = cur, cur_sum
    return best, best_sum


def storage_case(n, t_return_c, peak_heat_MW=None, depth_m=DEPTH_M, outage_days=OUTAGE_DAYS):
    """Tank for the all-doublets peak and for an N-1 winter outage, its cost, and the boiler it competes with [C, L, A]."""
    d = year.heating_year(int(n), float(t_return_c), peak_heat_MW=peak_heat_MW, depth_m=float(depth_m))
    full = d[[f"avail_{i}" for i in range(int(n))]].all(axis=1)
    short = (d.boiler_peak + d.unmet).where(full, 0.0)                     # MW per day the doublets cannot give, all on
    days, mw_days = _longest_run(short > 0.01, short)
    tank_peak = mw_days * 24
    cap = year.table(float(t_return_c), float(depth_m)).out_max            # MW per doublet at 300 m3/h [C]
    deficit = float((d.demand - (n - 1) * cap).clip(lower=0).max())        # N-1 on the coldest day [C]
    tank_out = deficit * 24 * outage_days
    tanks = max(math.ceil(tank_out / TANK_UNIT_MWH), math.ceil(deficit / TANK_UNIT_MW)) if tank_out > 0 else 0
    tank_meur = tank_out * TANK_EUR_MWH / 1e6
    boiler_meur = year.BACKUP_BOILER_MW * cost.BOILER_EUR_KW / 1000
    keep = "the boiler is kept" if tank_meur > boiler_meur else "a tank is cheaper than the boiler"
    verdict = (f"a tank covering the peak with all doublets on needs {tank_peak:.0f} MWh; covering a {outage_days}-day N-1 winter outage "
               f"needs {tank_out:.0f} MWh = {tanks} tanks for {tank_meur:.2f} MEUR against {boiler_meur:.2f} MEUR for the "
               f"{year.BACKUP_BOILER_MW:.0f} MW boiler, so {keep} [C, L, A]")
    return {"n_doublets": int(n), "t_return_c": float(t_return_c), "depth_m": float(depth_m),
            "all_on_deficit_GWh": float(short.sum() * 24 / 1000), "all_on_deficit_max_MW": float(short.max()),
            "all_on_longest_run_days": days, "tank_for_peak_MWh": tank_peak,
            "capacity_per_doublet_MW": cap, "n_minus_1_deficit_MW": deficit, "outage_days": outage_days,
            "tank_for_outage_MWh": tank_out, "tanks_needed": tanks, "tank_cost_MEUR": tank_meur,
            "tank_loss_over_outage_pct": 100 * TANK_LOSS_PER_DAY * outage_days, "backup_boiler_MW": year.BACKUP_BOILER_MW,
            "backup_boiler_MEUR": boiler_meur, "verdict": verdict,
            "basis": (f"tank {TANK_EUR_MWH:.0f} EUR/MWh (2 200-8 000), unit {TANK_UNIT_MWH:.0f} MWh / {TANK_UNIT_MW} MW, loss "
                      f"{100 * TANK_LOSS_PER_DAY:.1f} %/day [L, DEA]; units = max(energy, power) count [C]; boiler "
                      f"{cost.BOILER_EUR_KW:.0f} EUR/kW [C, research/04]; {outage_days}-day outage [A]; daily profile hides the "
                      "hourly peak, so the tank for the peak is a lower bound, and stored brine-temperature heat still needs the lift [A]"),
            "tag": "[C, L, A]"}


if __name__ == "__main__":
    s = storage_case(2, 60.0, 30.0)
    for k, v in s.items():
        print(f"{k}: {round(v, 2) if isinstance(v, float) else v}")
