"""Can the plant also make electricity? ORC power unit study on KNMI 2025 weather.

Starts from the final pick (2 doublets at 3.1 km, CHP, 33 MW boiler,
air-cooled chiller + free cooling + 3 ATES well pairs, staggered stops) and
adds an air-cooled ORC power unit (gemini_model.orc) on the brine after the
district HEX, down to the 40 K cap, so it only uses heat the district does
not need that day. The dispatcher chooses each day's flow, so it raises the
flow when the ORC's power is worth more than the extra pumping.

Parts:
  A  ORC size on the pick (0.5-3 MW_e).
  B  deeper wells (3.5-4.5 km; hotter brine, more heat above 100 degC) with and
     without an ORC.
  C  sensitivity of the best ORC case: export price = import price, ORC cost
     -33 %, cycle at the top of its calibrated range, CO2 price.
  D  power-only third doublet at 4.5 km.
  E  why the ORC can not sit ahead of the HEX (topping cascade): one doublet,
     the 40 K cap shared between power and heat (component model only).

    $env:PYTHONPATH="src"
    python simulator_examples/run_orc_study.py

Writes simulator_examples/study_results/2026-11-03/orc/: runs.csv, runs.md,
cascade.csv.
"""

import csv
import sys
import warnings
from pathlib import Path

from gemini_agent.tools import make_design
from gemini_design.annual import run_year
from gemini_design.challenge import ASSUMPTIONS, CHALLENGE, load_demand
from gemini_design.climate import read_knmi_daily, with_climate
from gemini_design.doublet import DoubletHydraulics
from gemini_model.orc.orc import OrganicRankineCycle

sys.path.insert(0, str(Path(__file__).parent))
from run_final_pick import INPUTS, PICK  # noqa: E402

KNMI = Path(__file__).parent / "weather" / "knmi_etmgeg_240_1991_2025.txt"
OUT = Path(__file__).parent / "study_results" / "2026-11-03" / "orc"


def run(label, request, overrides=None, demand=None):
    """Run one design for the year; return a flat row of KPIs."""
    assumptions = {**ASSUMPTIONS, **(overrides or {})}
    design = make_design(request, 30.0, 10.0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        daily, s = run_year(design, demand, CHALLENGE, assumptions)
    e, k, ec = s["energy_mwh"], s["kpi"], s["economics"]
    pumping = float((daily["esp_power_w"] + daily["injection_pump_power_w"]).sum()) * 24 / 1e6
    row = {
        "case": label,
        "design": design.name,
        "depth_m": design.depth_m,
        "reservoir_c": round(s["reservoir"]["temperature_c"], 1),
        "orc_mw_el": design.orc_capacity_mw_el,
        "lcoe_eur_per_mwh": round(ec["lcoe_eur_per_mwh"], 2),
        "co2_t": round(k["co2_t_per_year"]),
        "all_rules_met": s["all_hard_constraints_met"],
        "capex_meur": round(ec["capex_eur"]["total"] / 1e6, 2),
        "orc_capex_meur": round(ec["capex_eur"]["orc"] / 1e6, 2),
        "orc_mwh_el": round(e["orc_electricity"]),
        "orc_heat_mwh": round(e["orc_heat"]),
        "orc_full_load_hours": (
            round(e["orc_electricity"] / design.orc_capacity_mw_el)
            if design.orc_capacity_mw_el
            else 0
        ),
        "orc_mean_efficiency_pct": (
            round(100 * e["orc_electricity"] / e["orc_heat"], 2) if e["orc_heat"] else 0.0
        ),
        "pumping_mwh": round(pumping),
        "geothermal_heat_mwh": round(e["geothermal_heat"]),
        "purchased_gas_mwh": round(e["purchased_gas_fuel"]),
        "grid_import_mwh": round(e["grid_import"]),
        "grid_export_mwh": round(e["grid_export"]),
        "associated_gas_mwh": round(e["associated_gas_fuel"]),
        "doublet_days": int((daily["n_active"]).sum()),
        "mean_flow_m3h": round(float(daily.loc[daily.n_active > 0, "flow_per_doublet_m3h"].mean())),
    }
    print(
        f"{label:46s} {row['lcoe_eur_per_mwh']:7.2f} EUR/MWh {row['co2_t']:6d} t "
        f"ORC {row['orc_mwh_el']:6d} MWh pumping {row['pumping_mwh']:5d} MWh "
        f"ok={row['all_rules_met']}",
        flush=True,
    )
    return row


def cascade_table():
    """One doublet at 300 m3/h: ORC ahead of the HEX vs after it (topping vs bottoming).

    With the 40 K cap the brine can give up at most ~14.4 MW. Ahead of the
    HEX the ORC cools it first, so less is left above the district's needs.
    """
    rows = []
    orc = OrganicRankineCycle()
    orc.update_parameters({"capacity_net": 50e6, "plr_min": 0.0})
    rho_cp = CHALLENGE["brine_density"] * ASSUMPTIONS["brine_cp"]
    q = 300.0 / 3600.0
    for depth in (3100, 3500, 4000, 4500):
        hyd = DoubletHydraulics(depth)
        prod = hyd.producer(300.0)
        t_wh = prod["wellhead_temperature_c"]
        t_cap = t_wh - CHALLENGE["brine_cooling_max_k"]
        for air in (5.0, 10.0, 18.0):
            # power only: ORC uses the whole 40 K
            orc.calculate_output(
                {
                    "hot_temperature_in": t_wh,
                    "hot_flow_rate": q,
                    "air_temperature": air,
                    "hot_temperature_out_min": t_cap,
                }
            )
            p_only = orc.output["power_el"]
            # topping: ORC down to 103 degC (3 K HEX approach to the 100 degC supply), then HEX
            t_split = max(t_cap, 103.0)
            if t_wh > t_split:
                orc.calculate_output(
                    {
                        "hot_temperature_in": t_wh,
                        "hot_flow_rate": q,
                        "air_temperature": air,
                        "hot_temperature_out_min": t_split,
                    }
                )
                p_top = orc.output["power_el"]
            else:
                p_top = 0.0
            heat_top = rho_cp * q * max(0.0, min(t_split, t_wh) - t_cap)
            rows.append(
                {
                    "depth_m": depth,
                    "wellhead_c": round(t_wh, 1),
                    "air_c": air,
                    "pumping_mw": round(
                        (prod["esp_power_w"] + hyd.injector(300.0, t_cap)["pump_power_w"]) / 1e6, 3
                    ),
                    "heat_only_mw_th": round(rho_cp * q * 40.0 / 1e6, 2),
                    "power_only_mw_el": round(p_only / 1e6, 3),
                    "power_only_eff_pct": round(100 * p_only / (rho_cp * q * 40.0), 2),
                    "topping_orc_mw_el": round(p_top / 1e6, 3),
                    "topping_heat_left_mw_th": round(heat_top / 1e6, 2),
                }
            )
    return rows


def main():
    """Run the study and write the tables."""
    OUT.mkdir(parents=True, exist_ok=True)
    weather = read_knmi_daily(KNMI, 2025)
    demand = with_climate(load_demand(INPUTS), weather, "max")
    rows = [run("A pick (no ORC)", PICK, demand=demand)]
    for mw in (0.5, 1.0, 2.0, 3.0):
        rows.append(
            run(f"A pick + ORC {mw:g} MW", {**PICK, "orc_capacity_mw_el": mw}, None, demand)
        )
    best_deep = None
    for depth in (3500, 4000, 4500):
        base = {**PICK, "depth_m": depth}
        rows.append(run(f"B {depth} m (no ORC)", base, None, demand))
        for mw in (1.0, 2.0, 3.0):
            row = run(
                f"B {depth} m + ORC {mw:g} MW", {**base, "orc_capacity_mw_el": mw}, None, demand
            )
            rows.append(row)
            if best_deep is None or row["lcoe_eur_per_mwh"] < best_deep[1]["lcoe_eur_per_mwh"]:
                best_deep = ({**base, "orc_capacity_mw_el": mw}, row)
    request = best_deep[0]
    tag = f"{int(request['depth_m'])} m + ORC {request['orc_capacity_mw_el']:g} MW"
    sens = [
        ("export at import price (120)", {"electricity_export_price_eur_per_mwh": 120.0}),
        ("ORC cost 2,000 EUR/kW", {"orc_cost_eur_per_mw_el": 2.0e6}),
        ("ORC second-law fraction 0.54", {"orc_second_law_fraction": 0.54}),
        (
            "all three above",
            {
                "electricity_export_price_eur_per_mwh": 120.0,
                "orc_cost_eur_per_mw_el": 2.0e6,
                "orc_second_law_fraction": 0.54,
            },
        ),
    ]
    for label, over in sens:
        rows.append(run(f"C {tag}, {label}", request, over, demand))
        no_orc = {**request, "orc_capacity_mw_el": 0.0}
        rows.append(run(f"C {int(request['depth_m'])} m no ORC, {label}", no_orc, over, demand))
    for label, over in sens:
        rows.append(
            run(f"C pick + ORC 1 MW, {label}", {**PICK, "orc_capacity_mw_el": 1.0}, over, demand)
        )
    rows.append(run("C pick, all three above (no ORC)", PICK, sens[-1][1], demand))
    for mw in (2.0, 4.0):
        rows.append(
            run(
                f"D 3 doublets at 4500 m + ORC {mw:g} MW",
                {**PICK, "n_doublets": 3, "depth_m": 4500, "orc_capacity_mw_el": mw},
                None,
                demand,
            )
        )
    rows.append(
        run(
            "D 3 doublets at 4500 m (no ORC)",
            {**PICK, "n_doublets": 3, "depth_m": 4500},
            None,
            demand,
        )
    )

    with open(OUT / "runs.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    keys = (
        "case",
        "lcoe_eur_per_mwh",
        "co2_t",
        "all_rules_met",
        "capex_meur",
        "orc_mwh_el",
        "orc_full_load_hours",
        "orc_mean_efficiency_pct",
        "pumping_mwh",
        "purchased_gas_mwh",
        "grid_export_mwh",
    )
    lines = ["| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    lines += ["| " + " | ".join(str(r[k]) for k in keys) + " |" for r in rows]
    (OUT / "runs.md").write_text(
        "# ORC study, KNMI 2025 (Schiphol), staggered stops\n\n" + "\n".join(lines) + "\n"
    )
    cascade = cascade_table()
    with open(OUT / "cascade.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(cascade[0]))
        writer.writeheader()
        writer.writerows(cascade)
    for r in cascade:
        print(r)


if __name__ == "__main__":
    main()
