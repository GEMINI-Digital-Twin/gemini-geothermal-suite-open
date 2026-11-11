"""A steel hot-water storage tank priced against the 16 MW backup boiler, sized for the peak and for a winter outage of one doublet.

Tank data: Danish Energy Agency (DEA), Technology Data: Energy storage, https://ens.dk/media/6448/download
Parameter sources are in the inline comments.
storage_case() returns a dict: heat deficits (MW, GWh), tank size (MWh), tanks needed, tank and boiler cost (MEUR, million
euros), and "verdict" and "basis" strings. Run: python geo/storage.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geo import cost, year  # noqa: E402
from geo.common import DEPTH_M  # noqa: E402
from geo.well import ESP_DEPTH_M  # noqa: E402

TANK_EUR_MWH = 3000.0       # steel tank cost, EUR per MWh stored (2015 euros, range 2 200-8 000); source: DEA energy storage
TANK_UNIT_MWH = 175.0       # heat stored per standard tank, MWh; source: DEA energy storage
TANK_UNIT_MW = 2.9          # discharge power per standard tank, MW; source: DEA energy storage
TANK_LOSS_PER_DAY = 0.002   # share of the stored heat lost per day; source: DEA energy storage
OUTAGE_DAYS = 7             # unplanned winter outage of one doublet (N-1), days; assumed, no source


def _longest_run(mask, values):
    """Longest run of consecutive True days in mask and the sum of values over that run."""
    best, cur, best_sum, cur_sum = 0, 0, 0.0, 0.0
    for m, v in zip(mask, values):
        cur, cur_sum = (cur + 1, cur_sum + v) if m else (0, 0.0)
        if cur > best or (cur == best and cur_sum > best_sum):
            best, best_sum = cur, cur_sum
    return best, best_sum


def storage_case(n, t_return_c, peak_heat_MW=None, depth_m=DEPTH_M, outage_days=OUTAGE_DAYS, esp_depth_m=ESP_DEPTH_M):
    """Dict of the tank for the all-doublets peak and for an N-1 winter outage, its cost, and the boiler it competes with."""
    d = year.heating_year(int(n), float(t_return_c), peak_heat_MW=peak_heat_MW, depth_m=float(depth_m), esp_depth_m=float(esp_depth_m))
    full = d[[f"avail_{i}" for i in range(int(n))]].all(axis=1)
    short = (d.boiler_peak + d.unmet).where(full, 0.0)                     # MW per day the doublets cannot give with all of them on
    days, mw_days = _longest_run(short > 0.01, short)
    tank_peak = mw_days * 24
    cap = year.table(float(t_return_c), float(depth_m), esp_depth_m=float(esp_depth_m)).out_max   # MW per doublet at 300 m3/h
    deficit = float((d.demand - (n - 1) * cap).clip(lower=0).max())        # MW short with one doublet out on the coldest day
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
                      f"{cost.BOILER_EUR_KW:.0f} EUR/kW [C, DEA]; {outage_days}-day outage [A]; daily profile hides the "
                      "hourly peak, so the tank for the peak is a lower bound, and stored brine-temperature heat still needs the lift [A]"),
            "tag": "[C, L, A]"}


if __name__ == "__main__":
    s = storage_case(2, 60.0, 30.0)
    for k, v in s.items():
        print(f"{k}: {round(v, 2) if isinstance(v, float) else v}")
