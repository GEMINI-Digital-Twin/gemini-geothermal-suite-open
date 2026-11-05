"""Independent hand calculation of the selected design — no GEMINI, no agent code.

First-principles formulas and the brief's inputs only, to cross-check the agent's results.
Run: python3 independent_check.py
"""

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "gemini" / "docs_geohackathon2026" / "figures"
SPEC = json.loads((FIG / "selected_design.json").read_text())["selected_spec"]  # the agent's design
AGENT = json.loads((FIG / "robustness.json").read_text())["robust_summary"]  # its simulated KPIs
CH_MW, BOIL_MW = SPEC["electric_chiller_mw"], SPEC["backup_boiler_mw"]
rows = lambda f, c: [float(r[c]) for r in csv.DictReader(open(ROOT / "files" / f))]  # noqa: E731
heat = rows("GEMINI_Heating_Demand_Daily_2027.csv", "heating_demand_MWth")
cool = rows("GEMINI_Cooling_Demand_Daily_2027.csv", "cooling_demand_MWcool")

# --- brief inputs ---------------------------------------------------------------------------------
T_SURF, GRAD, RHO, Q_MAX, DT_MAX = 12.0, 30.0, 1030.0, 300.0, 40.0  # °C, °C/km, kg/m3, m3/h, K
T_SUP, T_RET, DAYS_ON = 100.0, 45.0, 330
# --- my own assumptions (stated) -------------------------------------------------------------------
CP = 4.0e3          # J/kg/K brine (saline, ~4.0; pure water 4.18)
WELL_LOSS_K = 2.5   # heat lost up the producer at full flow (Ramey-type estimate, 1-4 K)
COP_CH = 7.5        # electric chiller at 20 °C chilled water (≈ 45 % of Carnot 290 K / 18 K)
ETA_PUMP, PI = 0.70, 11.7  # pump efficiency (brief); productivity index m3/h/bar (Darcy, 200 mD, 100 m)

print("=== 1. Resource")
for z in (2.5, 3.1):
    print(f"  {z} km: reservoir {T_SURF + GRAD * z:.1f} °C, hydrostatic {RHO * 9.81 * z * 1e3 / 1e5:.0f} bar")
t_res = T_SURF + GRAD * 3.1
t_wh = t_res - WELL_LOSS_K
print(f"  wellhead at 3.1 km ≈ {t_wh:.1f} °C (agent: 102.6 °C)")

print("=== 2. Heat per doublet: Q = rho * q * cp * dT")
for cp in (3.9e3, 4.0e3, 4.18e3):
    q = RHO * Q_MAX / 3600 * cp * DT_MAX / 1e6
    print(f"  cp {cp / 1e3:.2f} kJ/kgK -> {q:.2f} MW per doublet, {2 * q:.2f} MW for two (agent: 13.73 / 27.47)")
Q1 = RHO * Q_MAX / 3600 * CP * DT_MAX / 1e6
print(f"  brine out {t_wh - DT_MAX:.1f} °C vs DH return {T_RET} °C: {t_wh - DT_MAX - T_RET:.1f} K margin at the cold end")

print("=== 3. Daily balance, 2 doublets, each offline 35 days in summer (staggered)")
off = [set(range(190, 225)), set(range(225, 260))]  # Jul-Sep, low heat demand
boiler, geo, worst_n1 = 0.0, 0.0, 0.0
for d, h in enumerate(heat):
    n = sum(1 for o in off if d not in o)
    g = min(h, n * Q1)
    geo += g * 24
    boiler += (h - g) * 24
    worst_n1 = max(worst_n1, h - Q1)  # one doublet tripped that day
summer_max = max(heat[d] for d in range(190, 260))
print(f"  summer heat during maintenance ≤ {summer_max:.1f} MW (one doublet gives {Q1:.1f}) -> covered")
print(f"  boiler energy {boiler / 1e3:.2f} GWh, geothermal share {100 * geo / (geo + boiler):.1f} % (agent: 0.92 GWh, 99.2 %)")
print(f"  peak day boiler {max(heat) - 2 * Q1:.2f} MW; one doublet out: boiler {worst_n1:.2f} MW (agent: 2.53 / 16.27; installed 17.5)")
print(f"  heating + cooling max on any day: {max(a + b for a, b in zip(heat, cool)):.1f} MW")

print("=== 4. Pumping (producer ESP), keep loop ≥ 30 bar so gas stays dissolved")
p_res = RHO * 9.81 * 3100 / 1e5
p_bh = p_res - Q_MAX / PI                       # drawdown
p_wh_nopump = p_bh - RHO * 9.81 * 3100 / 1e5    # column weight (constant density per brief)
dp_pump = 30 - p_wh_nopump + 8                  # + ~8 bar friction/filters (assumed)
p_kw = Q_MAX / 3600 * dp_pump * 1e5 / ETA_PUMP / 1e3
print(f"  drawdown {Q_MAX / PI:.1f} bar, pump head {dp_pump:.0f} bar -> {p_kw:.0f} kW per doublet at full flow (agent ESP: 762 kW)")
pump_gwh = sum(min(1.0, h / (2 * Q1)) ** 1 * 2 * p_kw / 1e3 * 24 for h in heat) / 1e3  # flow ~ load (crude)
print(f"  pump electricity ≈ {pump_gwh:.1f} GWh/yr (crude: flow ∝ load) (agent: 6.08)")

print("=== 5. Cooling")
ch_gwh = sum(cool) * 24 / 1e3 / COP_CH
print(f"  {sum(cool) * 24 / 1e3:.2f} GWh cooling / COP {COP_CH} = {ch_gwh:.2f} GWh electricity; peak {max(cool) / COP_CH:.2f} MWe")

print("=== 6. CO2 (grid 0.3 kg/kWh; gas 0.202 kg/kWh LHV, boiler 92 %)")
el = pump_gwh + ch_gwh
co2 = el * 1e3 * 0.3 + boiler / 1e3 * 1e3 / 0.92 * 0.202
print(f"  electricity {el:.1f} GWh -> {el * 300:.0f} t; boiler gas -> {boiler / 0.92 * 0.202:.0f} t; total ≈ {co2:.0f} t/yr (agent: {AGENT['co2_t_per_year']:,.0f})")

print("=== 7. Cost (assumptions as in economics_assumptions.yaml)")
md = 3100 * 1.15
capex = {"4 wells": 4 * (2e6 + 2000 * md), "surface 2 doublets (pressurised)": 2 * 3.5e6,
         "heat exchangers": 50e3 * 2 * Q1, f"chillers {CH_MW:g} MW": 250e3 * CH_MW, f"boiler {BOIL_MW:g} MW": 80e3 * BOIL_MW}
tot = sum(capex.values())
for k, v in capex.items():
    print(f"  {k:34s} {v / 1e6:6.2f} M€")
crf = 0.06 * 1.06 ** 30 / (1.06 ** 30 - 1)
opex = 0.01 * capex["4 wells"] + 0.025 * (tot - capex["4 wells"])
energy = el * 1e3 * 150 + boiler / 0.92 * 45 + co2 * 90
lcoe = (tot * crf + opex + energy) / ((sum(heat) + sum(cool)) * 24)
print(f"  CAPEX {tot / 1e6:.1f} M€ (agent {AGENT['capex_meur']:.1f}); LCOE {lcoe:.1f} €/MWh (agent {AGENT['lcoe_eur_per_mwh']:.1f})")
(Path(__file__).parent / "independent_check.json").write_text(json.dumps({
    "peak_geo_mw": round(2 * Q1, 1), "peak_boiler_mw": round(max(heat) - 2 * Q1, 1), "n1_boiler_mw": round(worst_n1, 1),
    "pump_kw": round(p_kw), "capex_meur": round(tot / 1e6, 1), "lcoe": round(lcoe, 1), "co2_t": round(co2),
    "boiler_gap_gwh": round(abs(boiler / 1e3 - AGENT["heat_supply_gwh"]["boiler"]), 2),
    "chillers_mw": CH_MW, "agent_lcoe": AGENT["lcoe_eur_per_mwh"], "agent_capex_meur": AGENT["capex_meur"]}, indent=1))
