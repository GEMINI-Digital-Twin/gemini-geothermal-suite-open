"""Evaluate one plant design end to end, or compare a set of designs.

    python -m agentic_design.run_design --doublets 2 --depth 2500
    python -m agentic_design.run_design --compare

Outputs (folder ``agentic_design/results/<name>/``):
  kpis.json            annual KPIs
  findings.json        constraint check results (violations / warnings / info)
  daily.csv            365-day operation
  gemini_peak_day.json GEMINI simulator project file of the peak day (loadable as-is)
  verification.txt     fast model vs full GEMINI simulator on 3 days
  summary.txt          short human-readable summary
"""

import argparse
import json
import time
from pathlib import Path

from agentic_design.annual import PlantDesign, compare, run_year
from agentic_design.checks import check, summarize
from agentic_design.config import Assumptions
from agentic_design.plant_json import build_project_dict, save_project
from agentic_design.verify import format_report, operating_point, verify_days
from agentic_design.wells import WellDesign

RESULTS = Path(__file__).parent / "results"


def evaluate(design: PlantDesign, a: Assumptions = None, out_dir=None, verify=True) -> dict:
    a = a or Assumptions()
    t0 = time.time()
    daily, kpis, _, _ = run_year(design, a)
    findings = check(daily, kpis, design, a)
    from agentic_design.economics import economics
    result = {"kpis": kpis, "findings": findings, "counts": summarize(findings),
              "economics": economics(design, daily, kpis, a), "runtime_s": round(time.time() - t0, 3)}
    if verify:
        v = verify_days(design, daily, a, ua_mw_k=kpis["hx_ua_mw_k"])
        result["gemini_verification_passed"] = bool(v["pass"].all())
        result["verification_report"] = format_report(v)
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "kpis.json").write_text(json.dumps(kpis, indent=2, default=float))
        (out / "findings.json").write_text(json.dumps(findings, indent=2))
        (out / "economics.json").write_text(json.dumps(result["economics"], indent=2, default=float))
        daily.to_csv(out / "daily.csv", index=False)
        peak = int(daily["heating_mw"].idxmax())
        save_project(build_project_dict(design, operating_point(daily.loc[peak], a), a,
                                        hx_ua_w_k=kpis["hx_ua_mw_k"] * 1e6), out / "gemini_peak_day.json")
        if verify:
            (out / "verification.txt").write_text(result["verification_report"])
        (out / "summary.txt").write_text(summary_text(design, result))
    return result


def summary_text(design, r) -> str:
    k = r["kpis"]
    lines = [
        design.describe(),
        f"Heating {k['heating_demand_gwh']:.1f} GWh: geothermal {k['heating_geothermal_gwh']:.1f} "
        f"({k['geothermal_share_of_heating']:.0%}), associated gas {k['heating_assoc_gas_gwh']:.1f}, "
        f"natural gas {k['heating_natural_gas_gwh']:.1f}, unmet {k['heating_unmet_gwh']:.2f}",
        f"Cooling {k['cooling_demand_gwh']:.1f} GWh, unmet {k['cooling_unmet_gwh']:.1f}",
        f"Pump electricity {k['pump_electricity_gwh']:.2f} GWh | CO2 {k['co2_t']:,.0f} t "
        f"({k['co2_kg_per_mwh_heat']:.0f} kg/MWh heat)",
        f"Flow per doublet {k['min_active_q_per_doublet_m3h']:.0f}-{k['max_q_per_doublet_m3h']:.0f} m3/h, "
        f"max brine cooling {k['max_brine_cooling_c']:.1f} degC, operating days {k['operating_days_per_doublet']}, "
        f"maintenance from {k['maintenance_start_dates']}",
        f"HX UA {k['hx_ua_mw_k']:.2f} MW/K | checks: {r['counts']}",
    ]
    if "economics" in r:
        e = r["economics"]
        lines.append(f"Investment {e['capex_meur']:.1f} MEUR (wells {e['capex_breakdown_meur']['wells']:.1f}) | "
                     f"cost {e['lcoe_eur_per_mwh']:.1f} EUR/MWh, {e['lcoe_with_co2_eur_per_mwh']:.1f} with CO2 price | "
                     f"backup boilers {e['boiler_capacity_mw']:.1f} MW (N-1) | "
                     f"{e['lcoe_with_shadow_co2_eur_per_mwh']:.1f} EUR/MWh with CO2 valued at "
                     f"{e['cost_assumptions']['co2_shadow_eur_per_t']:.0f} EUR/t")
    if "gemini_verification_passed" in r:
        lines.append(f"GEMINI verification: {'PASS' if r['gemini_verification_passed'] else 'CHECK'}")
    for f in r["findings"]:
        if f["severity"] != "info":
            lines.append(f"  [{f['severity']}] {f['code']}: {f['message']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default=None)
    ap.add_argument("--doublets", type=int, default=2)
    ap.add_argument("--depth", type=float, default=2500.0)
    ap.add_argument("--id", type=float, default=0.20, help="well inner diameter, m")
    ap.add_argument("--esp-depth", type=float, default=650.0)
    ap.add_argument("--hp", type=float, default=0.0, help="heat pump size, MW")
    ap.add_argument("--abs", type=float, default=0.0, help="absorption chiller size, MW cooling")
    ap.add_argument("--ec", type=float, default=0.0, help="electric chiller size, MW cooling")
    ap.add_argument("--ri", action="store_true", help="reinject associated gas not needed by the boilers")
    ap.add_argument("--return-temp", type=float, default=None, help="network return temperature, degC")
    ap.add_argument("--compare", action="store_true", help="compare 1-3 doublets at 2500/3000/3500 m")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()
    a = Assumptions()
    if args.return_temp is not None:
        a.heating_return_temperature_c = args.return_temp

    if args.compare:
        designs = [PlantDesign(f"{n}x{int(z)}m", n, WellDesign(depth_m=z))
                   for z in (2500.0, 3000.0, 3500.0) for n in (1, 2, 3)]
        tab = compare(designs, a)
        cols = ["geothermal_share_of_heating", "heating_natural_gas_gwh", "pump_electricity_gwh", "co2_t",
                "max_brine_cooling_c", "max_q_per_doublet_m3h", "hx_ua_mw_k"]
        print(tab[cols].round(3).to_string())
        RESULTS.mkdir(exist_ok=True)
        tab.to_csv(RESULTS / "comparison.csv")
        return

    from agentic_design.agent.tools import ToolBox
    name = args.name or ToolBox.canonical_name(args.doublets, args.depth, args.id, args.esp_depth, args.hp, args.abs,
                                               args.ec, args.ri)
    design = PlantDesign(name, args.doublets, WellDesign(args.depth, args.id, args.esp_depth),
                         heat_pump_mw=args.hp, absorption_mw=args.abs, electric_chiller_mw=args.ec, gas_reinjection=args.ri)
    r = evaluate(design, a, RESULTS / name, verify=not args.no_verify)
    print(summary_text(design, r))
    print(f"\nFiles written to {RESULTS / name}")


if __name__ == "__main__":
    main()
