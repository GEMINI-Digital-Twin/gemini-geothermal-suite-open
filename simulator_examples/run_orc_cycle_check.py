"""Calibration check of the ORC model against a real subcritical cycle (CoolProp).

For each brine inlet, allowed brine cool-down and outdoor air temperature,
the cycle model searches the evaporation temperature of seven working
fluids (saturated vapour + 2 K superheat, 5 K evaporator pinch, condensing
15 K above the air, turbine 0.82, feed pump 0.70, generator 0.96,
condenser fans 1.5 % of the heat rejected) and keeps the best net power.
It then prints the second-law fraction this implies and the net efficiency
of gemini_model.orc (default 0.45) for the same brine outlet.

Needs CoolProp (pip install CoolProp), which the toolkit itself does not.

    $env:PYTHONPATH="src"
    python simulator_examples/run_orc_cycle_check.py

Writes simulator_examples/study_results/2026-11-03/orc/cycle_check.csv.
"""

import csv
import math
from pathlib import Path

import numpy as np
from CoolProp.CoolProp import PropsSI

from gemini_model.orc.orc import OrganicRankineCycle

FLUIDS = ["Isobutane", "n-Butane", "Isopentane", "R245fa", "R1233zd(E)", "R134a", "Propane"]
CP_B, RHO_B = 4180.0, 1030.0


def orc(
    t_in,
    flow_m3h,
    t_air,
    fluid,
    dt_max=40.0,
    pinch=5.0,
    itd=15.0,
    eta_t=0.82,
    eta_p=0.70,
    eta_g=0.96,
    fan=0.015,
    sh=2.0,
):
    m_b = flow_m3h / 3600 * RHO_B
    t_cond = t_air + itd + 273.15
    best = None
    try:
        p_c = PropsSI("P", "T", t_cond, "Q", 0, fluid)
        tcrit = PropsSI("Tcrit", fluid)
    except Exception:
        return None
    for t_ev_c in np.arange(t_air + itd + 10, min(t_in - pinch, tcrit - 273.15 - 5), 0.5):
        t_ev = t_ev_c + 273.15
        p_e = PropsSI("P", "T", t_ev, "Q", 1, fluid)
        h1 = PropsSI("H", "P", p_c, "Q", 0, fluid)
        s1 = PropsSI("S", "P", p_c, "Q", 0, fluid)
        h2s = PropsSI("H", "P", p_e, "S", s1, fluid)
        h2 = h1 + (h2s - h1) / eta_p
        h_bub = PropsSI("H", "P", p_e, "Q", 0, fluid)
        t3 = t_ev + sh
        if t3 > t_in + 273.15 - pinch:
            continue
        h3 = (
            PropsSI("H", "P", p_e, "T", t3, fluid)
            if sh > 0
            else PropsSI("H", "P", p_e, "Q", 1, fluid)
        )
        s3 = (
            PropsSI("S", "P", p_e, "T", t3, fluid)
            if sh > 0
            else PropsSI("S", "P", p_e, "Q", 1, fluid)
        )
        h4s = PropsSI("H", "P", p_c, "S", s3, fluid)
        h4 = h3 - eta_t * (h3 - h4s)
        # pinch at bubble point: brine temp there >= t_ev + pinch
        # brine energy: hot end t_in; working fluid mass from pinch
        # m_wf*(h3-h_bub) = m_b*cp*(t_in - t_pp), t_pp = t_ev_c + pinch
        t_pp = t_ev_c + pinch
        if t_pp >= t_in:
            continue
        m_wf = m_b * CP_B * (t_in - t_pp) / (h3 - h_bub)
        q_in = m_wf * (h3 - h2)
        t_out = t_in - q_in / (m_b * CP_B)
        if t_in - t_out > dt_max:  # cap brine cooling: scale down flow through the ORC
            # keep brine cool-down at dt_max: reduce m_wf
            m_wf = m_b * CP_B * dt_max / (h3 - h2)
            q_in = m_b * CP_B * dt_max
            t_out = t_in - dt_max
        w_t = m_wf * (h3 - h4) * eta_g
        w_p = m_wf * (h2 - h1)
        q_out = m_wf * (h4 - h1)
        w_fan = fan * q_out
        w_net = w_t - w_p - w_fan
        if best is None or w_net > best["w_net"]:
            best = dict(
                fluid=fluid,
                t_ev=t_ev_c,
                t_out=t_out,
                q_in=q_in,
                w_gross=w_t,
                w_pump=w_p,
                w_fan=w_fan,
                w_net=w_net,
                eta_net=w_net / q_in,
                eta_gross=w_t / q_in,
            )
    return best


def best_orc(t_in, flow, t_air, **kw):
    res = [r for f in FLUIDS if (r := orc(t_in, flow, t_air, f, **kw))]
    return max(res, key=lambda r: r["w_net"]) if res else None


OUT = Path(__file__).parent / "study_results" / "2026-11-03" / "orc"


def main():
    """Print and save the cycle vs model table."""
    model = OrganicRankineCycle()
    model.update_parameters({"capacity_net": 50e6, "plr_min": 0.0, "part_load_penalty": 0.0})
    rows = []
    for t_in in (75.0, 85.0, 95.0, 102.4, 110.0, 120.0, 130.0, 141.5):
        for dt in (10.0, 20.0, 40.0):
            for air in (0.0, 10.0, 20.0):
                r = best_orc(t_in, 300.0, air, dt_max=dt)
                if not r or r["w_net"] <= 0:
                    continue
                t_out = float(r["t_out"])
                ti, to, tc = t_in + 273.15, t_out + 273.15, air + 15.0 + 273.15
                exergy = (ti - to) - tc * math.log(ti / to)
                eps = r["eta_net"] * (ti - to) / exergy
                model.calculate_output(
                    {
                        "hot_temperature_in": t_in,
                        "hot_flow_rate": 300.0 / 3600.0,
                        "air_temperature": air,
                        "hot_temperature_out_min": t_out,
                    }
                )
                rows.append(
                    {
                        "brine_in_c": t_in,
                        "max_cooldown_k": dt,
                        "air_c": air,
                        "best_fluid": r["fluid"],
                        "cycle_brine_out_c": round(t_out, 1),
                        "cycle_net_mw": round(r["w_net"] / 1e6, 3),
                        "cycle_net_eff_pct": round(100 * r["eta_net"], 2),
                        "cycle_gross_eff_pct": round(100 * r["eta_gross"], 2),
                        "implied_second_law_fraction": round(eps, 3),
                        "model_net_eff_pct": round(100 * model.output["efficiency"], 2),
                    }
                )
                print(rows[-1], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "cycle_check.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
