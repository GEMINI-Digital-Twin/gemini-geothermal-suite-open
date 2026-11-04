"""Daily annual simulation of an integrated geothermal heating and cooling plant.

One evaluation = 365 daily steady states. Per day the dispatcher searches every
combination of doublets running and flow per doublet (1 m3/h steps) and picks
the one with the lowest CO2, with a heavy penalty on unmet demand.

Brine cascade (hottest use first), all within the 40 degC brine-cooling cap:

    wellhead -> surface losses -> [absorption chiller generator] -> heating HX
             -> [heat pump evaporator] -> injectors

Network side:

    heating return -> HX -> [heat pump condenser] -> boiler (associated gas, then
                     natural gas) -> 100 degC supply
    cooling return -> [absorption chiller] -> [electric chiller] -> 20 degC supply

Components in [brackets] are optional design choices (capacity 0 = absent).
Well physics: GEMINI IPR + DPDT (wells.py). HX: GEMINI effectiveness-NTU.
Heat pump: GEMINI's Lorenz equation (surface.py, cross-checked in verify.py).
Chillers: new GEMINI models in gemini_model.chiller.
"""

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from agentic_design.config import CHALLENGE, Assumptions, gas_compression_kwh_per_nm3, gas_properties, load_demand
from agentic_design.surface import absorption_operate, electric_chiller_operate, heat_pump_operate
from agentic_design.wells import WellDesign, hydraulic_curve, interp_wellhead_temperature

Q_FINE = np.arange(CHALLENGE["min_flow_m3h_per_doublet"], CHALLENGE["max_flow_m3h_per_doublet"] + 0.5, 1.0)


@dataclass(frozen=True)
class PlantDesign:
    name: str = "baseline"
    n_doublets: int = 2
    well: WellDesign = field(default_factory=WellDesign)
    heat_pump_mw: float = 0.0  # heating capacity of a heat pump on the brine after the HX
    absorption_mw: float = 0.0  # cooling capacity of brine-driven absorption chillers
    electric_chiller_mw: float = 0.0  # cooling capacity of electric chillers
    maintenance_start_doy: tuple = ()  # one 0-based start day per doublet; () = auto schedule
    hx_ua_mw_k: float = None  # heat exchanger size; None = size for min approach on the peak day
    gas_reinjection: bool = False  # True: burn associated gas only when the boilers need it, reinject the rest

    @property
    def cooling(self):
        parts = [f"absorption {self.absorption_mw:g} MW"] * (self.absorption_mw > 0) + \
                [f"electric chiller {self.electric_chiller_mw:g} MW"] * (self.electric_chiller_mw > 0)
        return " + ".join(parts) if parts else "none"

    @property
    def topup(self):
        return (f"heat pump {self.heat_pump_mw:g} MW + " if self.heat_pump_mw > 0 else "") + "gas boiler"

    def describe(self):
        return (f"{self.name}: {self.n_doublets} doublet(s), wells to {self.well.depth_m:.0f} m, "
                f"ID {self.well.inner_diameter_m:.2f} m, ESP at {self.well.esp_depth_m:.0f} m, "
                f"top-up={self.topup}, cooling={self.cooling}"
                + (f", HX UA {self.hx_ua_mw_k:.2f} MW/K" if self.hx_ua_mw_k else ""))


def gas_handling(design, a):
    return "reinject_surplus" if getattr(design, "gas_reinjection", False) else getattr(a, "assoc_gas_handling", "burn_all")


def schedule_maintenance(load_mw: np.ndarray, n_doublets: int, days: int) -> tuple:
    """Place one non-overlapping maintenance window per doublet where geothermal load is lowest."""
    n_days = len(load_mw)
    window = pd.Series(load_mw).rolling(days).sum().shift(-(days - 1)).to_numpy()
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


def _geothermal_load_profile(design, demand, a):
    """Heat the doublets must deliver per day: heating plus absorption drive heat (if any)."""
    load = demand["heating_mw"].to_numpy().copy()
    if design.absorption_mw > 0:
        load += np.minimum(demand["cooling_mw"].to_numpy(), design.absorption_mw) / a.absorption_cop_nominal
    return load


def schedule_plant_outage(design, demand: pd.DataFrame, a: Assumptions) -> int:
    """Start day of the single plant-wide geothermal outage: the window where running WITHOUT geothermal
    costs least. Per day: heating from natural gas, all cooling from the electric chiller (absorption has no
    drive heat), and a large penalty for cooling the electric chiller cannot cover (the window must be feasible)."""
    days = a.maintenance_days_per_doublet
    heat, cool = demand["heating_mw"].to_numpy(), demand["cooling_mw"].to_numpy()
    co2_ng = a.natural_gas_co2_kg_nm3 * 3600 / a.natural_gas_lhv_mj_nm3 / a.boiler_efficiency  # kg/MWh heat
    co2_el = a.electricity_co2_kg_kwh * 1e3
    ec = design.electric_chiller_mw
    served = np.minimum(cool, ec)
    day_cost = (heat * co2_ng + served / 5.0 * co2_el  # typical chiller COP ~5 for ranking windows only
                + (cool - served) * a.unmet_demand_penalty_kg_co2_per_mwh) * 24
    window = pd.Series(day_cost).rolling(days).sum().shift(-(days - 1)).to_numpy()
    return int(np.nanargmin(window))


def _availability(design: PlantDesign, n_days: int, a: Assumptions, load_mw: np.ndarray, demand=None):
    if design.maintenance_start_doy:
        starts = design.maintenance_start_doy
    elif getattr(a, "maintenance_mode", "staggered") == "simultaneous":
        # one plant-wide geothermal outage (organisers, 1 Nov), placed where it costs least
        starts = (schedule_plant_outage(design, demand, a),) * design.n_doublets
    else:
        starts = schedule_maintenance(load_mw, design.n_doublets, a.maintenance_days_per_doublet)
    avail = np.ones((n_days, design.n_doublets), bool)
    for i, s in enumerate(starts):
        avail[s:s + a.maintenance_days_per_doublet, i] = False
    return avail, starts


def _hx_heat(c_b, c_sec, t_in, budget_dt, a: Assumptions, ua_mw_k=None):
    """Heat (MW) the heating HX moves from brine (capacity c_b MW/K, inlet t_in) to the network.

    ``ua_mw_k=None``: ideal counter-flow HX with a minimum approach (used once, to size
    the HX on the peak day). Otherwise GEMINI's counter-flow effectiveness-NTU equation
    for a fixed UA, with a brine bypass that throttles duty when the network would exceed
    100 degC or the brine would exceed its remaining cooling budget ``budget_dt``.
    Returns (heat, bypass_active).
    """
    t_sup, t_ret = CHALLENGE["heating_supply_temperature_c"], a.heating_return_temperature_c
    cap = np.minimum(c_sec * (t_sup - t_ret), c_b * np.clip(budget_dt, 0, None))
    if c_sec <= 0:
        return np.zeros_like(c_b), np.zeros_like(c_b, bool)
    if ua_mw_k is None:
        sec_limit = c_sec * np.clip(np.minimum(t_in - a.hx_min_approach_c, t_sup) - t_ret, 0, None)
        brine_dt = np.clip(np.minimum(budget_dt, t_in - (t_ret + a.hx_min_approach_c)), 0, None)
        return np.minimum(sec_limit, c_b * brine_dt), np.zeros_like(c_b, bool)
    c_min, c_max = np.minimum(c_b, c_sec), np.maximum(c_b, c_sec)
    with np.errstate(divide="ignore", invalid="ignore"):
        ntu = ua_mw_k / c_min
        cr = c_min / c_max
        e = np.exp(-ntu * (1 - cr))
        eff = np.where(np.abs(1 - cr) < 1e-9, ntu / (1 + ntu), (1 - e) / (1 - cr * e))
    q_ntu = np.where(c_min > 0, np.clip(eff * c_min * (t_in - t_ret), 0, None), 0.0)
    return np.minimum(q_ntu, cap), q_ntu > cap + 1e-9


def run_year(design: PlantDesign, a: Assumptions = None, demand: pd.DataFrame = None):
    """Simulate 365 days. Returns (daily DataFrame, KPI dict, hydraulic curve, maintenance starts)."""
    a = a or Assumptions()
    demand = load_demand() if demand is None else demand
    n_days = len(demand)
    curve = hydraulic_curve(design.well, a, t_inj_c=a.heating_return_temperature_c + a.hx_min_approach_c)
    gas = gas_properties()
    eta_b = a.boiler_efficiency
    rho_cp = CHALLENGE["brine_density_kg_m3"] * a.brine_specific_heat_j_kgk / 3600 / 1e6  # MW/K per m3/h
    t_sup, t_ret = CHALLENGE["heating_supply_temperature_c"], a.heating_return_temperature_c
    t_chw_sup = CHALLENGE["cooling_supply_temperature_c"]
    t_chw_mean = 0.5 * (t_chw_sup + a.cooling_return_temperature_c)
    qmax = CHALLENGE["max_flow_m3h_per_doublet"]
    budget0 = CHALLENGE["max_brine_cooling_c"] - a.surface_temperature_loss_c  # wellhead -> injection cap
    abs_p = {"capacity_w": design.absorption_mw * 1e6, "cop_nom": a.absorption_cop_nominal, "aux_fraction": a.chiller_aux_fraction}
    ec_p = {"capacity_w": design.electric_chiller_mw * 1e6, "eta_carnot": a.electric_chiller_eta_carnot,
            "aux_fraction": a.chiller_aux_fraction}
    co2_el = a.electricity_co2_kg_kwh * 1e3  # kg per MWh
    co2_ng = a.natural_gas_co2_kg_nm3 * 3600 / a.natural_gas_lhv_mj_nm3  # kg per MWh fuel
    co2_assoc = gas["co2_kg_nm3_burned"] * 3600 / gas["lhv_mj_nm3"]
    handling = gas_handling(design, a)
    comp_mw_per_fuel_mw = gas_compression_kwh_per_nm3(a) / 1e3 * 3600 / gas["lhv_mj_nm3"]  # MW electric per MW gas fuel
    penalty = a.unmet_demand_penalty_kg_co2_per_mwh

    t_wh = interp_wellhead_temperature(curve, Q_FINE)
    t_b = t_wh - a.surface_temperature_loss_c
    esp = np.interp(Q_FINE, curve["q_m3h"], curve["esp_power_mw"])
    intake = np.interp(Q_FINE, curve["q_m3h"], curve["esp_intake_pressure_bar"])
    inj_whp = np.interp(Q_FINE, curve["q_m3h"], curve["injector_whp_required_bar"])

    def options_one(qh, qc, n_on, ua, order, share):
        """All quantities for n_on doublets at every flow on Q_FINE (arrays), for one brine order
        ('abs_first' or 'hx_first') and one absorption load share (0-1 of what it could take)."""
        c_sec = qh / (t_sup - t_ret)
        c_b = n_on * Q_FINE * rho_cp
        zeros = np.zeros_like(Q_FINE)
        use_abs = design.absorption_mw > 0 and qc > 0 and share > 0

        def absorber(t_in, budget):
            if not use_abs:
                return zeros, zeros, np.full_like(Q_FINE, np.nan), zeros
            ab = absorption_operate(np.full_like(Q_FINE, share * min(qc, design.absorption_mw * 1.2) * 1e6), t_in,
                                    c_b * 1e6, a.cooling_water_temperature_c, t_chw_mean, abs_p,
                                    max_drive_dt=np.clip(budget, 0, None))
            return ab["cooling"] / 1e6, ab["drive_heat"] / 1e6, ab["cop"], ab["power_el"] / 1e6

        if order == "abs_first":
            cool_abs, drive, abs_cop, abs_aux = absorber(t_b, np.full_like(Q_FINE, budget0))
            t1 = t_b - drive / c_b
            budget1 = budget0 - drive / c_b
            geo, bypass = _hx_heat(c_b, c_sec, t1, budget1, a, ua)
            geo = np.minimum(geo, qh)
            t2 = t1 - geo / c_b
            budget2 = budget1 - geo / c_b
            t_after = t2
        else:  # heating HX takes the hottest brine; absorber runs on what is left
            t1, budget1 = t_b, np.full_like(Q_FINE, budget0)
            geo, bypass = _hx_heat(c_b, c_sec, t1, budget1, a, ua)
            geo = np.minimum(geo, qh)
            t2 = t1 - geo / c_b
            cool_abs, drive, abs_cop, abs_aux = absorber(t2, budget1 - geo / c_b)
            t_after = t2 - drive / c_b
            budget2 = budget1 - geo / c_b - drive / c_b
        t_hx_out = t_ret + (geo / c_sec if c_sec > 0 else 0.0)
        # heat pump on the remaining brine
        if design.heat_pump_mw > 0 and qh > 0:
            hp = heat_pump_operate(design.heat_pump_mw, qh - geo, c_sec, t_hx_out, t_after, c_b, t_after - budget2,
                                   eta=a.heat_pump_eta_lorenz)
            hp_heat, hp_pw, hp_cop, t3, hp_evap = hp["heat"], hp["power"], hp["cop"], hp["source_out_c"], hp["evaporator_heat"]
        else:
            hp_heat = hp_pw = hp_evap = zeros
            hp_cop = np.full_like(Q_FINE, np.nan)
            t3 = t_after
        # top-up boilers: associated gas first, then natural gas
        topup = np.clip(qh - geo - hp_heat, 0, None)
        gas_fuel = CHALLENGE["gas_liquid_ratio_nm3_per_m3"] * n_on * Q_FINE * gas["lhv_mj_nm3"] / 3600
        assoc_heat = np.minimum(topup, eta_b * gas_fuel) if handling != "reinject_all" else zeros
        ng_fuel = (topup - assoc_heat) / eta_b
        if handling == "burn_all":  # everything produced is burned or flared
            gas_emit, gas_reinj = gas_fuel, zeros
        else:  # burn what the boilers need, compress and reinject the rest
            gas_emit = assoc_heat / eta_b
            gas_reinj = gas_fuel - gas_emit
        comp_pw = gas_reinj * comp_mw_per_fuel_mw
        # electric chiller for remaining cooling
        ec_load = np.clip(qc - cool_abs, 0, None)
        if design.electric_chiller_mw > 0 and qc > 0:
            ec = electric_chiller_operate(ec_load * 1e6, t_chw_sup, a.cooling_water_temperature_c, ec_p)
            cool_ec, ec_pw, ec_cop = ec["cooling"] / 1e6, ec["power_el"] / 1e6, ec["cop"]
        else:
            cool_ec = ec_pw = zeros
            ec_cop = np.nan
        unmet_cool = np.clip(qc - cool_abs - cool_ec, 0, None)
        # pumps (surface plant sized for all installed doublets; GEMINI units are linear dp = R*Q)
        p_av = a.producer_wellhead_pressure_bar - a.surface_pressure_drop_bar * (n_on * Q_FINE / (design.n_doublets * qmax))
        inj_pump = n_on * Q_FINE / 3600 * np.clip(inj_whp - p_av, 0, None) * 1e5 / CHALLENGE["pump_hydraulic_efficiency"] / 1e6
        elec = n_on * esp + inj_pump + hp_pw + ec_pw + abs_aux + comp_pw
        co2 = ng_fuel * co2_ng + gas_emit * co2_assoc + elec * co2_el  # kg/h
        objective = co2 + penalty * unmet_cool
        return dict(c_sec=c_sec, cool_abs=cool_abs, drive=drive, abs_cop=abs_cop, abs_aux=abs_aux,
                    t1=np.broadcast_to(t1, Q_FINE.shape), geo=geo, bypass=bypass,
                    t_hx_out=np.broadcast_to(t_hx_out, Q_FINE.shape), t2=t2, hp_heat=hp_heat, hp_pw=hp_pw,
                    hp_cop=hp_cop, hp_evap=hp_evap, t3=t3, assoc_heat=assoc_heat, ng_fuel=ng_fuel, gas_fuel=gas_fuel,
                    gas_emit=gas_emit, gas_reinj=gas_reinj, comp_pw=comp_pw,
                    cool_ec=cool_ec, ec_pw=ec_pw, ec_cop=np.broadcast_to(ec_cop, Q_FINE.shape), unmet_cool=unmet_cool,
                    inj_pump=inj_pump, p_av=p_av, elec=elec, co2=co2, objective=objective,
                    order=np.full(Q_FINE.shape, order if use_abs else "-", dtype=object),
                    abs_share=np.full(Q_FINE.shape, share if use_abs else 0.0))

    ABS_SHARES = (0.0, 0.5, 1.0)

    def options(qh, qc, n_on, ua):
        """Best brine order and absorption share for every flow (elementwise minimum objective)."""
        combos = [("hx_first", 0.0)]
        if design.absorption_mw > 0 and qc > 0:
            combos += [(o, s) for o in ("abs_first", "hx_first") for s in ABS_SHARES if s > 0]
        best = None
        for order, share in combos:
            o = options_one(qh, qc, n_on, ua, order, share)
            if best is None:
                best = {k: (np.array(v, copy=True) if np.ndim(v) else v) for k, v in o.items()}
                continue
            better = o["objective"] < best["objective"] - 1e-9
            for k, v in o.items():
                if np.ndim(v):
                    best[k] = np.where(better, v, best[k])
        return best

    def dispatch(qh, qc, n_av, ua):
        best = None
        for n_on in range(1, n_av + 1):
            o = options(qh, qc, n_on, ua)
            j = int(np.lexsort((-(o["geo"] + o["hp_evap"]), o["objective"]))[0])
            key = (float(o["objective"][j]), -float(o["geo"][j]))
            if best is None or key < best[0]:
                best = (key, n_on, j, o)
        return best

    load_profile = _geothermal_load_profile(design, demand, a)
    avail, starts = _availability(design, n_days, a, load_profile, demand)

    ua = design.hx_ua_mw_k
    if ua is None:  # size the heating HX for its minimum approach on the peak heating day
        peak = int(demand["heating_mw"].idxmax())
        _, n_on, j, o = dispatch(float(demand.at[peak, "heating_mw"]), 0.0, int(avail[peak].sum()), None)
        geo = float(o["geo"][j])
        t_bi, t_bo, t_so = float(o["t1"][j]), float(o["t2"][j]), float(np.asarray(o["t_hx_out"])[j])
        dt1, dt2 = t_bi - t_so, t_bo - t_ret
        lmtd = dt1 if abs(dt1 - dt2) < 1e-9 else (dt1 - dt2) / np.log(dt1 / dt2)
        ua = geo / lmtd

    rows = []
    for d in range(n_days):
        qh, qc = float(demand.at[d, "heating_mw"]), float(demand.at[d, "cooling_mw"])
        n_av = int(avail[d].sum())
        res = dispatch(qh, qc, n_av, ua) if n_av else None
        if res is None:  # no doublet available: boilers and electric chiller only
            ec = electric_chiller_operate(qc * 1e6, t_chw_sup, a.cooling_water_temperature_c, ec_p) \
                if design.electric_chiller_mw > 0 else {"cooling": 0.0, "power_el": 0.0, "cop": np.nan}
            row = {"doublets_on": 0, "q_per_doublet_m3h": 0.0, "t_wellhead_c": np.nan, "t_hx_brine_in_c": np.nan,
                   "t_hx_brine_out_c": np.nan, "t_injection_c": np.nan, "t_network_after_hx_c": t_ret,
                   "hx_bypass_active": False, "heat_geothermal_mw": 0.0, "heat_pump_mw": 0.0, "heat_pump_power_mw": 0.0,
                   "heat_pump_cop": np.nan, "heat_pump_evaporator_mw": 0.0, "absorption_drive_mw": 0.0,
                   "heat_assoc_gas_boiler_mw": 0.0, "heat_ng_boiler_mw": qh, "ng_fuel_mw": qh / eta_b,
                   "assoc_gas_fuel_mw": 0.0, "assoc_gas_unused_fuel_mw": 0.0, "assoc_gas_emitted_fuel_mw": 0.0,
                   "assoc_gas_reinjected_fuel_mw": 0.0, "gas_compressor_power_mw": 0.0,
                   "cooling_absorption_mw": 0.0, "absorption_cop": np.nan, "cooling_electric_mw": float(ec["cooling"]) / 1e6,
                   "electric_chiller_cop": float(ec["cop"]), "electric_chiller_power_mw": float(ec["power_el"]) / 1e6,
                   "chiller_aux_power_mw": 0.0, "esp_power_mw": 0.0, "injection_pump_power_mw": 0.0,
                   "esp_intake_bar": np.nan, "injector_whp_required_bar": np.nan, "injection_choke_needed": False,
                   "brine_order": "-", "absorption_share": 0.0}
        else:
            _, n_on, j, o = res
            q = float(Q_FINE[j])
            g = lambda k: float(np.asarray(o[k])[j]) if np.ndim(o[k]) else float(o[k])  # noqa: E731
            row = {"doublets_on": n_on, "q_per_doublet_m3h": q, "t_wellhead_c": float(t_wh[j]),
                   "t_hx_brine_in_c": g("t1"), "t_hx_brine_out_c": g("t2"), "t_injection_c": g("t3"),
                   "t_network_after_hx_c": g("t_hx_out"), "hx_bypass_active": bool(o["bypass"][j]),
                   "heat_geothermal_mw": g("geo"), "heat_pump_mw": g("hp_heat"), "heat_pump_power_mw": g("hp_pw"),
                   "heat_pump_cop": g("hp_cop"), "heat_pump_evaporator_mw": g("hp_evap"), "absorption_drive_mw": g("drive"),
                   "heat_assoc_gas_boiler_mw": g("assoc_heat"), "heat_ng_boiler_mw": g("ng_fuel") * eta_b,
                   "ng_fuel_mw": g("ng_fuel"), "assoc_gas_fuel_mw": g("gas_fuel"),
                   "assoc_gas_unused_fuel_mw": g("gas_fuel") - g("assoc_heat") / eta_b,
                   "assoc_gas_emitted_fuel_mw": g("gas_emit"), "assoc_gas_reinjected_fuel_mw": g("gas_reinj"),
                   "gas_compressor_power_mw": g("comp_pw"),
                   "cooling_absorption_mw": g("cool_abs"), "absorption_cop": g("abs_cop"),
                   "cooling_electric_mw": g("cool_ec"), "electric_chiller_cop": g("ec_cop"),
                   "electric_chiller_power_mw": g("ec_pw"), "chiller_aux_power_mw": g("abs_aux"),
                   "esp_power_mw": n_on * float(esp[j]), "injection_pump_power_mw": g("inj_pump"),
                   "esp_intake_bar": float(intake[j]), "injector_whp_required_bar": float(inj_whp[j]),
                   "injection_choke_needed": bool(inj_whp[j] < o["p_av"][j]),
                   "brine_order": str(o["order"][j]), "absorption_share": float(o["abs_share"][j])}
        n_on, q = row["doublets_on"], row["q_per_doublet_m3h"]
        heat_supplied = row["heat_geothermal_mw"] + row["heat_pump_mw"] + row["heat_assoc_gas_boiler_mw"] + row["heat_ng_boiler_mw"]
        cool_supplied = row["cooling_absorption_mw"] + row["cooling_electric_mw"]
        rows.append({"date": demand.at[d, "date"], "heating_mw": qh, "cooling_mw": qc, "doublets_available": n_av, **row,
                     "q_total_m3h": q * n_on,
                     "brine_cooling_c": row["t_wellhead_c"] - row["t_injection_c"] if n_on else np.nan,
                     "heat_unmet_mw": max(0.0, qh - heat_supplied), "cooling_supplied_mw": cool_supplied,
                     "cooling_unmet_mw": max(0.0, qc - cool_supplied),
                     "production_m3h": q * n_on, "injection_m3h": q * n_on})
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
    heat, cool = gwh("heating_mw"), gwh("cooling_mw")
    elec_parts = {k: gwh(c) for k, c in [("esp", "esp_power_mw"), ("injection_pump", "injection_pump_power_mw"),
                                          ("heat_pump", "heat_pump_power_mw"), ("electric_chiller", "electric_chiller_power_mw"),
                                          ("chiller_aux", "chiller_aux_power_mw"),
                                          ("gas_compressor", "gas_compressor_power_mw")]}
    elec = sum(elec_parts.values())
    ng_nm3 = float((daily["ng_fuel_mw"] * 24 * 3600 / a.natural_gas_lhv_mj_nm3).sum())
    assoc_nm3 = float((daily["assoc_gas_fuel_mw"] * 24 * 3600 / gas["lhv_mj_nm3"]).sum())
    emitted_nm3 = float((daily["assoc_gas_emitted_fuel_mw"] * 24 * 3600 / gas["lhv_mj_nm3"]).sum())
    reinj_nm3 = float((daily["assoc_gas_reinjected_fuel_mw"] * 24 * 3600 / gas["lhv_mj_nm3"]).sum())
    co2_ng = ng_nm3 * a.natural_gas_co2_kg_nm3 / 1e3
    co2_assoc = emitted_nm3 * gas["co2_kg_nm3_burned"] / 1e3
    co2_el = elec * 1e6 * a.electricity_co2_kg_kwh / 1e3
    op_days = [int(daily[f"doublet_{i + 1}_on"].sum()) for i in range(design.n_doublets)]
    active = daily["doublets_on"] > 0
    hp_heat = gwh("heat_pump_mw")
    geo_heat_hx = gwh("heat_geothermal_mw")
    geo_into_heating = geo_heat_hx + gwh("heat_pump_evaporator_mw")  # brine heat ending up in the heating network
    return {
        "design": design.describe(),
        "heating_demand_gwh": heat,
        "heating_geothermal_gwh": geo_heat_hx,
        "heating_heat_pump_gwh": hp_heat,
        "heating_assoc_gas_gwh": gwh("heat_assoc_gas_boiler_mw"),
        "heating_natural_gas_gwh": gwh("heat_ng_boiler_mw"),
        "heating_unmet_gwh": gwh("heat_unmet_mw"),
        "geothermal_share_of_heating": geo_into_heating / heat,
        "heat_pump_mean_cop": float(hp_heat / max(elec_parts["heat_pump"], 1e-9)) if hp_heat > 0 else None,
        "cooling_demand_gwh": cool,
        "cooling_absorption_gwh": gwh("cooling_absorption_mw"),
        "cooling_electric_gwh": gwh("cooling_electric_mw"),
        "cooling_unmet_gwh": gwh("cooling_unmet_mw"),
        "absorption_drive_heat_gwh": gwh("absorption_drive_mw"),
        "electricity_gwh": elec,
        "electricity_breakdown_gwh": elec_parts,
        "pump_electricity_gwh": elec_parts["esp"] + elec_parts["injection_pump"],
        "natural_gas_mm3": ng_nm3 / 1e6,
        "assoc_gas_mm3": assoc_nm3 / 1e6,
        "assoc_gas_reinjected_mm3": reinj_nm3 / 1e6,
        "assoc_gas_handling": gas_handling(design, a),
        # flared share: only when surplus gas is not reinjected
        "assoc_gas_unused_share": (float(daily["assoc_gas_unused_fuel_mw"].sum() / max(daily["assoc_gas_fuel_mw"].sum(), 1e-9))
                                   if gas_handling(design, a) == "burn_all" else 0.0),
        "co2_t": co2_ng + co2_assoc + co2_el,
        "co2_t_breakdown": {"natural_gas": co2_ng, "associated_gas": co2_assoc, "electricity": co2_el},
        "co2_kg_per_mwh_heat": (co2_ng + co2_assoc + co2_el) * 1e3 / (heat * 1e3),
        "co2_kg_per_mwh_delivered": (co2_ng + co2_assoc + co2_el) * 1e3 / ((heat + cool) * 1e3),
        "operating_days_per_doublet": op_days,
        "max_q_per_doublet_m3h": float(daily["q_per_doublet_m3h"].max()),
        "min_active_q_per_doublet_m3h": float(daily.loc[active, "q_per_doublet_m3h"].min()) if active.any() else 0.0,
        "max_brine_cooling_c": float(daily["brine_cooling_c"].max()),
        "peak_heat_geothermal_mw": float(daily["heat_geothermal_mw"].max()),
        "peak_topup_mw": float((daily["heat_assoc_gas_boiler_mw"] + daily["heat_ng_boiler_mw"]).max()),
        "peak_boiler_ng_mw": float(daily["heat_ng_boiler_mw"].max()),
        "peak_electric_chiller_mw": float(daily["cooling_electric_mw"].max()),
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
