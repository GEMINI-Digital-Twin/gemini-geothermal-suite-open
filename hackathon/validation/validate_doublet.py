"""Three-way check of the doublet model at the 2,500 m baseline.

  A  GEMINI project mode: native project .json solved by gemini_simulator
     (ESP tuned to the target flow; GEMINI's example ESP, so <= ~240 m3/h)
  D  Design mode: GEMINI components (bottomhole_skin_dp, DPDT, injector) with
     our corrections and the brief's 70% pump efficiency
  C  Hand formulas only, no GEMINI code (Darcy-Weisbach with Haaland-type
     friction as in GEMINI's correlation; Thiem with r_e = L, DoubletCalc Eq. 7)

Run from the repo root:
    PYTHONPATH=. python hackathon/validation/validate_doublet.py
"""

import math

from hackathon.models import gemini_project as gp
from hackathon.models import subsurface as sub
from hackathon.models.config import load_config

DEPTH = 2500


def quick_estimate(cfg, q, spacing=None):
    """Leg C: textbook formulas only."""
    spacing = spacing or cfg.well_spacing_m
    k, h, mu, rw = cfg.permeability_m2, cfg.thickness_m, cfg.mu, cfg.well_id_m / 2
    pi = lambda s: 2 * math.pi * k * h / (mu * (math.log(spacing / rw) + s)) * 3600 * 1e5
    m = cfg.rho * q / 3600
    v = (q / 3600) / (math.pi / 4 * cfg.well_id_m ** 2)
    re = cfg.rho * v * cfg.well_id_m / cfg.mu
    f = 0.25 / math.log10(cfg.roughness_m / (3.7 * cfg.well_id_m) + 5.74 / re ** 0.9) ** 2
    fric = f * DEPTH / cfg.well_id_m * cfg.rho * v ** 2 / 2 / 1e5
    hydro = cfg.rho * 9.81 * DEPTH / 1e5
    p_res = cfg.ref_pressure_bar
    dp_prod = cfg.wellhead_pressure_bar + hydro + fric - (p_res - q / pi(cfg.skin_producer))
    p_inj = p_res + q / pi(cfg.skin_injector) - hydro + fric
    dp_inj = max(0.0, p_inj - (cfg.wellhead_pressure_bar - cfg.surface_loss_bar))
    return {
        "pi_producer": pi(cfg.skin_producer),
        "heat_40C_mw": m * cfg.cp * cfg.dt_brine_max / 1e6,
        "friction_bar": fric,
        "producer_pump_dp_bar": dp_prod,
        "producer_pump_mw": dp_prod * 1e5 * q / 3600 / cfg.pump_eff / 1e6,
        "injector_whp_bar": p_inj,
        "injection_pump_mw": dp_inj * 1e5 * q / 3600 / cfg.pump_eff / 1e6,
    }


def main():
    cfg = load_config()
    print(f"Baseline {DEPTH} m, spacing {cfg.well_spacing_m:.0f} m: T_res "
          f"{sub.reservoir_temperature_c(cfg, DEPTH):.1f} C, P_res {sub.reservoir_pressure_bar(cfg, DEPTH):.1f} bar, "
          f"PI (GEMINI bottomhole_skin_dp) {sub.productivity_index_m3h_bar(cfg):.2f} vs hand "
          f"{quick_estimate(cfg, 100)['pi_producer']:.2f} m3/h/bar\n")
    rows = []
    for q in (100, 150, 200, 300):
        d = sub.doublet_performance(cfg, DEPTH, q)
        c = quick_estimate(cfg, q)
        a = None
        if q <= 230:
            try:
                a, _ = gp.tune_esp_for_flow(cfg, DEPTH, q, esp_stages=15)
            except ValueError as exc:
                print("A failed:", exc)
        rows.append((q, a, d, c))
        print(f"--- Q = {q} m3/h")
        print(f"  wellhead T        D {d['wellhead_temperature_c']:.2f} C"
              + (f"   A input {a['wellhead_temperature_c']:.2f} C" if a else ""))
        print(f"  producer pump     D {d['pump_power_mw']:.3f} MW (dP {d['pump_dp_bar']:.1f} bar)"
              f"   C {c['producer_pump_mw']:.3f} MW (dP {c['producer_pump_dp_bar']:.1f} bar)"
              + (f"   A ESP curve {a['esp_power_mw']:.3f} MW @ {a['esp_freq_hz']:.1f} Hz" if a else ""))
        print(f"  injector WHP      D {d['injector_wellhead_pressure_corrected_bar']:.2f} bar"
              f"   C {c['injector_whp_bar']:.2f} bar"
              f"   GEMINI as-is {d['injector_wellhead_pressure_gemini_as_is_bar']:.2f} bar"
              + (f"   A {a['injector_wellhead_pressure_bar']:.2f} bar" if a else ""))
        print(f"  injection pump    D {d['injection_pump_power_mw']:.3f} MW   C {c['injection_pump_mw']:.3f} MW")
        print(f"  heat at 40 C drop D {d['geothermal_heat_mw']:.2f} MW   C {c['heat_40C_mw']:.2f} MW")
    return rows


if __name__ == "__main__":
    main()
