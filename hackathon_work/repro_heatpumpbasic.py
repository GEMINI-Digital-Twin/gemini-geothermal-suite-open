"""Minimal repro of three gemini_model.heatpump.HeatpumpBasic problems (no src/ edits).

Run in GEMINI repository root:
    $env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/repro_heatpumpbasic.py

Inputs are operating points from the hackathon daily model (brine 1030 kg/m3,
cp 4100 J/kg/K, Lorenz eta 0.5, sink out 100 C). For each case the expected
answer from the model's own two equations (Lorenz COP + energy balance),
solved with a bracketing root finder, is printed next to HeatpumpBasic's.
"""

import math
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gemini_model.heatpump.heatpump_basic import HeatpumpBasic  # noqa: E402
from scipy.optimize import brentq  # noqa: E402

warnings.filterwarnings("ignore", category=RuntimeWarning)
RHO, CP, ETA, TARGET = 1030.0, 4100.0, 0.5, 100.0
K = 273.15


def heatpump(ts_in_minimum):
    hp = HeatpumpBasic()
    hp.update_parameters({"mode": "lorenz", "eta_lorenz": ETA, "COP_0": 3.0, "Cp_h": CP, "Cp_s": CP,
                          "rho_h": RHO, "rho_s": RHO, "Th_out_target": TARGET, "Ts_in_minimum": ts_in_minimum})
    return hp


def reference(th_in, ts_in, hot_m3s, src_m3s):
    """Same equations, root-solved: COP = eta*Th/(Th-Ts) = Qh/(Qh-Qs), Th_out = target."""
    qh = CP * RHO * hot_m3s * (TARGET - th_in)

    def cop(ts_out):
        th = (TARGET - th_in) / math.log((TARGET + K) / (th_in + K))
        ts = (ts_in - ts_out) / math.log((ts_in + K) / (ts_out + K))
        return ETA * th / (th - ts)

    ts_out = brentq(lambda t: CP * RHO * src_m3s * (ts_in - t) - qh * (1 - 1 / cop(t)), ts_in - qh / (CP * RHO * src_m3s), ts_in - 1e-9)
    return {"COP": cop(ts_out), "Th_out": TARGET, "Ts_out": ts_out}


def show(label, y):
    print(f"  {label:28} COP={y['COP']:9.4f}  Th_out={y['Th_out']:9.2f} C  Ts_out={y['Ts_out']:8.2f} C")


def main():
    print("1) Ts_in_minimum fallback (source-limited): Th_out runs away")
    u = {"Th_in": 61.5, "Ts_in": 62.0, "hot_flow_rate": 0.1776, "source_flow_rate": 50 / 3600}
    hp = heatpump(ts_in_minimum=39.67)
    hp.calculate_output(dict(u))
    show("HeatpumpBasic:", hp.get_output())
    print("  expected: Th_out <= 100 C (the target) with Ts_out = Ts_in_minimum = 39.67 C;")
    print("  physically, 50 m3/h of 62 C brine cooled to 39.67 C supplies ~1.3 MW of source heat.")

    print("2) Primary solve (no source limit hit) diverges at low lift")
    u = {"Th_in": 85.34, "Ts_in": 82.94, "hot_flow_rate": 0.00793, "source_flow_rate": 300 / 3600}
    hp = heatpump(ts_in_minimum=-50.0)
    hp.calculate_output(dict(u))
    show("HeatpumpBasic:", hp.get_output())
    show("same equations, root-solved:", reference(u["Th_in"], u["Ts_in"], u["hot_flow_rate"], u["source_flow_rate"]))
    u = {"Th_in": 68.31, "Ts_in": 69.37, "hot_flow_rate": 0.0889 * 0.1, "source_flow_rate": 176 / 3600}
    hp.calculate_output(dict(u))
    show("HeatpumpBasic (small sink):", hp.get_output())
    show("same equations, root-solved:", reference(u["Th_in"], u["Ts_in"], u["hot_flow_rate"], u["source_flow_rate"]))
    u = {"Th_in": 77.85, "Ts_in": 79.0, "hot_flow_rate": 0.0889, "source_flow_rate": 295 / 3600}
    hp.calculate_output(dict(u))
    show("HeatpumpBasic (converges):", hp.get_output())
    show("same equations, root-solved:", reference(u["Th_in"], u["Ts_in"], u["hot_flow_rate"], u["source_flow_rate"]))

    print("3) get_output() returns the internal dict: earlier results are overwritten")
    hp = heatpump(ts_in_minimum=-50.0)
    hp.calculate_output({"Th_in": 77.85, "Ts_in": 79.0, "hot_flow_rate": 0.0889, "source_flow_rate": 295 / 3600})
    first = hp.get_output()
    cop_first = first["COP"]
    hp.calculate_output({"Th_in": 70.0, "Ts_in": 79.0, "hot_flow_rate": 0.0889, "source_flow_rate": 295 / 3600})
    print(f"  first result COP when returned: {cop_first:.4f}; same object after a second call: {first['COP']:.4f}")
    print(f"  first is hp.output: {first is hp.output}  (gemini_model.model_abstract.Model.get_output returns a copy)")


if __name__ == "__main__":
    main()
