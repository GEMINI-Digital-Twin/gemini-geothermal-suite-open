"""Sourced economics of one design: CAPEX by item, annual cost, LCoH (heating) and LCoC (cooling) over the 2027 year.

Why: the agent can say how many doublets meet the heat, but a jury asks what the next doublet costs. This module puts a
price on the dispatch of geo.year with tagged inputs only, heating and cooling kept apart so neither hides in the other.
Chillers 119 EUR/kW [L, HRE4 D3.2] and absorption 450 EUR/kW [A/TBC] come from the prep cost table
(../src/geohack/economics/data/cost_table.csv); the cooling tower 100 EUR/kW is [A] (no sourced value: the table marks it
TBC). Fixed O&M 5 % of CAPEX is the PBL doublet range applied to every item [A for surface equipment]. Absorption drive
heat is brine the heating side does not use, so it is free [A]. No subsidy, tax, network or re-drill cost [A].
"""
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # run as python geo/cost.py

from geo import year  # noqa: E402

R = 0.052                       # discount rate, real [L, PBL SDE++ 2026 WACC geothermal]
LIFE_DOUBLET, LIFE_SURFACE = 30, 20   # years [L, PBL] / [A]
FOM = 0.05                      # fixed O&M per year, share of CAPEX [C, PBL 118-124 EUR/kW/yr = 4.6-6.9 %]
DOUBLET_MEUR = 9.3              # per doublet, top at 2 450 m [C, ThermoGIS well-cost curve, research/03]
HP_EUR_KW = 950.0               # heat pump per kW heat out [L, DEA catalogue sheet 40, 10 MW, EUR2020]
BOILER_EUR_KW = 58.0            # gas boiler, 30 MW for 1.6-1.9 MEUR, midpoint [C, research/04]
CHILLER_EUR_KW = 119.0          # water-cooled electric chiller > 400 kW [L, HRE4 D3.2 via cost_table.csv]
TOWER_EUR_KW = 100.0            # wet cooling tower per kW heat rejected [A]
ABSORPTION_EUR_KW = 450.0       # single-effect LiBr per kW cold [A/TBC, cost_table.csv midpoint 314 EUR/kW-600 USD/kW]
P_EL = 182.4                    # EUR/MWh electricity [L, Eurostat NL 2026-S1 band ID, ex VAT]
P_GAS = 83.9                    # EUR/MWh gas, GCV [L, Eurostat NL 2026-S1 band I4, ex VAT]
BOILER_EFF = 0.9                # heat out per gas in, GCV basis [A]
CO2_T_MWH = 56.2 * 3.6 / 1000 / 1.11   # t/MWh gas GCV: 56.2 kg/GJ LHV [D, RVO 2026] / 1.11 GCV/LHV [A] = 0.182
P_CO2 = 58.64                   # EUR/t, ETS2 from 2028 [L, PBL 2026]


def crf(r, n):
    return r * (1 + r) ** n / ((1 + r) ** n - 1)


@lru_cache
def economics(n_doublets, t_return_c, peak_heat_MW=None, peak_cold_MW=None, doublet_MEUR=DOUBLET_MEUR, depth_m=year.DEPTH_M, heat_pump=True):
    """CAPEX MEUR by item, annual MEUR by cost type, LCoH and LCoC in EUR/MWh for n doublets at a t_return_c return [C].

    doublet_MEUR: research/03 (ThermoGIS curve) gives 9.3 MEUR, research/04 23.6 to 37.2 MEUR per doublet [TBC which]; pass it to see the spread.
    depth_m changes the dispatch only; the doublet price stays doublet_MEUR at every depth [A, no sourced depth curve].
    heat_pump False prices layout A (boiler lift, no heat pump): the heat-pump item is then 0 and gas carries the lift."""
    d = year.heating_year(int(n_doublets), float(t_return_c), peak_heat_MW=peak_heat_MW, depth_m=float(depth_m), heat_pump=bool(heat_pump))
    c, tot = year.cooling_year(d.surplus, peak_cold_MW=peak_cold_MW)
    gwh = lambda s: float(s.sum() * 24 / 1000)
    rejected = c.cold + c.electric / year.COP_ELECTRIC + c.absorption / year.COP_ABSORPTION   # tower duty, MW
    capex = {"doublets": n_doublets * doublet_MEUR, "heat_pump": d.hp.max() * HP_EUR_KW / 1000,
             "backup_boiler": year.BACKUP_BOILER_MW * BOILER_EUR_KW / 1000,
             "electric_chillers": c.electric.max() * CHILLER_EUR_KW / 1000, "cooling_tower": rejected.max() * TOWER_EUR_KW / 1000,
             "absorption_chillers": c.absorption.max() * ABSORPTION_EUR_KW / 1000}
    life = {k: LIFE_DOUBLET if k == "doublets" else LIFE_SURFACE for k in capex}
    heat_items, cold_items = ("doublets", "heat_pump", "backup_boiler"), ("electric_chillers", "cooling_tower", "absorption_chillers")
    el_heat = gwh(d.esp) + gwh(d.el_hp) + gwh(year.injection_pump_MW(d))
    el_cold = tot["el_chillers"] + tot["el_aux"]
    gas = gwh(d.boiler) / BOILER_EFF
    co2_kt = gas * CO2_T_MWH                                     # GWh x t/MWh = kt

    def annual(items, el, gas_gwh, co2):
        return {"capital": sum(capex[k] * crf(R, life[k]) for k in items), "fom": sum(capex[k] * FOM for k in items),
                "electricity": el * P_EL / 1000, "gas": gas_gwh * P_GAS / 1000, "co2": co2 * P_CO2 / 1000}
    heat_cost, cold_cost = annual(heat_items, el_heat, gas, co2_kt), annual(cold_items, el_cold, 0.0, 0.0)
    heat_GWh, cold_GWh = gwh(d.demand - d.unmet), tot["cold"]
    return {"n_doublets": int(n_doublets), "t_return_c": float(t_return_c), "depth_m": float(depth_m),
            "layout": "B heat-pump lift" if heat_pump else "A boiler lift",
            "capex_MEUR": {**capex, "total": sum(capex.values())},
            "annual_cost_MEUR": {"heating": heat_cost, "cooling": cold_cost,
                                 "total": sum(heat_cost.values()) + sum(cold_cost.values())},
            "heat_served_GWh": heat_GWh, "cold_served_GWh": cold_GWh,
            "lcoh_EUR_MWh": sum(heat_cost.values()) / heat_GWh * 1000,
            "lcoc_EUR_MWh": sum(cold_cost.values()) / cold_GWh * 1000 if cold_GWh > 0 else float("nan"),
            "electricity_GWh": el_heat + el_cold, "gas_GWh": gas, "co2_kt": co2_kt, "tag": "[C]",
            "basis": {"discount_rate": f"{R} real [L, PBL 2026]", "life_yr": "doublets 30 [L, PBL], surface 20 [A]",
                      "fom": f"{FOM} of CAPEX per yr [C, PBL 4.6-6.9 %]", "doublet_MEUR": f"{doublet_MEUR} at every depth [C, ThermoGIS 9.3 at 2 450 m; research/04 says 23.6-37.2, TBC; A off 2 500 m]",
                      "heat_pump_EUR_kW": f"{HP_EUR_KW} [L, DEA]", "boiler_EUR_kW": f"{BOILER_EUR_KW} [C, research/04]",
                      "chiller_EUR_kW": f"{CHILLER_EUR_KW} [L, HRE4]", "tower_EUR_kW": f"{TOWER_EUR_KW} [A]",
                      "absorption_EUR_kW": f"{ABSORPTION_EUR_KW} [A/TBC]", "electricity_EUR_MWh": f"{P_EL} [L, Eurostat ID]",
                      "gas_EUR_MWh": f"{P_GAS} GCV [L, Eurostat], boiler eff {BOILER_EFF} [A]",
                      "co2": f"{CO2_T_MWH:.3f} t/MWh gas [D, RVO], {P_CO2} EUR/t [L, ETS2]"}}


if __name__ == "__main__":
    rows = {n: economics(n, 60.0, 30.0, 10.0) for n in (1, 2, 3)}
    print("n  CAPEX MEUR  heat GWh  LCoH EUR/MWh  LCoC EUR/MWh  el GWh  gas GWh  CO2 kt   (60 C return, 30/10 MW) [C]")
    for n, e in rows.items():
        print(f"{n}  {e['capex_MEUR']['total']:10.2f}  {e['heat_served_GWh']:8.2f}  {e['lcoh_EUR_MWh']:12.2f}  "
              f"{e['lcoc_EUR_MWh']:12.2f}  {e['electricity_GWh']:6.2f}  {e['gas_GWh']:7.2f}  {e['co2_kt']:6.2f}")
    print(f"third doublet costs {rows[3]['lcoh_EUR_MWh'] - rows[2]['lcoh_EUR_MWh']:+.2f} EUR/MWh of heat [C]")
