"""Physical plant model for the GEMINI GeoHackathon 2026 entry.

Layers
------
1. GEMINI (unchanged physics)   : producer well + ESP, separator, filters,
   injector well + pump, produced-gas boiler/CHP  -> ``build_well_table``
2. GEMINI HeatExchanger class    : brine -> district water (e-NTU, counter-flow)
3. Lorenz heat pump              : lifts district water to 100 C using the
   brine leaving the HEX as heat source.  Same equations as GEMINI's
   HeatpumpBasic (Lorenz mode); solved by bisection because HeatpumpBasic's
   fallback branch returns non-physical values when the source-outlet limit
   is active (see README, "Known GEMINI issues").
4. Chillers                      : absorption (driven by 100 C heat) and
   electric (Carnot-fraction COP at the 20 C supply), both cooling the
   chilled-water return to 20 C.
5. GEMINI HeatpumpBasic (fixed)  : re-solves every reported day as an
   independent cross-check of layer 3.

Every number that is not an official challenge value is a field of
``Assumptions`` or ``Design`` (or read from challenge_plant.json) - nothing
else is typed into the physics.

Per-doublet chain (all doublets identical, in parallel):

  reservoir -> producer(ESP) -> separator -> filter A -> HEX(primary)
            -> HP evaporator -> filter B -> injector -> reservoir
  district return (T_RETURN) -> HEX(secondary) -> HP condenser -> 100 C supply
  separator gas -> boiler (80 %) + CHP (20 %)   (heat to network, CHP power)
"""

from __future__ import annotations

import copy
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from gemini_simulator.project_loader import build_project  # noqa: E402
from gemini_model.heat_exchanger.heat_exchanger import HeatExchanger  # noqa: E402
from gemini_model.heatpump.heatpump_basic import HeatpumpBasic  # noqa: E402

# ─────────────────────────── official challenge values ──────────────────────
BRINE_DENSITY = 1030.0          # kg/m3
BRINE_VISCOSITY = 0.40e-3       # Pa s
SURFACE_TEMP = 12.0             # C
GEO_GRADIENT = 30.0             # C/km
REF_DEPTH, REF_PRESSURE = 2500.0, 250.0   # m TVD, bar(g)
PERMEABILITY_MD = 200.0
THICKNESS_M = 100.0
GLR = 0.8                       # Nm3 gas / m3 liquid (0 C, 1.01325 bar)
X_CH4, X_CO2 = 0.80, 0.20       # mol fractions
RHO_CH4_N, RHO_CO2_N = 0.7175, 1.9767     # kg/Nm3 at 0 C, 1.01325 bar
LHV_CH4_N = 35.88e6             # J/Nm3 CH4
MAX_BRINE_COOLING = 40.0        # C  T_producer - T_injector
MIN_FLOW_M3H, MAX_FLOW_M3H = 50.0, 300.0
PUMP_EFFICIENCY = 0.70
SUPPLY_TEMP_HEATING = 100.0     # C
SUPPLY_TEMP_COOLING = 20.0      # C
GEO_OPERATING_DAYS = 330
TOTAL_DAYS = 365
MAX_DOUBLETS = 3

# ─────────────────────────── physical constants ─────────────────────────────
CP_WATER = 4186.0               # J/kg/K, default for brine & water (not supplied)
KELVIN = 273.15
DARCY_M2_PER_MD = 9.869233e-16
PLANT_JSON = HERE / "challenge_plant.json"
_BASE_JSON = json.loads(PLANT_JSON.read_text())
# filter temperature drop is a GEMINI component parameter: read it, do not repeat it
FILTER_B_DROP = float(_BASE_JSON["components"]["filter_b"]["parameters"]["temperature_drop"])


def reservoir_temperature(depth_m):
    return SURFACE_TEMP + GEO_GRADIENT * depth_m / 1000.0          # 87 C at 2500 m


def reservoir_pressure(depth_m):
    # hydrostatic, anchored to the official 250 bar(g) at 2500 m
    return REF_PRESSURE * depth_m / REF_DEPTH


def productivity_index_m3h_bar(skin, r_drainage, r_well):
    """Pseudo-steady radial Darcy PI from k = 200 mD, h = 100 m, mu = 0.40 mPa s."""
    k = PERMEABILITY_MD * DARCY_M2_PER_MD
    pi_si = 2 * math.pi * k * THICKNESS_M / (BRINE_VISCOSITY * (math.log(r_drainage / r_well) - 0.75 + skin))
    return pi_si * 3600.0 * 1e5


# produced gas (per Nm3 of gas mixture)
GAS_RHO_N = X_CH4 * RHO_CH4_N + X_CO2 * RHO_CO2_N                 # 0.969 kg/Nm3
GAS_LHV_PER_KG = X_CH4 * LHV_CH4_N / GAS_RHO_N                   # J/kg mixture
# CO2 released per GJ of mixture fuel energy: combustion of CH4 + native CO2
GAS_CO2_PER_GJ = (X_CH4 * RHO_CO2_N + X_CO2 * RHO_CO2_N) / (X_CH4 * LHV_CH4_N / 1e9)


@dataclass
class Assumptions:
    """Every value the challenge does not supply. Listed in validation_report.txt."""
    # district heating / cooling networks
    t_return: float = 40.0              # C district heating return
    t_cool_return: float = 26.0         # C chilled-water return (supply is the official 20 C)
    # heat pump and chillers
    eta_lorenz: float = 0.50            # fraction of Lorenz COP (GEMINI HeatpumpBasic default)
    hp_cop_max: float = 15.0            # numerical cap when source and sink nearly coincide
    chiller_eta_carnot: float = 0.40    # electric chiller: fraction of Carnot COP
    chiller_condensing_c: float = 35.0  # C condenser temperature (summer ambient + approach)
    chiller_evap_approach_c: float = 3.0  # C evaporator below the 20 C supply
    cop_absorption: float = 0.70        # single-effect absorption, 100 C drive
    # fuels, grid and burners
    grid_ef_kg_per_kwh: float = 0.30    # same factor as GEMINI examples
    gas_ef_kg_per_gj: float = 56.6      # purchased natural gas
    backup_boiler_eff: float = 0.90     # backup boiler and produced-gas boiler
    chp_eff: float = 0.80               # GEMINI CHP efficiency_factor for produced gas
    produced_gas_to_boiler: float = 0.80  # share of produced gas to the boiler (rest to CHP)
    # wells and reservoir
    skin: float = 2.0                   # well skin for PI (0 = ideal)
    r_drainage_m: float = 600.0         # drainage radius for PI
    r_well_m: float = 0.10              # wellbore radius for PI
    tubing_id_m: float = 0.15           # well inner diameter (GEMINI example)
    survey_stations_m: tuple = (300.0, 500.0, 1000.0)  # trajectory stations above the reservoir
    wellbore_heat_loss_c: float = 7.0   # reservoir -> wellhead (87 -> 80 C as in GEMINI example)
    wellhead_pressure_bar: float = 3.0  # producer wellhead pressure (GEMINI example)
    min_esp_intake_bar: float = 10.0    # keep ESP intake above gas break-out
    esp_freq_min_hz: float = 15.0       # variable-speed range scanned by the dispatcher
    esp_freq_max_hz: float = 70.0
    esp_freq_step_hz: float = 2.5
    pvt_t_max_c: float = 200.0          # validity limit passed to GEMINI's PVT
    cp: float = CP_WATER                # J/kg/K brine & water


def electric_chiller_cop(a):
    """Carnot-fraction COP: evaporator just below the 20 C supply, condenser at ambient."""
    t_evap = SUPPLY_TEMP_COOLING - a.chiller_evap_approach_c + KELVIN
    t_cond = a.chiller_condensing_c + KELVIN
    return a.chiller_eta_carnot * t_evap / (t_cond - t_evap)


@dataclass
class Design:
    n_doublets: int = 2
    hex_ua_w_per_k: float = 400_000.0   # per doublet
    esp_stages: int = 40
    esp_depth_m: float = 1000.0
    well_depth_m: float = 2500.0        # TVD of both wells (reservoir midpoint)
    backup_boiler_mw: float = 35.0      # installed gas backup boiler (100 C)
    electric_chiller_mw: float = 12.0   # installed electric chiller (20 C)
    absorption_chiller_mw: float = 12.0 # installed absorption chiller (20 C, 100 C drive)

    def label(self):
        return (f"N={self.n_doublets} depth={self.well_depth_m:.0f}m UA={self.hex_ua_w_per_k/1e3:.0f}kW/K "
                f"stages={self.esp_stages} boiler={self.backup_boiler_mw:g}MW "
                f"chillers={self.electric_chiller_mw:g}+{self.absorption_chiller_mw:g}MW")


# ─────────────────────────── GEMINI well/gas layer ──────────────────────────


def build_well_table(design: Design, assumptions: Assumptions):
    """Run the GEMINI plant over ESP frequencies -> operating points.

    Pump electric power uses the official 70 % convention
    (P = dp * Q / 0.70); GEMINI's ESP-curve power is kept for reference.
    """
    a = assumptions
    base = copy.deepcopy(_BASE_JSON)
    z = design.well_depth_m
    t_res = reservoir_temperature(z)
    t_wh = t_res - a.wellbore_heat_loss_c
    pi = productivity_index_m3h_bar(a.skin, a.r_drainage_m, a.r_well_m)
    stations = [0.0] + [d for d in a.survey_stations_m if d < z] + [z]
    traj = [{"MD": d, "TVD": d, "ID": a.tubing_id_m} for d in stations]
    pvt = {"RHOL": BRINE_DENSITY, "VISL": BRINE_VISCOSITY, "temperature_max": a.pvt_t_max_c + KELVIN}
    c = base["components"]
    for w in ("producer_well", "injector_well"):
        wp = c[w]["parameters"]
        wp.update(reservoir_pressure_bar=reservoir_pressure(z), productivity_index_m3h_per_bar=pi,
                  trajectory_table=traj, pvt=pvt)
    c["producer_well"]["parameters"]["ambient_temperature_c"] = SURFACE_TEMP
    c["injector_well"]["parameters"]["injector_pump"]["efficiency_factor"] = PUMP_EFFICIENCY
    c["separator"]["parameters"].update(gas_water_ratio=GLR, gas_density=GAS_RHO_N)
    for b in ("boiler", "chp"):
        c[b]["parameters"].update(caloric_value=GAS_LHV_PER_KG, gas_emission_factor=GAS_CO2_PER_GJ)
    c["boiler"]["parameters"]["efficiency_factor"] = a.backup_boiler_eff
    c["chp"]["parameters"]["efficiency_factor"] = a.chp_eff
    c["gas_splitter"]["parameters"]["split_fractions"] = [a.produced_gas_to_boiler, 1 - a.produced_gas_to_boiler]
    for bi in base["boundary_inputs"]:
        if bi["component"] == "producer_well" and bi["key"] == "wellhead_temperature":
            bi["value"] = t_wh
        if bi["component"] == "producer_well" and bi["key"] == "wellhead_pressure":
            bi["value"] = a.wellhead_pressure_bar
    freqs = np.arange(a.esp_freq_min_hz, a.esp_freq_max_hz + 1e-9, a.esp_freq_step_hz)
    rows = []
    for f in freqs:
        p = copy.deepcopy(base)
        pw = p["components"]["producer_well"]["parameters"]
        pw["esp_freq_hz"] = float(f)
        pw["esp"]["no_stages"] = design.esp_stages
        pw["esp_depth_m"] = design.esp_depth_m
        try:
            s = build_project(p)
            s.run()
        except Exception:
            continue
        g = s.get_output
        q = g("producer_well", "flow_rate")
        intake = g("producer_well", "esp_intake_pressure")
        if not (MIN_FLOW_M3H <= q <= MAX_FLOW_M3H) or intake < assumptions.min_esp_intake_bar:
            continue
        dp_bar = g("producer_well", "esp_discharge_pressure") - intake
        q_m3s = q / 3600.0
        gas_in = g("separator", "gas_mass_flow_rate")
        rows.append(dict(
            t_wellhead=t_wh, t_reservoir=t_res, pi_m3h_bar=pi,
            gas_kg_s=gas_in,
            gas_to_burners_kg_s=g("gas_splitter", "output_0") + g("gas_splitter", "output_1"),
            gas_ch4_nm3_h=q * GLR * X_CH4,
            esp_freq_hz=float(f),
            q_m3h=q,
            q_inj_m3h=g("injector_well", "flow_rate_m3s") * 3600.0,
            esp_intake_bar=intake,
            esp_dp_bar=dp_bar,
            esp_power_w=dp_bar * 1e5 * q_m3s / PUMP_EFFICIENCY,
            esp_power_gemini_curve_w=g("producer_well", "esp_power_el"),
            inj_pump_w=g("injector_well", "power_el"),
            inj_hydraulic_w=q_m3s * max(0.0, g("injector_well", "wellhead_pressure_pa")
                                        - g("filter_b", "pressure_out_pa")),
            t_hex_in=g("filter_a", "temperature_out"),
            gas_heat_w=g("boiler", "power_th") + g("chp", "power_th"),
            chp_el_w=g("chp", "power_el"),
            gas_co2_kg_s=g("boiler", "emission") + g("chp", "emission"),
        ))
    return rows


# ─────────────────────────── heat pump (Lorenz) ─────────────────────────────
def _lmt(t_in_c, t_out_c):
    a, b = t_in_c + KELVIN, t_out_c + KELVIN
    return a if abs(a - b) < 1e-6 else (a - b) / math.log(a / b)


def heat_pump(th_in, mh, ts_in, ms, eta, ts_min, cop_max, th_out=SUPPLY_TEMP_HEATING, cp=CP_WATER):
    """Solve Lorenz HP for source outlet temperature.

    Returns dict(Q_h, W, Q_s, COP, Ts_out) or None if 100 C is unreachable
    without cooling the brine below ``ts_min``.
    """
    q_h = mh * cp * max(th_out - th_in, 0.0)
    if q_h <= 0:
        return dict(Q_h=0.0, W=0.0, Q_s=0.0, COP=float("nan"), Ts_out=ts_in)
    th_lm = _lmt(th_in, th_out)

    def cop(ts_out):
        ts_lm = _lmt(ts_in, ts_out)
        return min(eta * th_lm / max(th_lm - ts_lm, 1e-6), cop_max)

    def resid(ts_out):  # source heat taken from brine minus heat HP needs
        return ms * cp * (ts_in - ts_out) - q_h * (1 - 1 / cop(ts_out))

    if ts_in <= ts_min or resid(ts_min) < 0:
        return None
    lo, hi = ts_min, ts_in          # resid(lo) >= 0, resid(hi) < 0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if resid(mid) >= 0:
            lo = mid
        else:
            hi = mid
    ts_out = 0.5 * (lo + hi)
    c = cop(ts_out)
    return dict(Q_h=q_h, W=q_h / c, Q_s=q_h * (1 - 1 / c), COP=c, Ts_out=ts_out)


# ─────────────────────────── one doublet, one load ──────────────────────────
def doublet_point(row, design: Design, a: Assumptions, m_w):
    """HEX + HP for one doublet at district-water mass flow m_w [kg/s]."""
    q_m3s = row["q_m3h"] / 3600.0
    m_b = q_m3s * BRINE_DENSITY
    hx = HeatExchanger()
    hx.update_parameters(dict(flow_resistance=0.0, flow_configuration="counter",
                              heat_transfer_coefficient=design.hex_ua_w_per_k,
                              fluid_density=BRINE_DENSITY, specific_heat=a.cp))
    # secondary given as brine-equivalent volume so mass flow is exact
    # flow_resistance is 0, so pressure_in only passes through the HEX unchanged
    hx.calculate_output(dict(pressure_in=a.wellhead_pressure_bar * 1e5, primary_flow_rate=q_m3s,
                             secondary_flow_rate=m_w / BRINE_DENSITY,
                             primary_temperature_in=row["t_hex_in"],
                             secondary_temperature_in=a.t_return))
    o = dict(hx.get_output())
    if o["secondary_temperature_out"] > SUPPLY_TEMP_HEATING:
        # hot brine (deep wells): HEX bypass trims the water to exactly 100 C
        o["heat_duty"] = m_w * a.cp * (SUPPLY_TEMP_HEATING - a.t_return)
        o["secondary_temperature_out"] = SUPPLY_TEMP_HEATING
        o["primary_temperature_out"] = row["t_hex_in"] - o["heat_duty"] / (m_b * a.cp)
    ts_min = row["t_wellhead"] - MAX_BRINE_COOLING + FILTER_B_DROP     # injector >= T_prod - 40 C
    hp = heat_pump(o["secondary_temperature_out"], m_w, o["primary_temperature_out"], m_b, a.eta_lorenz, ts_min, a.hp_cop_max, cp=a.cp)
    if hp is None or hp["Ts_out"] < ts_min - 1e-9:
        return None
    t_inj = hp["Ts_out"] - FILTER_B_DROP
    t_supply = o["secondary_temperature_out"] + hp["Q_h"] / (m_w * a.cp)   # computed, not set
    q_delivered = m_w * a.cp * (SUPPLY_TEMP_HEATING - a.t_return)
    q_geo = m_b * a.cp * (row["t_hex_in"] - hp["Ts_out"])
    closure = q_delivered - (o["heat_duty"] + hp["Q_h"])          # network side
    closure_src = q_geo - (o["heat_duty"] + hp["Q_s"])             # brine side
    return dict(m_w=m_w, t_mid=o["secondary_temperature_out"], t_b1=o["primary_temperature_out"],
                q_hex=o["heat_duty"], q_hp=hp["Q_h"], w_hp=hp["W"], cop=hp["COP"],
                t_source_out=hp["Ts_out"], t_inj=t_inj, t_supply=t_supply, m_b=m_b,
                q_delivered=q_delivered, q_geo=q_geo,
                closure_w=max(abs(closure), abs(closure_src)))


def capacity_curve(row, design, a, n_grid=30):
    """Max district flow at 100 C for one doublet + interpolation grid."""
    # upper bracket: all allowed brine heat, multiplied up by the best possible heat pump
    m_b = row["q_m3h"] / 3600.0 * BRINE_DENSITY
    q_max = m_b * a.cp * MAX_BRINE_COOLING * a.hp_cop_max / (a.hp_cop_max - 1)
    lo, hi = 0.0, 1.01 * q_max / (a.cp * (SUPPLY_TEMP_HEATING - a.t_return))
    if doublet_point(row, design, a, hi) is not None:
        m_max = hi
    else:
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if doublet_point(row, design, a, mid) is not None:
                lo = mid
            else:
                hi = mid
        m_max = lo
    grid = np.linspace(0.0, m_max, n_grid)
    pts = [doublet_point(row, design, a, m) if m > 0 else None for m in grid]
    w = np.array([p["w_hp"] if p else 0.0 for p in pts])
    tinj = np.array([p["t_inj"] if p else row["t_hex_in"] - FILTER_B_DROP for p in pts])
    return dict(m_max=m_max, grid=grid, w_hp=w, t_inj=tinj)


def gemini_heat_pump_check(pt, a, ts_min):
    """Re-solve one day's heat pump with GEMINI's (fixed) HeatpumpBasic."""
    if pt is None or pt["q_hp"] <= 0:
        return None
    hp = HeatpumpBasic()
    hp.update_parameters(dict(mode="lorenz", eta_lorenz=a.eta_lorenz, Cp_h=a.cp, Cp_s=a.cp,
                              rho_h=BRINE_DENSITY, rho_s=BRINE_DENSITY,
                              Th_out_target=SUPPLY_TEMP_HEATING, Ts_in_minimum=ts_min))
    with np.errstate(invalid="ignore", divide="ignore"):   # Nelder-Mead probes log(<0) internally
        hp.calculate_output(dict(Th_in=pt["t_mid"], Ts_in=pt["t_b1"], hot_flow_rate=pt["m_w"] / BRINE_DENSITY,
                                 source_flow_rate=pt["m_b"] / BRINE_DENSITY))
    return hp.get_output()
