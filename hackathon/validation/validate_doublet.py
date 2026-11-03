"""Three-way check of the doublet model at the 2,500 m baseline.

  A  GEMINI project mode: native project .json solved by gemini_simulator
     (ESP tuned to the target flow; example ESP curve, so <= ~240 m3/h)
  D  Design mode: GEMINI components (IPR, DPDT, injector) with our
     corrections and the brief's 70% pump efficiency
  C  Quick estimate by hand formulas (no GEMINI)

Leg B (reference hand calculation from the owner's references) is added
when those references are in.

Run from the repo root:
    PYTHONPATH=. python hackathon/validation/validate_doublet.py
"""

import math

from hackathon.models import gemini_project as gp
from hackathon.models import subsurface as sub
from hackathon.models.config import load_config

DEPTH = 2500


def quick_estimate(cfg, q):
    """Leg C: textbook formulas only."""
    t_res = cfg.surface_temp_c + cfg.gradient_c_per_m * DEPTH
    m = cfg.rho * q / 3600
    pi = sub.productivity_index_m3h_bar(cfg)
    v = (q / 3600) / (math.pi / 4 * cfg.well_id_m ** 2)
    re = cfg.rho * v * cfg.well_id_m / cfg.mu
    f = 0.25 / math.log10(1e-4 / (3.7 * cfg.well_id_m) + 5.74 / re ** 0.9) ** 2
    fric = f * DEPTH / cfg.well_id_m * cfg.rho * v ** 2 / 2 / 1e5
    hydro = cfg.rho * 9.81 * DEPTH / 1e5
    dp_prod = cfg.wellhead_pressure_bar + hydro + fric - (cfg.ref_pressure_bar - q / pi)
    p_inj = cfg.ref_pressure_bar + q / pi - hydro + fric
    return {
        "heat_40K_mw": m * cfg.cp * cfg.dt_brine_max / 1e6,
        "friction_bar": fric,
        "producer_pump_dp_bar": dp_prod,
        "producer_pump_mw": dp_prod * 1e5 * q / 3600 / cfg.pump_eff / 1e6,
        "injector_whp_bar": p_inj,
        "reservoir_t_c": t_res,
    }


def main():
    cfg = load_config()
    print(f"Baseline {DEPTH} m: T_res {sub.reservoir_temperature_c(cfg, DEPTH):.1f} C, "
          f"P_res {sub.reservoir_pressure_bar(cfg, DEPTH):.1f} bar, "
          f"PI {sub.productivity_index_m3h_bar(cfg):.2f} m3/h/bar\n")
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
        print(f"  heat at 40 K      D {d['geothermal_heat_mw']:.2f} MW   C {c['heat_40K_mw']:.2f} MW")
    return rows


if __name__ == "__main__":
    main()
