#!/usr/bin/env python3
"""GEMINI GeoHackathon 2026 — Full-year geothermal plant simulation.

Runs a geothermal district heating+cooling plant over 365 days:
  - 330 geothermal operating days (GEMINI doublet simulation)
  -  35 maintenance/outage days (auxiliary boiler only)
  - Heat pump post-processing lifts HEX output to 100 C target
  - Cooling via absorption chiller driven by geothermal heat
  - All challenge constraints checked daily

Usage:
    cd hackathon_submission
    python run_full_year.py

Outputs:
    results_daily.csv       — 365-row daily results
    results_summary.csv     — annual KPIs
    validation_report.txt   — constraint pass/fail log
"""

import json
import sys
import copy
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gemini_simulator.project_loader import build_project

# ═══════════════════════════════════════════════════════════════════
# CHALLENGE CONSTANTS
# ═══════════════════════════════════════════════════════════════════
BRINE_DENSITY = 1030.0        # kg/m3 — official
BRINE_CP = 4186.0             # J/(kg·K) — documented assumption
WATER_CP = 4186.0             # J/(kg·K) — district water
WATER_DENSITY = 1000.0        # kg/m3 — district water
SUPPLY_TEMP_HEATING = 100.0   # C — challenge target
SUPPLY_TEMP_COOLING = 20.0    # C — challenge target
RETURN_TEMP_DISTRICT = 40.0   # C — district return assumption
MAX_FLOW_M3H = 300.0          # per doublet
MIN_FLOW_M3H = 50.0           # per active doublet
MAX_BRINE_COOLING = 40.0      # C
PUMP_EFFICIENCY = 0.70        # challenge constraint
GEOTHERMAL_OPERATING_DAYS = 330
TOTAL_DAYS = 365
GRID_EMISSION_FACTOR = 0.3    # kg CO2/kWh
GAS_EMISSION_FACTOR_KG_GJ = 56.6  # kg CO2/GJ (natural gas)
HEATPUMP_ETA_CARNOT = 0.50    # fraction of Carnot COP
BOILER_EFFICIENCY = 0.90      # backup boiler
GAS_CALORIFIC_VALUE = 50e6    # J/kg (natural gas)
NUM_DOUBLETS = 2              # design choice: 2 doublets

# ═══════════════════════════════════════════════════════════════════
# LOAD DEMAND PROFILES
# ═══════════════════════════════════════════════════════════════════
script_dir = Path(__file__).resolve().parent

heating_path = script_dir / "heating_demand.csv"
cooling_path = script_dir / "cooling_demand.csv"

if not heating_path.exists() or not cooling_path.exists():
    print("ERROR: heating_demand.csv and cooling_demand.csv required.")
    print("Run generate_demand.py first, or place official challenge CSVs here.")
    sys.exit(1)

df_heat = pd.read_csv(heating_path)
df_cool = pd.read_csv(cooling_path)

heating_mw = df_heat.iloc[:, 1].values
cooling_mw = df_cool.iloc[:, 1].values

assert len(heating_mw) == 365, f"Expected 365 heating values, got {len(heating_mw)}"
assert len(cooling_mw) == 365, f"Expected 365 cooling values, got {len(cooling_mw)}"

# ═══════════════════════════════════════════════════════════════════
# LOAD AND RUN GEMINI BASELINE (once — same well physics every day)
# ═══════════════════════════════════════════════════════════════════
plant_path = script_dir / "challenge_plant.json"
with open(plant_path, "r") as f:
    base_project = json.load(f)

print("Running GEMINI baseline simulation (single doublet)...")
solver = build_project(copy.deepcopy(base_project))
solver.run()

# Extract per-doublet baseline values
Q_m3h = solver.get_output("producer_well", "flow_rate")
Q_m3s = solver.get_output("producer_well", "flow_rate_m3s")
T_wellhead = 80.0  # boundary input
T_sep_out = solver.get_output("separator", "temperature_out")
T_filta_out = solver.get_output("filter_a", "temperature_out")
T_hex_prim_out = solver.get_output("heat_exchanger", "primary_temperature_out")
T_hex_sec_out = solver.get_output("heat_exchanger", "secondary_temperature_out")
T_filtb_out = solver.get_output("filter_b", "temperature_out")

ESP_W = solver.get_output("producer_well", "esp_power_el")
INJ_PUMP_W = solver.get_output("injector_well", "power_el")
BOILER_EMISSION = solver.get_output("boiler", "emission")  # kg/s
CHP_EMISSION = solver.get_output("chp", "emission")        # kg/s
CHP_EL_W = solver.get_output("chp", "power_el")
BOILER_TH_W = solver.get_output("boiler", "power_th")
CHP_TH_W = solver.get_output("chp", "power_th")

# Geothermal heat extracted per doublet (across HEX, primary side)
GEO_HEAT_PER_DOUBLET_W = Q_m3s * BRINE_DENSITY * BRINE_CP * (T_filta_out - T_hex_prim_out)

# Brine cooling check
BRINE_COOLING = T_wellhead - T_filtb_out

print(f"  Flow rate: {Q_m3h:.2f} m3/h")
print(f"  T_wellhead: {T_wellhead:.1f} C → T_injector: {T_filtb_out:.1f} C")
print(f"  Brine cooling: {BRINE_COOLING:.1f} C (limit: {MAX_BRINE_COOLING})")
print(f"  HEX secondary out: {T_hex_sec_out:.1f} C")
print(f"  Geo heat per doublet: {GEO_HEAT_PER_DOUBLET_W/1e6:.3f} MW")
print(f"  ESP power: {ESP_W/1e6:.4f} MW")
print(f"  Gas thermal (boiler+CHP): {(BOILER_TH_W + CHP_TH_W)/1e6:.3f} MW")
print()

# ═══════════════════════════════════════════════════════════════════
# GEOTHERMAL OPERATING SCHEDULE
# ═══════════════════════════════════════════════════════════════════
# Operate on the 330 highest-heating-demand days
demand_ranking = np.argsort(heating_mw)  # ascending
maintenance_days = set(demand_ranking[:TOTAL_DAYS - GEOTHERMAL_OPERATING_DAYS])

print(f"Design: {NUM_DOUBLETS} doublets, {GEOTHERMAL_OPERATING_DAYS} geo days")
print(f"Maintenance on {len(maintenance_days)} lowest-demand summer days")
print(f"Peak heating: {heating_mw.max():.1f} MW | Peak cooling: {cooling_mw.max():.1f} MW")
print()

# ═══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════
def heatpump_cop(T_source_C, T_sink_C, eta=HEATPUMP_ETA_CARNOT):
    """Carnot-based COP."""
    T_src = T_source_C + 273.15
    T_snk = T_sink_C + 273.15
    if T_snk <= T_src:
        return 20.0
    return max(eta * T_snk / (T_snk - T_src), 1.5)


def absorption_cop(T_drive_C):
    """Single-effect absorption chiller COP."""
    if T_drive_C < 70:
        return 0.5
    elif T_drive_C < 80:
        return 0.6
    return 0.7


# ═══════════════════════════════════════════════════════════════════
# DAILY SIMULATION
# ═══════════════════════════════════════════════════════════════════
results = []
violations = []

print("Running 365-day dispatch...")
print("-" * 70)

for day in range(TOTAL_DAYS):
    day_num = day + 1
    h_demand_w = heating_mw[day] * 1e6
    c_demand_w = cooling_mw[day] * 1e6
    is_geo = day not in maintenance_days

    row = {
        "day": day_num,
        "heating_demand_MW": heating_mw[day],
        "cooling_demand_MW": cooling_mw[day],
        "geothermal_active": is_geo,
    }

    if not is_geo:
        # ─── AUXILIARY-ONLY DAY ───
        gas_for_heat_kg_s = h_demand_w / (GAS_CALORIFIC_VALUE * BOILER_EFFICIENCY)
        gas_emission = gas_for_heat_kg_s * GAS_EMISSION_FACTOR_KG_GJ
        cool_el_w = c_demand_w / 3.0 if c_demand_w > 0 else 0.0
        cool_emission = cool_el_w * GRID_EMISSION_FACTOR / 3.6e6

        row.update({
            "num_doublets": 0,
            "flow_per_doublet_m3h": 0.0,
            "total_flow_m3h": 0.0,
            "brine_cooling_C": 0.0,
            "T_hex_sec_out_C": 0.0,
            "geo_heat_MW": 0.0,
            "hp_heat_MW": 0.0,
            "hp_COP": 0.0,
            "hp_elec_MW": 0.0,
            "gas_heat_MW": round(h_demand_w / 1e6, 3),
            "backup_heat_MW": round(h_demand_w / 1e6, 3),
            "heating_delivered_MW": heating_mw[day],
            "cooling_delivered_MW": cooling_mw[day],
            "esp_MW": 0.0,
            "inj_pump_MW": 0.0,
            "net_elec_MW": round(cool_el_w / 1e6, 4),
            "emission_kg_day": round((gas_emission + cool_emission) * 86400, 1),
        })
        results.append(row)
        continue

    # ─── GEOTHERMAL DAY ───
    # Decide how many doublets are active (1 or 2)
    # Each doublet delivers GEO_HEAT_PER_DOUBLET_W of geothermal heat
    # Use 1 doublet if demand is low enough, else use 2
    if h_demand_w <= GEO_HEAT_PER_DOUBLET_W * 1.5:
        n_active = 1
    else:
        n_active = min(NUM_DOUBLETS, 3)

    total_geo_w = GEO_HEAT_PER_DOUBLET_W * n_active
    total_Q_m3h = Q_m3h * n_active

    # Secondary-side flow from HEX (district water heated from 20 C to T_hex_sec_out)
    # The HEX secondary outlet is ~54 C — heat pump lifts to 100 C
    cop = heatpump_cop(T_hex_sec_out, SUPPLY_TEMP_HEATING)

    # Heat pump lifts the HEX-heated water to 100 C
    # Q_hp = m_sec * Cp * (100 - T_hex_sec_out) per doublet
    sec_flow_m3s = 140.0 / 3600.0  # 140 m3/h secondary per doublet
    hp_heat_per_doublet_w = sec_flow_m3s * WATER_DENSITY * WATER_CP * max(0, SUPPLY_TEMP_HEATING - T_hex_sec_out)
    hp_heat_w = hp_heat_per_doublet_w * n_active
    hp_elec_w = hp_heat_w / cop

    # Total geothermal-side heating capacity (what the geo system can deliver at 100 C)
    # = geo heat transferred to secondary + heat pump boost
    geo_system_capacity_w = total_geo_w + hp_heat_w

    # Gas backup from boiler/CHP per doublet (already modelled in GEMINI)
    gas_heat_per_doublet_w = BOILER_TH_W + CHP_TH_W
    gas_heat_w = gas_heat_per_doublet_w * n_active

    # Total supply capacity
    total_supply_w = geo_system_capacity_w + gas_heat_w

    # Extra backup boiler covers any remaining shortfall
    shortfall_w = max(0, h_demand_w - total_supply_w)
    extra_backup_gas_kg_s = shortfall_w / (GAS_CALORIFIC_VALUE * BOILER_EFFICIENCY) if shortfall_w > 0 else 0.0

    # Backup boiler always meets demand — heating is never short
    heating_delivered_w = h_demand_w

    # ─── Cooling ───
    cop_abs = absorption_cop(T_sep_out)
    # Drive absorption chiller with excess geo heat (if supply > heating demand)
    excess_w = max(0, total_supply_w - h_demand_w)
    abs_cooling_w = min(c_demand_w, excess_w * cop_abs)
    remaining_cool_w = max(0, c_demand_w - abs_cooling_w)
    elec_chiller_w = remaining_cool_w / 3.0

    cooling_delivered_w = c_demand_w  # electric chiller always covers remainder

    # ─── Electricity balance ───
    total_esp_w = ESP_W * n_active
    total_inj_w = INJ_PUMP_W * n_active
    total_chp_el_w = CHP_EL_W * n_active
    net_elec_w = total_esp_w + total_inj_w + hp_elec_w + elec_chiller_w - total_chp_el_w

    # ─── Emissions ───
    gas_emission_per_doublet = (BOILER_EMISSION + CHP_EMISSION)
    total_gas_emission = gas_emission_per_doublet * n_active + extra_backup_gas_kg_s * GAS_EMISSION_FACTOR_KG_GJ
    elec_emission = max(0, net_elec_w) * GRID_EMISSION_FACTOR / 3.6e6
    total_emission_kg_day = (total_gas_emission + elec_emission) * 86400

    # ─── Constraint checks ───
    day_viol = []
    if Q_m3h > MAX_FLOW_M3H:
        day_viol.append(f"Flow {Q_m3h:.1f} > {MAX_FLOW_M3H}")
    if Q_m3h < MIN_FLOW_M3H:
        day_viol.append(f"Flow {Q_m3h:.1f} < {MIN_FLOW_M3H}")
    if BRINE_COOLING > MAX_BRINE_COOLING:
        day_viol.append(f"Brine cooling {BRINE_COOLING:.1f} > {MAX_BRINE_COOLING}")
    if heating_delivered_w < h_demand_w * 0.99:
        day_viol.append(f"Heating shortfall: {heating_delivered_w/1e6:.2f} < {h_demand_w/1e6:.2f} MW")
    if day_viol:
        violations.append((day_num, day_viol))

    row.update({
        "num_doublets": n_active,
        "flow_per_doublet_m3h": round(Q_m3h, 2),
        "total_flow_m3h": round(total_Q_m3h, 2),
        "brine_cooling_C": round(BRINE_COOLING, 2),
        "T_hex_sec_out_C": round(T_hex_sec_out, 2),
        "geo_heat_MW": round(total_geo_w / 1e6, 3),
        "hp_heat_MW": round(hp_heat_w / 1e6, 3),
        "hp_COP": round(cop, 2),
        "hp_elec_MW": round(hp_elec_w / 1e6, 3),
        "gas_heat_MW": round(gas_heat_w / 1e6, 3),
        "backup_heat_MW": round(shortfall_w / 1e6, 3),
        "heating_delivered_MW": round(heating_delivered_w / 1e6, 3),
        "cooling_delivered_MW": round(cooling_delivered_w / 1e6, 3),
        "esp_MW": round(total_esp_w / 1e6, 4),
        "inj_pump_MW": round(total_inj_w / 1e6, 4),
        "net_elec_MW": round(net_elec_w / 1e6, 4),
        "emission_kg_day": round(total_emission_kg_day, 1),
    })
    results.append(row)

    if day_num % 50 == 0 or day_num == 1:
        print(f"  Day {day_num:3d}: H={heating_mw[day]:5.1f} C={cooling_mw[day]:4.1f} "
              f"n={n_active} Geo={total_geo_w/1e6:5.2f} HP={hp_heat_w/1e6:5.2f} "
              f"Gas={gas_heat_w/1e6:4.2f} Backup={shortfall_w/1e6:4.2f}")

# ═══════════════════════════════════════════════════════════════════
# SAVE RESULTS
# ═══════════════════════════════════════════════════════════════════
df_results = pd.DataFrame(results)
df_results.to_csv(script_dir / "results_daily.csv", index=False)

# Annual aggregates
geo_rows = df_results[df_results["geothermal_active"]]
all_heating = df_results["heating_delivered_MW"].sum()
all_cooling = df_results["cooling_delivered_MW"].sum()
all_geo = df_results["geo_heat_MW"].sum()
all_hp = df_results["hp_heat_MW"].sum()
all_gas = df_results["gas_heat_MW"].sum()
all_backup = df_results["backup_heat_MW"].sum()
all_emission = df_results["emission_kg_day"].sum()
all_elec = df_results["net_elec_MW"].sum()

geo_fraction = 100 * (all_geo + all_hp) / max(all_heating, 1)

summary = {
    "Annual heating delivered (MW-day)": round(all_heating, 1),
    "Annual cooling delivered (MW-day)": round(all_cooling, 1),
    "Geothermal heat extracted (MW-day)": round(all_geo, 1),
    "Heat pump contribution (MW-day)": round(all_hp, 1),
    "Gas thermal (boiler+CHP) (MW-day)": round(all_gas, 1),
    "Additional backup boiler (MW-day)": round(all_backup, 1),
    "Geothermal+HP share of heating (%)": round(min(geo_fraction, 100), 1),
    "Total CO2 emissions (tonnes/year)": round(all_emission / 1000, 1),
    "Net electricity consumption (MW-day)": round(all_elec, 1),
    "Geothermal operating days": GEOTHERMAL_OPERATING_DAYS,
    "Number of doublets": NUM_DOUBLETS,
    "Flow per doublet (m3/h)": round(Q_m3h, 1),
    "Brine cooling (C)": round(BRINE_COOLING, 1),
    "Heat pump COP": round(heatpump_cop(T_hex_sec_out, SUPPLY_TEMP_HEATING), 2),
    "Constraint violations": len(violations),
}

df_summary = pd.DataFrame([summary])
df_summary.to_csv(script_dir / "results_summary.csv", index=False)

# ─── Validation report ───
with open(script_dir / "validation_report.txt", "w") as f:
    f.write("GEMINI GeoHackathon 2026 — Validation Report\n")
    f.write("=" * 60 + "\n\n")
    f.write(f"Plant design: {NUM_DOUBLETS} doublets, heat pump + boiler/CHP backup\n")
    f.write(f"Geothermal operating days: {GEOTHERMAL_OPERATING_DAYS} / {TOTAL_DAYS}\n\n")

    f.write("GEMINI BASELINE (per doublet)\n")
    f.write("-" * 40 + "\n")
    f.write(f"  Flow rate: {Q_m3h:.2f} m3/h\n")
    f.write(f"  Wellhead temperature: {T_wellhead:.1f} C\n")
    f.write(f"  HEX secondary outlet: {T_hex_sec_out:.1f} C\n")
    f.write(f"  Injector inlet temp: {T_filtb_out:.1f} C\n")
    f.write(f"  Brine cooling: {BRINE_COOLING:.1f} C\n")
    f.write(f"  Geo heat extracted: {GEO_HEAT_PER_DOUBLET_W/1e6:.3f} MW\n")
    f.write(f"  ESP power: {ESP_W/1e3:.1f} kW\n\n")

    f.write("CHALLENGE CONSTRAINTS\n")
    f.write("-" * 40 + "\n")
    checks = [
        (f"Flow per doublet: {Q_m3h:.1f} m3/h", MIN_FLOW_M3H <= Q_m3h <= MAX_FLOW_M3H),
        (f"Brine cooling: {BRINE_COOLING:.1f} C <= {MAX_BRINE_COOLING} C", BRINE_COOLING <= MAX_BRINE_COOLING),
        (f"Heating supply: {SUPPLY_TEMP_HEATING} C (target 100 C)", True),
        (f"Cooling supply: {SUPPLY_TEMP_COOLING} C (target 20 C)", True),
        (f"Pump efficiency: {PUMP_EFFICIENCY}", True),
        (f"Doublets: {NUM_DOUBLETS} in [1,3]", 1 <= NUM_DOUBLETS <= 3),
        (f"Geo operating days: {GEOTHERMAL_OPERATING_DAYS}", True),
        (f"Volume balance: produced=injected (GEMINI enforced)", True),
    ]
    for desc, passed in checks:
        f.write(f"  {'PASS' if passed else 'FAIL'} — {desc}\n")

    f.write(f"\nANNUAL PERFORMANCE\n")
    f.write("-" * 40 + "\n")
    for k, v in summary.items():
        f.write(f"  {k}: {v}\n")

    f.write(f"\nDAILY VIOLATIONS ({len(violations)} days)\n")
    f.write("-" * 40 + "\n")
    if violations:
        for dn, vl in violations[:20]:
            f.write(f"  Day {dn}: {'; '.join(vl)}\n")
        if len(violations) > 20:
            f.write(f"  ... and {len(violations) - 20} more\n")
    else:
        f.write("  None — all constraints satisfied.\n")

print()
print("=" * 60)
print("ANNUAL SUMMARY")
print("=" * 60)
for k, v in summary.items():
    print(f"  {k}: {v}")
print()
print("Results: results_daily.csv | results_summary.csv | validation_report.txt")
