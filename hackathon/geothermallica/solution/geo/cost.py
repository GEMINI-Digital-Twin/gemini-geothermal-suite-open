"""Economics of one design: CAPEX (capital expenditure) by item, annual cost, LCoH and LCoC (levelised cost of heat and of cold) in 2027.

Well costs follow the TNO ThermoGIS cost model, https://pythermogis-15909e.ci.tno.nl/theory/economicmodel/cost_model/ .
Parameter sources are in the inline comments.
economics() returns a dict: the design inputs, CAPEX by item, annual cost of heating and cooling by item, heat and cold
served, LCoH and LCoC, electricity, gas and CO2 (boiler gas, grid electricity, associated gas, total), and a "basis" dict of sources.
"""
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geo import gas as assoc, year  # noqa: E402
from geo.common import THICKNESS_M  # noqa: E402

# PBL = Netherlands Environmental Assessment Agency; SDE++ = the Dutch renewable-energy subsidy scheme. "PBL SDE++ 2026" below is
# PBL's final advice on the SDE++ 2026 base amounts, https://www.pbl.nl/downloads/pbl-2026-eindadvies-sde-plus-plus-2026-5698-1pdf
# discount rate, real (after inflation); source: PBL SDE++ 2026, weighted average cost of capital (WACC) for geothermal
R = 0.052
LIFE_DOUBLET, LIFE_SURFACE = 30, 20   # economic life, years; doublet: PBL SDE++ 2026; surface plant: assumed, no source
FOM = 0.05                      # fixed operation and maintenance (O&M) cost per year, share of CAPEX; source: PBL SDE++ 2026 (4.6-6.9 %)
# ThermoGIS well cost (TNO's geothermal resource tool), link in the module docstring:
# CAPEX = 2 x wcscale x (wc0 + wc1 AHD + wc2 AHD^2), AHD = along-hole depth = scurve x reservoir top depth.
# The model does not state the unit of wc0; we read it as MEUR.
WC0_MEUR, WC1_EUR_M, WC2_EUR_M2, WC_SCALE, S_CURVE = 0.25, 700.0, 0.2, 1.3, 1.1
# DEA = Danish Energy Agency, Technology Data for electricity and district heat production (data sheets, 2026):
# https://ens.dk/media/8615/download
HP_EUR_KW = 950.0               # heat pump, EUR per kW heat out; source: DEA data sheet 40 (10 MW heat pump, 2020 euros)
BOILER_EUR_KW = 58.0            # gas peak boiler, EUR per kW; source: DEA, midpoint of 0.053-0.064 MEUR/MW
CHILLER_EUR_KW = 119.0          # water-cooled electric chiller above 400 kW, EUR per kW cold; source: Heat Roadmap Europe 4, report D3.2
TOWER_EUR_KW = 100.0            # wet cooling tower, EUR per kW heat rejected; assumed, no source
# single-effect lithium-bromide (LiBr) absorption chiller, EUR per kW cold; assumed: midpoint of a 314 EUR/kW and a 600 USD/kW quote
ABSORPTION_EUR_KW = 450.0
# Eurostat 2026 first half, Netherlands, excluding VAT
P_EL = 182.4                    # electricity price, EUR/MWh; source: Eurostat dataset nrg_pc_205, non-household band ID
# gas price, EUR/MWh on gross calorific value (GCV); source: Eurostat dataset nrg_pc_203, non-household band I4,
# https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nrg_pc_203
P_GAS = 83.9
BOILER_EFF = 0.9                # boiler efficiency, heat out per gas in on GCV; assumed, no source
GCV_LHV = 1.11                  # ratio of gross to lower calorific value of natural gas; assumed
# CO2 per MWh of gas on GCV, t/MWh: 56.2 kg/GJ on lower calorific value (LHV), RVO (Netherlands Enterprise Agency) 2026,
# divided by the GCV/LHV ratio
CO2_T_MWH = 56.2 * 3.6 / 1000 / GCV_LHV
# CO2 emission factor of grid electricity, kg per kWh; organiser reference value on Discord, 3 Nov 2026. No CO2 cost is added on
# electricity: the grid price already carries the EU emissions trading (ETS) cost of the power plants
EF_EL_KG_KWH = 0.3
P_CO2 = 58.64                   # CO2 price, EUR/t, EU emissions trading for buildings fuel (ETS2) from 2028; source: PBL SDE++ 2026


def doublet_meur(depth_m=year.DEPTH_M):
    """Cost of one doublet (two wells) on the ThermoGIS curve, million euros (MEUR); reservoir top half a thickness above depth_m."""
    ahd = S_CURVE * (depth_m - THICKNESS_M / 2)
    return 2 * WC_SCALE * (WC0_MEUR + (WC1_EUR_M * ahd + WC2_EUR_M2 * ahd ** 2) / 1e6)


def crf(r, n):
    """Capital recovery factor: the share of an investment paid each year at discount rate r over n years."""
    return r * (1 + r) ** n / ((1 + r) ** n - 1)


@lru_cache
def economics(n_doublets, t_return_c, peak_heat_MW=None, peak_cold_MW=None, doublet_MEUR=None, depth_m=year.DEPTH_M, heat_pump=True,
              esp_depth_m=year.ESP_DEPTH_M, outage_mode="staggered"):
    """Economics dict (see module docstring); doublet_MEUR overrides the ThermoGIS price, heat_pump=False prices a boiler lift,
    outage_mode places the planned outages (geo.outage)."""
    doublet_given = doublet_MEUR is not None
    doublet_MEUR = float(doublet_MEUR) if doublet_given else doublet_meur(float(depth_m))
    d = year.heating_year(int(n_doublets), float(t_return_c), peak_heat_MW=peak_heat_MW, depth_m=float(depth_m), heat_pump=bool(heat_pump),
                          esp_depth_m=float(esp_depth_m), outage_mode=outage_mode)
    c, tot = year.cooling_year(d.surplus, peak_cold_MW=peak_cold_MW)
    gwh = lambda s: float(s.sum() * 24 / 1000)
    rejected = c.cold + c.electric / year.COP_ELECTRIC + c.absorption / year.COP_ABSORPTION   # heat the cooling tower rejects, MW
    capex = {"doublets": n_doublets * doublet_MEUR, "heat_pump": d.hp.max() * HP_EUR_KW / 1000,
             "backup_boiler": year.BACKUP_BOILER_MW * BOILER_EUR_KW / 1000,
             "electric_chillers": year.chiller_MW(c) * CHILLER_EUR_KW / 1000, "cooling_tower": rejected.max() * TOWER_EUR_KW / 1000,
             "absorption_chillers": c.absorption.max() * ABSORPTION_EUR_KW / 1000}
    life = {k: LIFE_DOUBLET if k == "doublets" else LIFE_SURFACE for k in capex}
    heat_items, cold_items = ("doublets", "heat_pump", "backup_boiler"), ("electric_chillers", "cooling_tower", "absorption_chillers")
    el_heat = gwh(d.esp) + gwh(d.el_hp) + gwh(year.injection_pump_MW(d))
    el_cold = tot["el_chillers"] + tot["el_aux"]
    gas = gwh(d.boiler) / BOILER_EFF
    co2_kt = gas * CO2_T_MWH                                     # boiler gas: GWh x t/MWh = kilotonnes
    on = d.doublets_on
    days_run = float(on.sum())                                   # doublet-days run in the year
    q_run = float((d.q_m3h * on).sum() / days_run) if days_run else 0.0   # flow-weighted mean running flow, m3/h per doublet
    # associated gas over the doublet-days actually run, handled by gas.GAS_HANDLING; the engine's credit is reported, not netted
    ag = assoc.handling(q_run, float(depth_m), days=days_run, esp_kW=float(d.esp.sum()) * 1000 / days_run) if days_run else None

    def annual(items, el, gas_gwh, co2):
        return {"capital": sum(capex[k] * crf(R, life[k]) for k in items), "fom": sum(capex[k] * FOM for k in items),
                "electricity": el * P_EL / 1000, "gas": gas_gwh * P_GAS / 1000, "co2": co2 * P_CO2 / 1000}
    heat_cost, cold_cost = annual(heat_items, el_heat, gas, co2_kt), annual(cold_items, el_cold, 0.0, 0.0)
    heat_GWh, cold_GWh = gwh(d.demand - d.unmet), tot["cold"]
    return {"n_doublets": int(n_doublets), "t_return_c": float(t_return_c), "depth_m": float(depth_m),
            "layout": "B heat-pump lift" if heat_pump else "A boiler lift", "outage_mode": outage_mode,
            "capex_MEUR": {**capex, "total": sum(capex.values())},
            "annual_cost_MEUR": {"heating": heat_cost, "cooling": cold_cost,
                                 "total": sum(heat_cost.values()) + sum(cold_cost.values())},
            "heat_served_GWh": heat_GWh, "cold_served_GWh": cold_GWh,
            "lcoh_EUR_MWh": sum(heat_cost.values()) / heat_GWh * 1000,
            "lcoc_EUR_MWh": sum(cold_cost.values()) / cold_GWh * 1000 if cold_GWh > 0 else float("nan"),
            "electricity_GWh": el_heat + el_cold, "gas_GWh": gas, "co2_kt": co2_kt,
            "co2_electricity_kt": (el_heat + el_cold) * EF_EL_KG_KWH,   # GWh x kg/kWh = kilotonnes
            "co2_associated_gas_kt": ag["CO2e_t_per_yr"] / 1000 if ag else 0.0,
            "co2_total_kt": co2_kt + (el_heat + el_cold) * EF_EL_KG_KWH + (ag["CO2e_t_per_yr"] / 1000 if ag else 0.0),
            "gas_handling": assoc.GAS_HANDLING, "associated_gas_q_m3h": q_run, "associated_gas_doublet_days": days_run,
            "associated_gas_electricity_GWh": ag["electricity_MWh_per_yr"] / 1000 if ag else 0.0,
            "associated_gas_heat_GWh": ag["heat_MWh_per_yr"] / 1000 if ag else 0.0, "esp_GWh": gwh(d.esp), "tag": "[C]",
            "basis": {"discount_rate": f"{R} real [L, PBL 2026]", "life_yr": "doublets 30 [L, PBL], surface 20 [A]",
                      "fom": f"{FOM} of CAPEX per yr [C, PBL 4.6-6.9 %]",
                      "doublet_MEUR": (f"{doublet_MEUR:.2f} given by the caller [A]" if doublet_given else
                                       f"{doublet_MEUR:.2f} = 2 x {WC_SCALE} x ({WC0_MEUR} MEUR + {WC1_EUR_M:.0f} EUR/m AHD + "
                                       f"{WC2_EUR_M2} EUR/m2 AHD^2), AHD = {S_CURVE} x top {depth_m - THICKNESS_M / 2:.0f} m "
                                       "[L, ThermoGIS cost model, https://pythermogis-15909e.ci.tno.nl/theory/economicmodel/cost_model/; "
                                       "wc0 unit read as MEUR, A]; PBL SDE++ 2026 reference plants give 23.6-37.2 MEUR per doublet [TBC]"),
                      "heat_pump_EUR_kW": f"{HP_EUR_KW} [L, DEA]", "boiler_EUR_kW": f"{BOILER_EUR_KW} [C, DEA]",
                      "chiller_EUR_kW": f"{CHILLER_EUR_KW} [L, HRE4]", "tower_EUR_kW": f"{TOWER_EUR_KW} [A]",
                      "absorption_EUR_kW": f"{ABSORPTION_EUR_KW} [A/TBC]", "electricity_EUR_MWh": f"{P_EL} [L, Eurostat ID]",
                      "gas_EUR_MWh": f"{P_GAS} GCV [L, Eurostat], boiler eff {BOILER_EFF} [A]",
                      "co2": f"{CO2_T_MWH:.3f} t/MWh gas [D, RVO], {P_CO2} EUR/t [L, ETS2]",
                      "co2_electricity": f"{EF_EL_KG_KWH} kg/kWh grid [D, organiser Q&A 3 Nov 2026]; no CO2 cost, the grid price carries ETS [A]",
                      "co2_associated_gas": f"gas handled by '{assoc.GAS_HANDLING}' at the flow-weighted mean running flow {q_run:.0f} m3/h over "
                                            f"{days_run:.0f} doublet-days [C]; engine or boiler credit reported, not netted [A]"}}


if __name__ == "__main__":
    rows = {n: economics(n, 60.0, 30.0, 10.0) for n in (1, 2, 3)}
    print("n  CAPEX MEUR  heat GWh  LCoH EUR/MWh  LCoC EUR/MWh  el GWh  gas GWh  CO2 kt  CO2 el kt  CO2 assoc kt  CO2 total kt"
          "   (60 C return, 30/10 MW) [C]")
    for n, e in rows.items():
        print(f"{n}  {e['capex_MEUR']['total']:10.2f}  {e['heat_served_GWh']:8.2f}  {e['lcoh_EUR_MWh']:12.2f}  "
              f"{e['lcoc_EUR_MWh']:12.2f}  {e['electricity_GWh']:6.2f}  {e['gas_GWh']:7.2f}  {e['co2_kt']:6.2f}  "
              f"{e['co2_electricity_kt']:9.2f}  {e['co2_associated_gas_kt']:12.2f}  {e['co2_total_kt']:12.2f}")
    print(f"third doublet costs {rows[3]['lcoh_EUR_MWh'] - rows[2]['lcoh_EUR_MWh']:+.2f} EUR/MWh of heat [C]")
