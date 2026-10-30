"""Daily annual simulation of a geothermal heating (and later cooling) plant.

One evaluation = 365 daily steady states. Per day the dispatcher decides how
many doublets run and at what flow, using the GEMINI-based doublet curves from
``wells.py``; the surface energy balance is a counter-flow heat exchanger with
a minimum approach temperature, followed by a top-up to the 100 degC supply.

Plant concept implemented today (baseline, extendable):

    producers -> separator (associated gas out) -> filters -> HX -> injectors
    network return -> HX secondary -> top-up -> 100 degC supply
    top-up = boiler on associated gas first, then purchased natural gas

Cooling is a placeholder (``cooling='none'``: cooling demand reported as
unmet) until the cooling models are added.
"""

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from agentic_design.config import CHALLENGE, Assumptions, gas_properties, load_demand
from agentic_design.wells import WellDesign, hydraulic_curve

Q_FINE = np.arange(CHALLENGE["min_flow_m3h_per_doublet"], CHALLENGE["max_flow_m3h_per_doublet"] + 0.5, 1.0)


@dataclass(frozen=True)
class PlantDesign:
    name: str = "baseline"
    n_doublets: int = 2
    well: WellDesign = field(default_factory=WellDesign)
    maintenance_start_doy: tuple = ()  # one 0-based start day per doublet; () = auto schedule
    topup: str = "gas_boiler"  # associated gas first, then purchased natural gas
    cooling: str = "none"
    hx_ua_mw_k: float = None  # heat exchanger size; None = size for min approach on the peak day

    def describe(self):
        return (f"{self.name}: {self.n_doublets} doublet(s), wells to {self.well.depth_m:.0f} m, "
                f"ID {self.well.inner_diameter_m:.2f} m, ESP at {self.well.esp_depth_m:.0f} m, "
                f"top-up={self.topup}, cooling={self.cooling}"
                + (f", HX UA {self.hx_ua_mw_k:.2f} MW/K" if self.hx_ua_mw_k else ""))


def schedule_maintenance(load_mw: np.ndarray, n_doublets: int, days: int) -> tuple:
    """Place one non-overlapping maintenance window per doublet where load is lowest."""
    n_days = len(load_mw)
    window = pd.Series(load_mw).rolling(days).sum().shift(-(days - 1)).to_numpy()  # sum starting at d
    starts, blocked = [], np.zeros(n_days, bool)
    for _ in range(n_doublets):
        cand = np.where(np.isnan(window), np.inf, window).copy()
        for s in range(n_days):
            if blocked[s:s + days].any():
                cand[s] = np.inf
        s = int(np.argmin(cand))
        starts.append(s)
        blocked[s:s + days] = True
    return tuple(starts)


def _availability(design: PlantDesign, n_days: int, a: Assumptions, load_mw: np.ndarray):
    starts = design.maintenance_start_doy or schedule_maintenance(
        load_mw, design.n_doublets, a.maintenance_days_per_doublet)
    avail = np.ones((n_days, design.n_doublets), bool)
    for i, s in enumerate(starts):
        avail[s:s + a.maintenance_days_per_doublet, i] = False
    return avail, starts


def _geothermal_heat(q, n_on, c_sec, t_b, a: Assumptions, ua_mw_k=None):
    """Heat (MW) the HX moves from n_on doublets at flow q into the network.

    ``ua_mw_k=None``: ideal counter-flow HX with a minimum approach (used once,
    to size the HX on the peak day). Otherwise: GEMINI's counter-flow
    effectiveness-NTU equation for an HX of fixed size UA, with a brine bypass
    that throttles duty when the network would exceed 100 degC or the brine
    would be cooled by more than the 40 degC cap.
    Returns (heat, bypass_active).
    """
    rho_cp = CHALLENGE["brine_density_kg_m3"] * a.brine_specific_heat_j_kgk / 3600 / 1e6  # MW/K per m3/h
    t_sup = CHALLENGE["heating_supply_temperature_c"]
    t_ret = a.heating_return_temperature_c
    # the 40 degC cap is producer wellhead -> injector, so surface losses count against it
    max_hx_dt = CHALLENGE["max_brine_cooling_c"] - a.surface_temperature_loss_c
    c_b = n_on * q * rho_cp
    cap = np.minimum(c_sec * (t_sup - t_ret), c_b * max_hx_dt)
    if ua_mw_k is None:
        sec_limit = c_sec * np.clip(np.minimum(t_b - a.hx_min_approach_c, t_sup) - t_ret, 0, None)
        brine_dt = np.clip(np.minimum(max_hx_dt, t_b - (t_ret + a.hx_min_approach_c)), 0, None)
        return np.minimum(sec_limit, c_b * brine_dt), np.zeros_like(q, bool)
    c_min, c_max = np.minimum(c_b, c_sec), np.maximum(c_b, c_sec)
    with np.errstate(divide="ignore", invalid="ignore"):
        ntu = ua_mw_k / c_min
        cr = c_min / c_max
        e = np.exp(-ntu * (1 - cr))
        eff = np.where(np.abs(1 - cr) < 1e-9, ntu / (1 + ntu), (1 - e) / (1 - cr * e))
    q_ntu = np.clip(eff * c_min * (t_b - t_ret), 0, None)
    q_ntu = np.where(c_min > 0, q_ntu, 0.0)
    return np.minimum(q_ntu, cap), q_ntu > cap + 1e-9


def run_year(design: PlantDesign, a: Assumptions = None, demand: pd.DataFrame = None):
    """Simulate 365 days. Returns (daily DataFrame, KPI dict, curve, maintenance starts)."""
    a = a or Assumptions()
    demand = load_demand() if demand is None else demand
    n_days = len(demand)
    curve = hydraulic_curve(design.well, a, t_inj_c=a.heating_return_temperature_c + a.hx_min_approach_c)
    gas = gas_properties()
    eta = a.boiler_efficiency
    rho_cp = CHALLENGE["brine_density_kg_m3"] * a.brine_specific_heat_j_kgk / 3600 / 1e6
    t_sup = CHALLENGE["heating_supply_temperature_c"]
    t_ret = a.heating_return_temperature_c
    qmax = CHALLENGE["max_flow_m3h_per_doublet"]

    # per-flow lookups on a fine grid (GEMINI curve interpolated)
    t_wh = np.interp(Q_FINE, curve["q_m3h"], curve["wellhead_temperature_c"])
    t_b = t_wh - a.surface_temperature_loss_c
    esp = np.interp(Q_FINE, curve["q_m3h"], curve["esp_power_mw"])
    intake = np.interp(Q_FINE, curve["q_m3h"], curve["esp_intake_pressure_bar"])
    inj_whp = np.interp(Q_FINE, curve["q_m3h"], curve["injector_whp_required_bar"])

    def surface_pressure(n_on):
        # surface plant sized for all installed doublets; GEMINI units are linear (dp = R*Q)
        return a.producer_wellhead_pressure_bar - a.surface_pressure_drop_bar * (
            n_on * Q_FINE / (design.n_doublets * qmax))

    def dispatch(qh, n_av, ua):
        """Exhaustive search over (doublets on, flow) minimising the day's CO2.

        CO2 = purchased natural gas + all produced associated gas (combusted
        whether used or flared) + pump electricity; ties -> more geothermal heat.
        """
        c_sec = qh / (t_sup - t_ret)
        best = None
        for n_on in range(1, n_av + 1):
            q_geo, bypass = _geothermal_heat(Q_FINE, n_on, c_sec, t_b, a, ua)
            q_geo = np.minimum(q_geo, qh)
            topup = qh - q_geo
            gas_fuel = CHALLENGE["gas_liquid_ratio_nm3_per_m3"] * n_on * Q_FINE * gas["lhv_mj_nm3"] / 3600
            assoc_heat = np.minimum(topup, eta * gas_fuel)
            ng_fuel = (topup - assoc_heat) / eta
            p_av = surface_pressure(n_on)
            inj_pump = Q_FINE / 3600 * np.clip(inj_whp - p_av, 0, None) * 1e5 / CHALLENGE["pump_hydraulic_efficiency"] / 1e6
            pump = n_on * (esp + inj_pump)
            co2_kg_h = (ng_fuel * 3600 / a.natural_gas_lhv_mj_nm3 * a.natural_gas_co2_kg_nm3
                        + gas_fuel * 3600 / gas["lhv_mj_nm3"] * gas["co2_kg_nm3_burned"]
                        + pump * 1e3 * a.electricity_co2_kg_kwh)
            j = int(np.lexsort((-q_geo, co2_kg_h))[0])
            key = (float(co2_kg_h[j]), -float(q_geo[j]))
            if best is None or key < best["key"]:
                best = {"key": key, "n_on": n_on, "j": j, "geo": float(q_geo[j]), "bypass": bool(bypass[j]),
                        "inj_pump": float(inj_pump[j]), "p_avail": float(p_av[j]), "gas_fuel": float(gas_fuel[j])}
        return best, c_sec

    avail, starts = _availability(design, n_days, a, demand["heating_mw"].to_numpy())

    # HX size: given, or sized so the peak day reaches the minimum approach
    ua = design.hx_ua_mw_k
    if ua is None:
        peak = int(demand["heating_mw"].idxmax())
        b, c_sec = dispatch(float(demand.at[peak, "heating_mw"]), int(avail[peak].sum()), None)
        j, n_on = b["j"], b["n_on"]
        t_bo = t_b[j] - b["geo"] / (n_on * Q_FINE[j] * rho_cp)
        t_so = t_ret + b["geo"] / c_sec
        dt1, dt2 = t_b[j] - t_so, t_bo - t_ret
        lmtd = dt1 if abs(dt1 - dt2) < 1e-9 else (dt1 - dt2) / np.log(dt1 / dt2)
        ua = b["geo"] / lmtd

    rows = []
    for d in range(n_days):
        qh, qc = float(demand.at[d, "heating_mw"]), float(demand.at[d, "cooling_mw"])
        n_av = int(avail[d].sum())
        b, c_sec = dispatch(qh, n_av, ua) if n_av else (None, qh / (t_sup - t_ret))
        if b is None:
            n_on, j, geo, bypass, inj_pump_mw, p_av, gas_fuel_avail = 0, None, 0.0, False, 0.0, np.nan, 0.0
        else:
            n_on, j, geo, bypass = b["n_on"], b["j"], b["geo"], b["bypass"]
            inj_pump_mw, p_av, gas_fuel_avail = n_on * b["inj_pump"], b["p_avail"], b["gas_fuel"]
        q = float(Q_FINE[j]) if n_on else 0.0
        t_prod = float(t_wh[j]) if n_on else np.nan
        t_inj = float(t_b[j]) - geo / (n_on * q * rho_cp) if n_on else np.nan
        topup = max(0.0, qh - geo)
        assoc_heat = min(topup, eta * gas_fuel_avail)
        ng_heat = topup - assoc_heat
        rows.append({
            "date": demand.at[d, "date"],
            "heating_mw": qh,
            "cooling_mw": qc,
            "doublets_available": n_av,
            "doublets_on": n_on,
            "q_per_doublet_m3h": q,
            "q_total_m3h": q * n_on,
            "t_wellhead_c": t_prod,
            "t_injection_c": t_inj,
            "brine_cooling_c": t_prod - t_inj if n_on else np.nan,
            "t_network_after_hx_c": t_ret + (geo / c_sec if c_sec > 0 else 0.0),
            "hx_bypass_active": bypass,
            "heat_geothermal_mw": geo,
            "heat_assoc_gas_boiler_mw": assoc_heat,
            "heat_ng_boiler_mw": ng_heat,
            "heat_unmet_mw": max(0.0, qh - geo - assoc_heat - ng_heat),
            "cooling_supplied_mw": 0.0,
            "cooling_unmet_mw": qc,
            "esp_power_mw": n_on * float(esp[j]) if n_on else 0.0,
            "injection_pump_power_mw": inj_pump_mw,
            "esp_intake_bar": float(intake[j]) if n_on else np.nan,
            "injector_whp_required_bar": float(inj_whp[j]) if n_on else np.nan,
            "injection_choke_needed": bool(n_on and inj_whp[j] < p_av),
            "ng_fuel_mw": ng_heat / eta,
            "assoc_gas_fuel_mw": gas_fuel_avail,
            "assoc_gas_unused_fuel_mw": gas_fuel_avail - assoc_heat / eta,
            "production_m3h": q * n_on,
            "injection_m3h": q * n_on,  # same reservoir, equal liquid volumes (by design)
        })
    daily = pd.DataFrame(rows)
    on = np.zeros((n_days, design.n_doublets), bool)
    for d, n_on in enumerate(daily["doublets_on"]):
        on[d, np.flatnonzero(avail[d])[:n_on]] = True
    for i in range(design.n_doublets):
        daily[f"doublet_{i + 1}_on"] = on[:, i]
    kpis = compute_kpis(daily, design, a)
    kpis["hx_ua_mw_k"] = float(ua)
    kpis["maintenance_start_dates"] = [str(demand.at[s, "date"].date()) for s in starts]
    return daily, kpis, curve, starts


def compute_kpis(daily: pd.DataFrame, design: PlantDesign, a: Assumptions) -> dict:
    gas = gas_properties()
    gwh = lambda col: float(daily[col].sum() * 24 / 1e3)  # noqa: E731
    heat = gwh("heating_mw")
    elec = gwh("esp_power_mw") + gwh("injection_pump_power_mw")
    ng_nm3 = float((daily["ng_fuel_mw"] * 24 * 3600 / a.natural_gas_lhv_mj_nm3).sum())
    assoc_nm3 = float((daily["assoc_gas_fuel_mw"] * 24 * 3600 / gas["lhv_mj_nm3"]).sum())
    co2_ng = ng_nm3 * a.natural_gas_co2_kg_nm3 / 1e3
    co2_assoc = assoc_nm3 * gas["co2_kg_nm3_burned"] / 1e3  # all produced gas is combusted (used or flared)
    co2_el = elec * 1e6 * a.electricity_co2_kg_kwh / 1e3
    op_days = [int(daily[f"doublet_{i + 1}_on"].sum()) for i in range(design.n_doublets)]
    return {
        "design": design.describe(),
        "heating_demand_gwh": heat,
        "heating_geothermal_gwh": gwh("heat_geothermal_mw"),
        "heating_assoc_gas_gwh": gwh("heat_assoc_gas_boiler_mw"),
        "heating_natural_gas_gwh": gwh("heat_ng_boiler_mw"),
        "heating_unmet_gwh": gwh("heat_unmet_mw"),
        "geothermal_share_of_heating": gwh("heat_geothermal_mw") / heat,
        "cooling_demand_gwh": gwh("cooling_mw"),
        "cooling_unmet_gwh": gwh("cooling_unmet_mw"),
        "pump_electricity_gwh": elec,
        "natural_gas_mm3": ng_nm3 / 1e6,
        "assoc_gas_mm3": assoc_nm3 / 1e6,
        "assoc_gas_unused_share": float(daily["assoc_gas_unused_fuel_mw"].sum() / max(daily["assoc_gas_fuel_mw"].sum(), 1e-9)),
        "co2_t": co2_ng + co2_assoc + co2_el,
        "co2_t_breakdown": {"natural_gas": co2_ng, "associated_gas": co2_assoc, "electricity": co2_el},
        "co2_kg_per_mwh_heat": (co2_ng + co2_assoc + co2_el) * 1e3 / (heat * 1e3),
        "operating_days_per_doublet": op_days,
        "max_q_per_doublet_m3h": float(daily["q_per_doublet_m3h"].max()),
        "min_active_q_per_doublet_m3h": float(daily.loc[daily["doublets_on"] > 0, "q_per_doublet_m3h"].min()),
        "max_brine_cooling_c": float(daily["brine_cooling_c"].max()),
        "peak_heat_geothermal_mw": float(daily["heat_geothermal_mw"].max()),
        "peak_topup_mw": float((daily["heat_assoc_gas_boiler_mw"] + daily["heat_ng_boiler_mw"]).max()),
        "hx_bypass_days": int(daily["hx_bypass_active"].sum()),
    }


def compare(designs, a: Assumptions = None, demand=None) -> pd.DataFrame:
    """Run several designs and return a one-row-per-design KPI table."""
    a = a or Assumptions()
    demand = load_demand() if demand is None else demand
    out = []
    for d in designs:
        _, k, _, _ = run_year(d, a, demand)
        flat = {kk: v for kk, v in k.items() if not isinstance(v, (dict, list))}
        out.append({"name": d.name, **flat})
    return pd.DataFrame(out).set_index("name")


__all__ = ["PlantDesign", "run_year", "compare", "schedule_maintenance", "replace"]
