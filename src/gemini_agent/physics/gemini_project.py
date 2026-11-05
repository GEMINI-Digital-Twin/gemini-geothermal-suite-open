"""Compile a design into a native GEMINI simulator project and verify it.

``compile_project`` turns one doublet's operating point on a chosen day into a
``gemini_simulator`` project JSON (components / boundary_inputs / connections),
the format GEMINI's ``project_loader.build_project`` loads:

    producer_well (nodal solve, generated ESP) -> [separator] -> filter_a
      -> heat_exchanger -> [heat_pump source] -> filter_b -> injector_well (+ pump)
    DH water:  heat_exchanger secondary -> [splitter -> heat_pump hot side -> mixer] -> [boiler]

``verify_day`` runs it through GEMINI's ``Solver`` (high fidelity) and compares
flow, heat duties, temperatures and pump powers with the screening dispatch.

Automatic model generation: GEMINI's example ESP curve is fitted for ~130 m3/h
and is not valid at 300 m3/h, so a duty-matched ESP curve is generated here
(centrifugal head H = H0 (1 - (Q/Qmax)^2) per stage, power from eta = 70 %,
stage count and frequency solved for the design point) in GEMINI's own
polynomial-coefficient format.
"""

from __future__ import annotations

import json
import math

from scipy.optimize import brentq

from gemini_agent.physics.site import gas_properties
from gemini_agent.physics.wells import gemini_well_config, producer_point
from gemini_agent.service import Evaluation
from gemini_model.pump.esp import ESP
from gemini_simulator.project_loader import build_project
from gemini_simulator.well_flow import solve_primary_flow_m3h

BBLD = ESP.M3S_TO_BBLD
FT_PA = ESP.FT_HEAD_TO_PA
BHP_W = ESP.BHP_TO_WATT


def generate_esp(
    flow_m3h: float, pump_dp_bar: float, eta: float = 0.7, head0_ft: float = 60.0
) -> dict:
    """Duty-matched ESP in GEMINI's coefficient format (head ft/stage, power bhp/stage @ 60 Hz)."""
    qd = flow_m3h / 3600.0 * BBLD
    qmax = 2.0 * qd
    head_coeff = [head0_ft, 0.0, -head0_ft / qmax**2, 0.0, 0.0, 0.0]
    a1 = head0_ft * FT_PA / (BBLD * eta * BHP_W)
    power_coeff = [0.0, a1, 0.0, -a1 / qmax**2, 0.0, 0.0]
    head_stage_pa = head0_ft * (1 - (qd / qmax) ** 2) * FT_PA
    stages = max(1, math.ceil(pump_dp_bar * 1e5 / head_stage_pa * 1.10))
    return {
        "no_stages": stages,
        "head_coeff": head_coeff,
        "power_coeff": power_coeff,
        "electricity_emission_factor": 0.3,
    }


def compile_project(ev: Evaluation, day: int, brief) -> dict:
    """GEMINI project JSON for ONE doublet at the dispatch point of ``day``."""
    s, r = ev.spec, ev.result
    d = r.days[day]
    if d.n_on == 0:
        raise ValueError(f"No doublet produces on day {day}; pick another day.")
    from gemini_agent.physics.plant import PlantModel  # local import (cycle-free)

    plant = PlantModel(brief, s, peak_heat_mw=max(r.heat_mw))
    ws = plant.ws
    f = d.flow_per_doublet_m3h
    pp = producer_point(brief, s.well_depth_m, f, ws)
    cfg = gemini_well_config(brief, s.well_depth_m, ws)
    esp = generate_esp(f, pp.pump_dp_bar, brief.constraints["pump_efficiency"])
    prod = dict(cfg, esp_depth_m=pp.esp_setting_depth_m, esp=esp)
    prod.pop("ambient_temperature_c", None)
    prod["ambient_temperature_c"] = cfg["ambient_temperature_c"]

    def flow_at(freq):
        try:
            return (
                solve_primary_flow_m3h(
                    dict(prod, esp_freq_hz=freq),
                    ws.min_wellhead_pressure_bar,
                    d.wellhead_t_c,
                    cfg["ambient_temperature_c"],
                )
                - f
            )
        except ValueError:  # pump too weak at this frequency: no producing root
            return -f

    grid = [30.0 + 2.5 * i for i in range(25)]  # 30-90 Hz
    vals = [flow_at(fr) for fr in grid]
    lo = next((i for i in range(len(grid) - 1) if vals[i] < 0 <= vals[i + 1]), None)
    if lo is None:
        raise ValueError(f"Generated ESP cannot deliver {f:.0f} m3/h between 30 and 90 Hz: {vals}")
    prod["esp_freq_hz"] = brentq(flow_at, grid[lo], grid[lo + 1], xtol=1e-4)

    rho_b, cp_b = plant.rho_b, plant.cp_b
    t_r, t_sup = s.dh_return_temperature_c, s.heating_supply_temperature_c
    heat_w = (d.q_hex + d.q_hp + d.q_boiler) / d.n_on * 1e6
    m_dh = heat_w / (plant.cp_w * (t_sup - t_r))
    q_dh_eq = m_dh * plant.cp_w / (rho_b * cp_b)  # brine-equivalent volumetric flow
    use_sep = not plant.reinject
    use_hp = d.q_hp > 1e-6
    use_boiler = d.q_boiler > 1e-6
    x_hp = 1.0
    if use_hp:  # fraction of DH flow through the HP condenser (capacity limit)
        x_hp = min(
            1.0,
            (d.q_hp / d.n_on * 1e6)
            / max(
                1.0,
                m_dh * plant.cp_w * (t_sup - (t_r + d.q_hex / d.n_on * 1e6 / (m_dh * plant.cp_w))),
            ),
        )

    z_hex = 1.0  # fraction of DH flow through the HEX (3-way valve), sized to the dispatch duty
    target_hex_w = d.q_hex / d.n_on * 1e6
    if not use_hp and target_hex_w > 0:

        def hex_duty(z):
            return (
                plant._hex_run(plant.ua_per_doublet, d.wellhead_t_c, f / 3600.0, t_r, z * m_dh)[
                    "heat_duty"
                ]
                - target_hex_w
            )

        if hex_duty(1.0) > 1e3:  # unconstrained HEX would over-cool the brine
            z_hex = brentq(hex_duty, 1e-4, 1.0, xtol=1e-6)

    comps = {
        "producer_well": {"type": "producer_well", "parameters": prod},
        "filter_a": {
            "type": "filter",
            "parameters": {
                "base_resistance": 3.6,
                "fouling_coeff_a": 0.0,
                "fouling_coeff_b": 0.0,
                "temperature_drop": 0.0,
            },
        },
        "heat_exchanger": {
            "type": "heat_exchanger",
            "parameters": {
                "flow_resistance": 0.0,
                "flow_configuration": "counter",
                "heat_transfer_coefficient": plant.ua_per_doublet,
                "fluid_density": rho_b,
                "specific_heat": cp_b,
            },
        },
        "filter_b": {
            "type": "filter",
            "parameters": {
                "base_resistance": 3.6,
                "fouling_coeff_a": 0.0,
                "fouling_coeff_b": 0.0,
                "temperature_drop": 0.0,
            },
        },
        "injector_well": {
            "type": "injector_well",
            "parameters": dict(
                {k: v for k, v in cfg.items() if k != "ambient_temperature_c"},
                injector_pump={
                    "efficiency_factor": brief.constraints["pump_efficiency"],
                    "electricity_emission_factor": 0.3,
                },
            ),
        },
    }
    bnd = [
        {
            "component": "producer_well",
            "key": "wellhead_pressure",
            "value": ws.min_wellhead_pressure_bar,
        },
        {"component": "producer_well", "key": "wellhead_temperature", "value": d.wellhead_t_c},
        {"component": "heat_exchanger", "key": "secondary_temperature_in", "value": t_r},
        {"component": "heat_exchanger", "key": "secondary_flow_rate", "value": q_dh_eq * z_hex},
    ]
    con = []
    if use_sep:
        g = gas_properties(brief)
        comps["separator"] = {
            "type": "separator",
            "parameters": {
                "flow_resistance": 3.6,
                "temperature_drop": 0.0,
                "gas_water_ratio": g.gas_nm3_per_m3,
                "gas_density": g.mix_density_kg_per_nm3,
            },
        }
        con += [
            {
                "predecessor": "producer_well",
                "successor": "separator",
                "ports": [
                    ["flow_rate_m3s", "flow_rate"],
                    ["pressure_out", "pressure"],
                    ["temperature_out", "temperature"],
                ],
            },
            {
                "predecessor": "separator",
                "successor": "filter_a",
                "ports": [
                    ["pressure_out", "pressure"],
                    ["temperature_out", "temperature"],
                    ["flow_rate", "flow_rate"],
                ],
            },
        ]
    else:
        con += [
            {
                "predecessor": "producer_well",
                "successor": "filter_a",
                "ports": [
                    ["flow_rate_m3s", "flow_rate"],
                    ["pressure_out", "pressure"],
                    ["temperature_out", "temperature"],
                ],
            }
        ]
    con += [
        {
            "predecessor": "filter_a",
            "successor": "heat_exchanger",
            "ports": [
                ["pressure_out", "pressure_in"],
                ["temperature_out", "primary_temperature_in"],
                ["flow_rate", "primary_flow_rate"],
            ],
        }
    ]
    last_brine, last_brine_t = "heat_exchanger", "primary_temperature_out"
    dh_src, dh_t, dh_q = "heat_exchanger", "secondary_temperature_out", "secondary_flow_rate"
    if use_hp:
        comps["heat_pump"] = {
            "type": "heat_pump",
            "parameters": {
                "mode": "lorenz",
                "eta_lorenz": plant.econ["heat_pump_eta_lorenz"],
                "Th_out_target": t_sup,
                "Ts_in_minimum": d.wellhead_t_c - brief.constraints["max_brine_cooling_k"],
                "Cp_h": cp_b,
                "rho_h": rho_b,
                "Cp_s": cp_b,
                "rho_s": rho_b,
            },
        }
        comps["dh_splitter"] = {
            "type": "splitter",
            "parameters": {"split_fractions": [x_hp, 1 - x_hp]},
        }
        comps["dh_mixer"] = {"type": "mixer", "parameters": {"num_inputs": 2}}
        con += [
            {
                "predecessor": "heat_exchanger",
                "successor": "dh_splitter",
                "predecessor_output": "secondary_flow_rate",
                "successor_input": "input",
            },
            {
                "predecessor": "heat_exchanger",
                "successor": "heat_pump",
                "ports": [
                    ["secondary_temperature_out", "Th_in"],
                    ["primary_temperature_out", "Ts_in"],
                    ["primary_flow_rate", "source_flow_rate"],
                ],
            },
            {
                "predecessor": "dh_splitter",
                "successor": "heat_pump",
                "predecessor_output": "output_0",
                "successor_input": "hot_flow_rate",
            },
            {
                "predecessor": "heat_pump",
                "successor": "dh_mixer",
                "ports": [["hot_flow_rate", "input_0_flow"], ["Th_out", "input_0_temperature"]],
            },
            {
                "predecessor": "dh_splitter",
                "successor": "dh_mixer",
                "predecessor_output": "output_1",
                "successor_input": "input_1_flow",
            },
            {
                "predecessor": "heat_exchanger",
                "successor": "dh_mixer",
                "predecessor_output": "secondary_temperature_out",
                "successor_input": "input_1_temperature",
            },
        ]
        last_brine, last_brine_t = "heat_pump", "Ts_out"
        dh_src, dh_t, dh_q = "dh_mixer", "temperature", "flow"
    if z_hex < 1.0:  # DH bypass around the HEX (3-way valve) keeps brine cooling <= 40 K
        comps["dh_bypass_mixer"] = {"type": "mixer", "parameters": {"num_inputs": 2}}
        bnd += [
            {"component": "dh_bypass_mixer", "key": "input_1_flow", "value": q_dh_eq * (1 - z_hex)},
            {"component": "dh_bypass_mixer", "key": "input_1_temperature", "value": t_r},
        ]
        con.append(
            {
                "predecessor": "heat_exchanger",
                "successor": "dh_bypass_mixer",
                "ports": [
                    ["secondary_flow_rate", "input_0_flow"],
                    ["secondary_temperature_out", "input_0_temperature"],
                ],
            }
        )
        dh_src, dh_t, dh_q = "dh_bypass_mixer", "temperature", "flow"
    if use_boiler:
        lhv = gas_properties(brief).mix_lhv_mj_per_kg * 1e6
        gas_kg_s = d.q_boiler / d.n_on * 1e6 / plant.econ["boiler_efficiency_lhv"] / lhv
        comps["boiler"] = {
            "type": "boiler",
            "parameters": {
                "caloric_value": lhv,
                "efficiency_factor": plant.econ["boiler_efficiency_lhv"],
                "gas_emission_factor": 56.1,
                "fluid_density": rho_b,
                "specific_heat": cp_b,
            },
        }
        bnd.append({"component": "boiler", "key": "gas_flow_rate", "value": gas_kg_s})
        con.append(
            {
                "predecessor": dh_src,
                "successor": "boiler",
                "ports": [[dh_t, "temperature_in"], [dh_q, "water_flow_rate"]],
            }
        )
    con += [
        {
            "predecessor": last_brine,
            "successor": "filter_b",
            "ports": [[last_brine_t, "temperature"]],
        },
        {
            "predecessor": "heat_exchanger",
            "successor": "filter_b",
            "ports": [["pressure_out", "pressure"], ["primary_flow_rate", "flow_rate"]],
        },
        {
            "predecessor": "filter_b",
            "successor": "injector_well",
            "ports": [
                ["flow_rate_m3h", "flow_rate"],
                ["temperature_out", "wellhead_temperature"],
                ["pressure_out_pa", "pressure_in"],
            ],
        },
    ]
    return {
        "_description": f"GeoDesign export: one doublet of design {s.key()} ({s.label()}) on "
        f"{r.dates[day]}; generated by gemini_agent.physics.gemini_project.",
        "_units": "SI flow (m3/s) on the surface, m3/h for wells, bar, degC, W.",
        "components": comps,
        "boundary_inputs": bnd,
        "connections": con,
    }


def verify_day(ev: Evaluation, day: int, brief) -> dict:
    """Run the compiled project in GEMINI's Solver and compare with the screening result."""
    proj = compile_project(ev, day, brief)
    solver = build_project(json.loads(json.dumps(proj)))
    solver.run()
    d = ev.result.days[day]
    n = d.n_on
    g = solver.get_output
    hex_mw = g("heat_exchanger", "heat_duty") / 1e6
    hp_mw = g("heat_pump", "power_th") / 1e6 if "heat_pump" in proj["components"] else 0.0
    t_inj = g("filter_b", "temperature_out")
    esp_kw = g("producer_well", "esp_power_el") / 1e3
    inj_kw = g("injector_well", "power_el") / 1e3
    screening = {
        "flow_m3h": d.flow_per_doublet_m3h,
        "hex_mw": d.q_hex / n,
        "hp_mw": d.q_hp / n,
        "injection_t_c": d.injection_t_c,
    }
    gemini = {
        "flow_m3h": g("producer_well", "flow_rate"),
        "hex_mw": hex_mw,
        "hp_mw": hp_mw,
        "injection_t_c": t_inj,
        "esp_kw": esp_kw,
        "injection_pump_kw": inj_kw,
        "esp_freq_hz": proj["components"]["producer_well"]["parameters"]["esp_freq_hz"],
        "esp_stages": proj["components"]["producer_well"]["parameters"]["esp"]["no_stages"],
    }
    dev = {
        "flow_pct": 100 * (gemini["flow_m3h"] - screening["flow_m3h"]) / screening["flow_m3h"],
        "hex_pct": 100 * (hex_mw - screening["hex_mw"]) / max(1e-6, screening["hex_mw"]),
        "hp_pct": (
            100 * (hp_mw - screening["hp_mw"]) / max(1e-6, screening["hp_mw"]) if hp_mw else 0.0
        ),
        "injection_t_k": t_inj - screening["injection_t_c"],
    }
    ok = (
        abs(dev["flow_pct"]) < 1
        and abs(dev["hex_pct"]) < 3
        and abs(dev["hp_pct"]) < 5
        and abs(dev["injection_t_k"]) < 1
    )
    return {
        "date": ev.result.dates[day],
        "per_doublet": True,
        "screening": screening,
        "gemini_solver": gemini,
        "deviation": dev,
        "consistent": ok,
        "project": proj,
    }
