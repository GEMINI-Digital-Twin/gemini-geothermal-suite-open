"""GEMINI GeoHackathon 2026 — full-year simulation of the selected design.

Reads agent_best_design.json (agent.py), else best_design.json (optimize_design.py), else
the built-in default) and simulates all 365 days with the official 2027 demand profiles,
runs the independent validator and writes:

    results_daily.csv       365 rows, every flow/temperature/power per day
    results_summary.csv     annual KPIs
    validation_report.txt   pass/fail of every challenge constraint
    plots/*.png             dispatch, temperatures, design comparison

Run:  python run_full_year.py
"""

import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from plant_model import Assumptions, Design
from dispatch import Plant, load_demand, summarize, validate

HERE = Path(__file__).resolve().parent


def load_design(path=None):
    """Design to report: --design file, else the agent's choice, else the grid-search best."""
    candidates = [Path(path)] if path else [HERE / "agent_best_design.json", HERE / "best_design.json"]
    for f in candidates:
        if f.exists():
            j = json.loads(f.read_text())
            print(f"Design source: {f.name}" + (f" ({j['agent']}, iteration {j['iteration']})" if "agent" in j else ""))
            return Design(**j["design"]), Assumptions(**j["assumptions"])
    print("Design source: built-in default")
    return Design(n_doublets=3, well_depth_m=3500, hex_ua_w_per_k=2.0e6, esp_stages=50,
                  backup_boiler_mw=4.5, electric_chiller_mw=10.5, absorption_chiller_mw=9), Assumptions()


def make_plots(df, out, cop_abs=0.7):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out.mkdir(exist_ok=True)
    x = pd.to_datetime(df.date)

    fig, ax = plt.subplots(figsize=(12, 5))
    hp_el = df.hp_elec_MW
    ax.stackplot(x, df.heat_hex_MW, df.heat_hp_MW - hp_el, hp_el, df.heat_produced_gas_MW, df.heat_backup_boiler_MW,
                 labels=["Geothermal via HEX", "Geothermal via heat pump (source)", "Heat pump electricity",
                         "Produced-gas boiler/CHP", "Backup gas boiler"],
                 colors=["#c0392b", "#e67e22", "#f1c40f", "#7f8c8d", "#34495e"], alpha=0.9)
    ax.plot(x, df.heating_demand_MW, color="black", lw=1.2, label="Heating demand")
    drive = df.heating_demand_MW + df.cooling_absorption_MW / cop_abs
    ax.plot(x, drive, color="#2980b9", lw=0.8, ls="--", label="+ absorption-chiller drive heat")
    ax.set_ylabel("MW (daily mean)")
    ax.set_title("Heating supply at 100 C by source, 2027")
    ax.legend(loc="upper center", ncol=3, fontsize=8)
    ax.margins(x=0)
    fig.tight_layout(); fig.savefig(out / "heating_dispatch.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.stackplot(x, df.cooling_absorption_MW, df.cooling_electric_MW,
                 labels=["Absorption chiller (geothermal heat)", "Electric chiller"],
                 colors=["#2980b9", "#95a5a6"])
    ax.plot(x, df.cooling_demand_MW, color="black", lw=1.2, label="Cooling demand")
    ax.set_ylabel("MW (daily mean)"); ax.set_title("Cooling supply at 20 C, 2027")
    ax.legend(loc="upper left", fontsize=8); ax.margins(x=0)
    fig.tight_layout(); fig.savefig(out / "cooling_dispatch.png", dpi=130); plt.close(fig)

    fig, ax1 = plt.subplots(figsize=(12, 4))
    act = df.geothermal_active
    ax1.plot(x[act], df.flow_per_doublet_m3h[act], ".", ms=4, color="#16a085", label="Flow per doublet")
    ax1.axhline(50, ls="--", color="#16a085", lw=0.8); ax1.axhline(300, ls="--", color="#16a085", lw=0.8)
    ax1.set_ylabel("m3/h per doublet", color="#16a085")
    ax2 = ax1.twinx()
    ax2.plot(x[act], df.brine_cooling_C[act], ".", ms=4, color="#8e44ad", label="Brine cooling")
    ax2.axhline(40, ls="--", color="#8e44ad", lw=0.8)
    ax2.set_ylabel("Brine cooling (C)", color="#8e44ad"); ax2.set_ylim(0, 45)
    ax1.set_title("Operating envelope: flow (limits 50-300 m3/h) and brine cooling (limit 40 C)")
    ax1.margins(x=0)
    fig.tight_layout(); fig.savefig(out / "operating_envelope.png", dpi=130); plt.close(fig)

    comp_f = HERE / "design_comparison.csv"
    if comp_f.exists():
        comp = pd.read_csv(comp_f)
        best = comp[comp.feasible].groupby("n_doublets").co2_t_per_year.min()
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar([f"{n} doublet{'s' if n > 1 else ''}" for n in best.index], best.values,
               color=["#bdc3c7", "#95a5a6", "#c0392b"][:len(best)])
        for i, v in enumerate(best.values):
            ax.text(i, v, f"{v:,.0f} t", ha="center", va="bottom")
        ax.set_ylabel("Annual CO2 (t)"); ax.set_title("Best design per number of doublets")
        fig.tight_layout(); fig.savefig(out / "design_comparison.png", dpi=130); plt.close(fig)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", help="JSON file with a design (default: agent_best_design.json)")
    design, a = load_design(ap.parse_args().design)
    dates, H, C = load_demand(HERE)
    print(f"Simulating {design.label()} for 365 days ...")
    df = Plant(design, a).simulate_year(dates, H, C)
    df.round(4).to_csv(HERE / "results_daily.csv", index=False)

    s = summarize(df, design)
    checks = validate(df, design)
    s["constraint_checks_passed"] = f"{sum(ok for _, ok, _ in checks)}/{len(checks)}"
    pd.DataFrame([s]).to_csv(HERE / "results_summary.csv", index=False)

    lines = ["GEMINI GeoHackathon 2026 — Validation Report", "=" * 64, "",
             f"Design: {design.label()}  (ESP depth {design.esp_depth_m:.0f} m)",
             "All checks below are recomputed from results_daily.csv — none are hard-coded.", "",
             "CHALLENGE CONSTRAINTS", "-" * 64]
    lines += [f"  {'PASS' if ok else 'FAIL'}  {name:42s} {det}" for name, ok, det in checks]
    lines += ["", "ANNUAL PERFORMANCE", "-" * 64]
    lines += [f"  {k}: {v}" for k, v in s.items()]
    lines += ["", "ASSUMPTIONS (not supplied by the challenge)", "-" * 64]
    lines += [f"  {k}: {v}" for k, v in asdict(a).items()]
    (HERE / "validation_report.txt").write_text("\n".join(lines) + "\n")

    try:
        make_plots(df, HERE / "plots", a.cop_absorption)
        plots = "plots/*.png"
    except ImportError:
        plots = "(install matplotlib for plots)"

    print("\n".join(lines))
    print(f"\nWritten: results_daily.csv | results_summary.csv | validation_report.txt | {plots}")


if __name__ == "__main__":
    main()
