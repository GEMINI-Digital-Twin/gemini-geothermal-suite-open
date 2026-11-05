"""GeoBalance surface tools (author: Misghana; hand calculations).

Used by the agent next to GEMINI and as an independent cross-check of
GEMINI results. Units: MW, degC, m3/h, m, bar.
Every tool returns a dict with a 'warnings' list: limits are reported,
never silently capped, so the agent can see and fix them.
"""
import math

SURFACE_T = 12.0      # degC (given)
GRADIENT = 30.0       # degC/km (given)
RHO = 1030.0          # kg/m3 brine (given)
CP = 4000.0           # J/(kg K) brine, our assumption
MIN_FLOW, MAX_FLOW = 50.0, 300.0   # m3/h per doublet (given)
MAX_BRINE_DT = 40.0   # degC producer -> injector (given)
CO2_KG_PER_NM3 = 44.01 / 22.414    # kg CO2 per Nm3 of CH4 burned or CO2 released


def _mw(flow_m3h, dT):
    return flow_m3h / 3600 * RHO * CP * dT / 1e6


def _flow(mw, dT):
    return mw * 1e6 / (RHO * CP * dT) * 3600


def reservoir_temperature_c(depth_m=2500):
    return {"temperature_c": SURFACE_T + GRADIENT * depth_m / 1000, "warnings": []}


def doublet_heat_mw(flow_m3h=300, brine_cooling_c=40):
    w = []
    if flow_m3h > MAX_FLOW:
        w.append(f"Flow {flow_m3h:.0f} m3/h > max {MAX_FLOW:.0f} m3/h per doublet")
    if 0 < flow_m3h < MIN_FLOW:
        w.append(f"Flow {flow_m3h:.0f} m3/h < min stable {MIN_FLOW:.0f} m3/h")
    if brine_cooling_c > MAX_BRINE_DT:
        w.append(f"Brine cooling {brine_cooling_c:.0f} C > max {MAX_BRINE_DT:.0f} C")
    return {"heat_mw": _mw(flow_m3h, brine_cooling_c), "warnings": w}


def heat_pump(heat_demand_mw, cop=3.0):
    w = []
    if cop > 5.0:
        w.append(f"COP {cop} is optimistic for 100 C supply")
    return {"geothermal_heat_mw": heat_demand_mw * (cop - 1) / cop,
            "electricity_mw": heat_demand_mw / cop, "warnings": w}


def absorption_chiller(cooling_demand_mw, cop=0.7, t_in_c=87, drive_min_c=80, t_out_c=70):
    w = []
    if t_in_c < drive_min_c:
        w.append(f"Brine {t_in_c:.0f} C below chiller drive temperature {drive_min_c:.0f} C")
    heat = cooling_demand_mw / cop
    dT = max(t_in_c - t_out_c, 0.1)
    return {"geothermal_heat_mw": heat, "brine_flow_m3h": _flow(heat, dT),
            "brine_out_c": t_out_c, "warnings": w}


def electric_chiller(cooling_demand_mw, cop=5.0):
    return {"electricity_mw": cooling_demand_mw / cop, "warnings": []}


def summer_cascade(cooling_mw, heating_mw, n_doublets=2, flow_per_doublet=300,
                   t_res_c=87, hp_cop=3.0):
    """Chiller first (t_res -> 70 C), then heat pump on the rest (70 -> t_res-40)."""
    w = []
    flow = n_doublets * flow_per_doublet
    if flow_per_doublet > MAX_FLOW:
        w.append("Flow per doublet above 300 m3/h")
    abs_cool = min(cooling_mw, _mw(flow, t_res_c - 70) * 0.7)
    elec_cool = cooling_mw - abs_cool
    hp_source = _mw(flow, 70 - (t_res_c - MAX_BRINE_DT))
    hp = heat_pump(heating_mw, hp_cop)
    if hp["geothermal_heat_mw"] > hp_source:
        w.append("Heat pump source heat exceeds stage-2 brine heat")
    if elec_cool > 0:
        w.append(f"{elec_cool:.1f} MW cooling not covered by absorption -> electric chiller")
    return {"absorption_cooling_mw": abs_cool, "electric_chiller_cooling_mw": elec_cool,
            "electric_chiller_power_mw": electric_chiller(elec_cool)["electricity_mw"],
            "heat_pump_electricity_mw": hp["electricity_mw"], "warnings": w}


def gas_engine(flow_m3h, glr=0.8, ch4_fraction=0.8, lhv_kwh_nm3=9.97,
               el_eff=0.40, th_eff=0.45):
    """Associated gas -> gas engine. CO2 = burned CH4 + CO2 already in the gas."""
    gas_nm3h = flow_m3h * glr
    fuel = gas_nm3h * ch4_fraction * lhv_kwh_nm3 / 1000
    co2_t_h = gas_nm3h * CO2_KG_PER_NM3 / 1000   # all carbon in the gas ends up as CO2
    return {"electricity_mw": fuel * el_eff, "heat_mw": fuel * th_eff,
            "fuel_mw": fuel, "co2_t_per_h": co2_t_h, "warnings": []}


def doublet_pressure_and_pump(flow_m3h=300, perm_md=200, thickness_m=100,
                              visc_pa_s=0.4e-3, spacing_m=1500, rw_m=0.1,
                              p_res_bar=250, depth_m=2500,
                              wellhead_bar=10, friction_bar=5, pump_eff=0.70):
    """Doublet pressures + pump power (70% efficiency). Limits from P. Andersen (UiS).

    The reservoir pressure p_res_bar is also used as the static column pressure,
    so 250 bar is used consistently (given value).
    """
    w = []
    k = perm_md * 9.869e-16
    q = flow_m3h / 3600
    dp_total = q * visc_pa_s * math.log(spacing_m / rw_m) / (math.pi * k * thickness_m) / 1e5
    p_prod = p_res_bar - dp_total / 2
    p_inj = p_res_bar + dp_total / 2
    if p_prod < 0.75 * p_res_bar:
        w.append(f"Producer BHP {p_prod:.0f} bar below 75% of reservoir pressure")
    if p_inj > 1.25 * p_res_bar:
        w.append(f"Injector BHP {p_inj:.0f} bar above +25% (fracturing risk)")
    static = p_res_bar
    dp_prod_pump = max(0, static + wellhead_bar + friction_bar - p_prod)
    dp_inj_pump = max(0, p_inj + friction_bar - static)
    pump_mw = q * (dp_prod_pump + dp_inj_pump) * 1e5 / pump_eff / 1e6
    return {"total_dp_bar": round(dp_total, 1), "producer_bhp_bar": round(p_prod, 1),
            "injector_bhp_bar": round(p_inj, 1), "pump_power_mw": round(pump_mw, 2),
            "warnings": w}


if __name__ == "__main__":
    print(reservoir_temperature_c())
    print(doublet_heat_mw(350))
    print(summer_cascade(cooling_mw=10, heating_mw=2.7))
    print(gas_engine(600))
    print(doublet_pressure_and_pump())
