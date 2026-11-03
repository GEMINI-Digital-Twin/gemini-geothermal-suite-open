"""Every brief constraint as one line (value, limit, pass/fail) from geo.year.checks, then the realised capacities read from 05 and 06."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from geo.common import PROJECT
from geo.year import checks, injection_pump_MW, table

N_DOUBLETS, T_RETURN_C = 2, 60.0
PROC = PROJECT / "data" / "processed"
d = pd.read_csv(PROC / "solution_05_dispatch_daily.csv", parse_dates=["date"]).set_index("date")
c = pd.read_csv(PROC / "solution_06_cooling_daily.csv", parse_dates=["date"]).set_index("date")
tab = table(T_RETURN_C)
gwh = lambda s: s.sum() * 24 / 1000
rows = checks(N_DOUBLETS, T_RETURN_C)

# injection pump electricity over the year, interpolated on the daily flow [C]
mw_inj = injection_pump_MW(d)
pk, cpk = d.demand.idxmax(), c.cold.idxmax()
caps = [
    ("heating capacity, 2 doublets at 300 m3/h", f"{2 * tab.out_max:.2f} MW", "[C]"),
    (f"heating at the peak {pk.date()}: exchanger / heat pump / boiler", f"{d.geo[pk]:.2f} / {d.hp[pk]:.2f} / {d.boiler[pk]:.2f} MW", "[C]"),
    ("heating energy: exchanger / heat pump (el) / boiler", f"{gwh(d.geo):.2f} / {gwh(d.hp):.2f} ({gwh(d.el_hp):.2f}) / {gwh(d.boiler):.2f} GWh", "[C]"),
    ("backup boiler capacity (N-1)", "16 MW, 0 GWh", "[L, research/04]"),
    (f"cooling at the peak {cpk.date()}: free / absorption / electric", f"{c.free[cpk]:.2f} / {c.absorption[cpk]:.2f} / {c.electric[cpk]:.2f} MW", "[C, A]"),
    ("cooling, max daily MW by source: free / absorption / electric", f"{c.free.max():.2f} / {c.absorption.max():.2f} / {c.electric.max():.2f} MW", "[C, A]"),
    ("cooling energy: free / absorption / electric", f"{gwh(c.free):.2f} / {gwh(c.absorption):.2f} / {gwh(c.electric):.2f} GWh", "[C, A]"),
    ("electricity: ESP / heat pump / injection pump", f"{gwh(d.esp):.2f} / {gwh(d.el_hp):.2f} / {gwh(mw_inj):.2f} GWh", "[C]"),
]

md = ["| constraint | value | limit | result |", "|---|---|---|---|"] + [f"| {r['name']} | {r['value']} | {r['limit']} | {r['status']} |" for r in rows]
md += ["", "| realised | value | tag |", "|---|---|---|"] + [f"| {a} | {b} | {t} |" for a, b, t in caps]
out = Path(__file__).resolve().parent / "tables"
out.mkdir(exist_ok=True)
(out / "08_checks.md").write_text("\n".join(md) + "\n")
print("\n".join(md))
print("wrote", out / "08_checks.md")
