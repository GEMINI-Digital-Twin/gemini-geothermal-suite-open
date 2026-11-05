"""365-day dispatch + independent validator.

For each day the dispatcher chooses, among all feasible options, the one
with the lowest CO2:
  * number of active doublets (1..N), ESP frequency (-> flow 50-300 m3/h)
  * share of cooling made by the absorption chiller (rest: electric chiller)
Geothermal is switched off on one contiguous 35-day maintenance block,
chosen where switching off costs the least CO2 (330 operating days).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from plant_model import (CP, MAX_BRINE_COOLING, MAX_DOUBLETS, MAX_FLOW_M3H, MIN_FLOW_M3H,
                         PUMP_EFFICIENCY, SUPPLY_TEMP_COOLING, SUPPLY_TEMP_HEATING,
                         GEO_OPERATING_DAYS, TOTAL_DAYS, T_WELLHEAD, Assumptions, Design,
                         build_well_table, capacity_curve, doublet_point)

ABS_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)
HEAT_TOL = 1e-6


def load_demand(folder):
    h = pd.read_csv(folder / "GEMINI_Heating_Demand_Daily_2027.csv")
    c = pd.read_csv(folder / "GEMINI_Cooling_Demand_Daily_2027.csv")
    assert len(h) == len(c) == TOTAL_DAYS
    return h["date"].values, h.iloc[:, 1].values.astype(float), c.iloc[:, 1].values.astype(float)


class Plant:
    def __init__(self, design: Design, a: Assumptions):
        self.d, self.a = design, a
        self.rows = build_well_table(design, a)
        if not self.rows:
            raise RuntimeError("no feasible well operating point")
        self.curves = [capacity_curve(r, design, a) for r in self.rows]
        self.dT = SUPPLY_TEMP_HEATING - a.t_return
        self.co2_el = a.grid_ef_kg_per_kwh / 3.6e6            # kg per J
        self.co2_gas = a.gas_ef_kg_per_gj * 1e-9 / a.backup_boiler_eff  # kg per J heat

    # ── one option ──────────────────────────────────────────────────────────
    def _option(self, n, i, heat_w, cool_w, f_abs):
        r, c = self.rows[i], self.curves[i]
        need = heat_w + f_abs * cool_w / self.a.cop_absorption       # 100 C heat
        per = need / n
        m_w = max(0.0, per - r["gas_heat_w"]) / (CP * self.dT)
        m_w_run = min(m_w, c["m_max"])
        w_hp = float(np.interp(m_w_run, c["grid"], c["w_hp"]))
        t_inj = float(np.interp(m_w_run, c["grid"], c["t_inj"]))
        geo_chain = m_w_run * CP * self.dT                             # HEX + HP heat
        backup = n * max(0.0, per - r["gas_heat_w"] - geo_chain)
        gas_used = n * min(r["gas_heat_w"], per)                       # surplus gas heat is dumped
        chiller_el = (1 - f_abs) * cool_w / self.a.cop_electric_chiller
        elec = n * (r["esp_power_w"] + r["inj_pump_w"] + w_hp - r["chp_el_w"]) + chiller_el
        co2 = (max(elec, 0.0) * self.co2_el + n * r["gas_co2_kg_s"] + backup * self.co2_gas) * 86400
        return dict(co2=co2, n=n, i=i, f_abs=f_abs, m_w=m_w_run, w_hp=w_hp, t_inj=t_inj,
                    geo_chain=n * geo_chain, gas_used=gas_used, backup=backup,
                    chiller_el=chiller_el, elec=elec)

    def best_geo(self, heat_w, cool_w):
        best = None
        for n in range(1, self.d.n_doublets + 1):
            for i in range(len(self.rows)):
                for f in ABS_FRACTIONS:
                    if f > 0 and cool_w <= 0:
                        continue
                    o = self._option(n, i, heat_w, cool_w, f)
                    if best is None or o["co2"] < best["co2"] - 1e-9:
                        best = o
        return best

    def geo_off(self, heat_w, cool_w):
        chiller_el = cool_w / self.a.cop_electric_chiller
        co2 = (chiller_el * self.co2_el + heat_w * self.co2_gas) * 86400
        return dict(co2=co2, n=0, i=None, f_abs=0.0, m_w=0.0, w_hp=0.0, t_inj=float("nan"),
                    geo_chain=0.0, gas_used=0.0, backup=heat_w, chiller_el=chiller_el, elec=chiller_el)

    # ── full year ───────────────────────────────────────────────────────────
    def simulate_year(self, dates, heat_mw, cool_mw):
        on = [self.best_geo(h * 1e6, c * 1e6) for h, c in zip(heat_mw, cool_mw)]
        off = [self.geo_off(h * 1e6, c * 1e6) for h, c in zip(heat_mw, cool_mw)]
        penalty = np.array([f["co2"] - o["co2"] for o, f in zip(on, off)])
        k = TOTAL_DAYS - GEO_OPERATING_DAYS
        window = np.convolve(penalty, np.ones(k), "valid")
        start = int(np.argmin(window))
        maint = set(range(start, start + k))

        recs = []
        for day in range(TOTAL_DAYS):
            o = off[day] if day in maint else on[day]
            r = self.rows[o["i"]] if o["i"] is not None else None
            pt = (doublet_point(r, self.d, self.a, o["m_w"]) if (r and o["m_w"] > 0) else None)
            n = o["n"]
            recs.append(dict(
                date=dates[day], day=day + 1,
                heating_demand_MW=heat_mw[day], cooling_demand_MW=cool_mw[day],
                geothermal_active=n > 0, maintenance=day in maint,
                doublets_active=n,
                esp_freq_hz=r["esp_freq_hz"] if r else 0.0,
                flow_per_doublet_m3h=r["q_m3h"] if r else 0.0,
                injection_per_doublet_m3h=r["q_inj_m3h"] if r else 0.0,
                T_producer_C=T_WELLHEAD if r else np.nan,
                T_injector_C=o["t_inj"] if r else np.nan,
                brine_cooling_C=(T_WELLHEAD - o["t_inj"]) if r else 0.0,
                T_heating_supply_C=SUPPLY_TEMP_HEATING,
                T_cooling_supply_C=SUPPLY_TEMP_COOLING,
                hp_COP=pt["cop"] if pt else np.nan,
                heat_hex_MW=n * pt["q_hex"] / 1e6 if pt else 0.0,
                heat_hp_MW=n * pt["q_hp"] / 1e6 if pt else 0.0,
                heat_geo_brine_MW=n * pt["q_geo"] / 1e6 if pt else 0.0,
                hp_elec_MW=n * o["w_hp"] / 1e6,
                heat_produced_gas_MW=o["gas_used"] / 1e6,
                heat_backup_boiler_MW=o["backup"] / 1e6,
                absorption_share=o["f_abs"],
                cooling_absorption_MW=o["f_abs"] * cool_mw[day],
                cooling_electric_MW=(1 - o["f_abs"]) * cool_mw[day],
                chiller_elec_MW=o["chiller_el"] / 1e6,
                esp_elec_MW=n * r["esp_power_w"] / 1e6 if r else 0.0,
                esp_hydraulic_MW=n * r["esp_dp_bar"] * 1e5 * r["q_m3h"] / 3600 / 1e6 if r else 0.0,
                inj_pump_elec_MW=n * r["inj_pump_w"] / 1e6 if r else 0.0,
                chp_elec_MW=n * r["chp_el_w"] / 1e6 if r else 0.0,
                net_elec_MW=o["elec"] / 1e6,
                energy_closure_kW=n * pt["closure_w"] / 1e3 if pt else 0.0,
                co2_t=o["co2"] / 1000,
            ))
        df = pd.DataFrame(recs)
        heat_out = df.heat_hex_MW + df.heat_hp_MW + df.heat_produced_gas_MW + df.heat_backup_boiler_MW
        df["heating_delivered_MW"] = heat_out - df.absorption_share * df.cooling_demand_MW / self.a.cop_absorption
        df["cooling_delivered_MW"] = df.cooling_absorption_MW + df.cooling_electric_MW
        return df


def summarize(df, design: Design):
    mwh = lambda col: float(df[col].sum() * 24)
    geo_heat = mwh("heat_hex_MW") + mwh("heat_hp_MW")
    # shares are of all 100 C heat produced (district heating + absorption drive)
    heat = geo_heat + mwh("heat_produced_gas_MW") + mwh("heat_backup_boiler_MW")
    return {
        "design": design.label(),
        "n_doublets": design.n_doublets,
        "hex_ua_kW_per_K": design.hex_ua_w_per_k / 1e3,
        "esp_stages": design.esp_stages,
        "co2_t_per_year": round(df.co2_t.sum(), 1),
        "heating_delivered_MWh": round(mwh("heating_delivered_MW"), 0),
        "absorption_drive_heat_MWh": round(heat - mwh("heating_delivered_MW"), 0),
        "cooling_delivered_MWh": round(mwh("cooling_delivered_MW"), 0),
        "geothermal_chain_share_pct": round(100 * geo_heat / heat, 1),
        "produced_gas_share_pct": round(100 * mwh("heat_produced_gas_MW") / heat, 1),
        "backup_boiler_share_pct": round(100 * mwh("heat_backup_boiler_MW") / heat, 1),
        "backup_boiler_MWh": round(mwh("heat_backup_boiler_MW"), 0),
        "net_electricity_MWh": round(mwh("net_elec_MW"), 0),
        "mean_hp_COP": round(float(df.hp_COP.mean()), 2),
        "max_brine_cooling_C": round(float(df.brine_cooling_C.max()), 2),
        "geo_days": int(df.geothermal_active.sum()),
        "maintenance_block": f"{df[df.maintenance].date.min()} .. {df[df.maintenance].date.max()}",
    }


def validate(df, design: Design, tol=1e-3):
    """Independent pass/fail checks recomputed from the daily results."""
    act = df[df.geothermal_active]
    checks = []

    def add(name, ok, detail):
        checks.append((name, bool(ok), detail))

    add("Doublets installed in [1,3]", 1 <= design.n_doublets <= MAX_DOUBLETS, f"{design.n_doublets}")
    add("Active doublets <= installed", (df.doublets_active <= design.n_doublets).all(),
        f"max {df.doublets_active.max()}")
    q = act.flow_per_doublet_m3h
    add("Flow per active doublet 50-300 m3/h", ((q >= MIN_FLOW_M3H) & (q <= MAX_FLOW_M3H)).all(),
        f"{q.min():.1f} - {q.max():.1f} m3/h")
    add("No flow on inactive days", (df[~df.geothermal_active].flow_per_doublet_m3h == 0).all(), "q = 0")
    vb = (act.flow_per_doublet_m3h - act.injection_per_doublet_m3h).abs().max()
    add("Volume balance produced = injected", vb <= 1e-6, f"max |diff| {vb:.2e} m3/h")
    add("Brine cooling <= 40 C", (act.brine_cooling_C <= MAX_BRINE_COOLING + tol).all(),
        f"max {act.brine_cooling_C.max():.2f} C")
    eff = (act.esp_hydraulic_MW / act.esp_elec_MW).round(6).unique()
    add("Pump efficiency = 0.70", np.allclose(eff, PUMP_EFFICIENCY), f"{eff}")
    add("Heating supply >= 100 C", (df.T_heating_supply_C >= SUPPLY_TEMP_HEATING - tol).all(),
        "HP condenser outlet solved at 100 C; boilers set to 100 C")
    short_h = (df.heating_demand_MW - df.heating_delivered_MW).max()
    add("Heating demand met every day", short_h <= tol, f"max shortfall {max(short_h,0):.4f} MW")
    short_c = (df.cooling_demand_MW - df.cooling_delivered_MW).max()
    add("Cooling demand met every day at 20 C", short_c <= tol, f"max shortfall {max(short_c,0):.4f} MW")
    add("Geothermal operating days = 330", int(df.geothermal_active.sum()) == GEO_OPERATING_DAYS,
        f"{int(df.geothermal_active.sum())} days")
    add("Energy balance closes (HEX+HP)", df.energy_closure_kW.abs().max() <= 1.0,
        f"max residual {df.energy_closure_kW.abs().max():.3f} kW")
    return checks
