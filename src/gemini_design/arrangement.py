"""Series or parallel: how two doublets share the district heating load.

The year model (:mod:`gemini_design.plant`) treats all doublets as equal
and mixes their brine on one header in front of one heat exchanger. That
is right for doublets at the same depth, but it is only one of three
ways to connect them:

``parallel_header``
    Both brines mix and pass one HEX; the district water passes it once.
    With doublets at different depths the mix is cooled to one outlet
    temperature, so the 40 K cap of the *hotter* doublet decides how far
    both may be cooled.
``parallel_split``
    Each doublet has its own HEX, and the district flow is split between
    them (in proportion to the brine flow).
``series``
    Each doublet has its own HEX, and the district water passes them one
    after the other, coolest doublet first. Each HEX sees a warmer
    district inlet than the one before it, so a hot deep doublet can top
    up what a cooler shallow one starts.

Every HEX is GEMINI's ``HeatExchanger`` (counter-flow, effectiveness-NTU)
with its own bypass, so neither the 40 K brine cap nor the 100 degC
supply is ever exceeded. The boiler tops up to 100 degC.

:func:`compare_year` dispatches every day of the year for each
arrangement (both doublets' flows on a grid, cheapest day kept, each
doublet down for its 35 days in the low-demand season) and returns
annual totals. It covers heating only: cooling, CHP and associated gas do
not depend on the arrangement, so they are left out of the comparison.
"""

import itertools

import numpy as np

from gemini_design.annual import schedule_outages
from gemini_design.challenge import ASSUMPTIONS, CHALLENGE
from gemini_design.doublet import DoubletHydraulics
from gemini_design.economics import capital_recovery_factor
from gemini_design.plant import Design
from gemini_model.heat_exchanger.heat_exchanger import HeatExchanger

ARRANGEMENTS = ("parallel_header", "parallel_split", "series")
FLOW_GRID = (0.0, 50.0, 100.0, 150.0, 200.0, 250.0, 300.0)


class _Hex:
    """One GEMINI HEX with a bypass on the district side."""

    def __init__(self, ua, rho, cp):
        self.model = HeatExchanger()
        self.model.update_parameters(
            {
                "flow_resistance": 0.0,
                "flow_configuration": "counter",
                "heat_transfer_coefficient": ua,
                "fluid_density": rho,
                "specific_heat": cp,
            }
        )

    def _run(self, t_brine, q_brine, t_in, q_district, fraction):
        self.model.calculate_output(
            {
                "pressure_in": 10.0,
                "primary_temperature_in": t_brine,
                "primary_flow_rate": q_brine,
                "secondary_temperature_in": t_in,
                "secondary_flow_rate": fraction * q_district,
            }
        )
        out = self.model.output
        t_mixed = fraction * out["secondary_temperature_out"] + (1.0 - fraction) * t_in
        return out["primary_temperature_out"], t_mixed

    def heat(self, t_brine, q_brine, t_in, q_district, t_brine_min, t_supply):
        """Return (brine outlet, district outlet) with the bypass that respects both limits."""
        if q_brine <= 0 or q_district <= 0 or t_brine <= t_in:
            return t_brine, t_in

        def ok(f):
            t_b, t_s = self._run(t_brine, q_brine, t_in, q_district, f)
            return t_b >= t_brine_min - 1e-9 and t_s <= t_supply + 1e-9

        if ok(1.0):
            return self._run(t_brine, q_brine, t_in, q_district, 1.0)
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if ok(mid) else (lo, mid)
        return self._run(t_brine, q_brine, t_in, q_district, lo)


class DoubletPair:
    """Two doublets (any depths) and one way of connecting them to the district network."""

    def __init__(self, depths_m, arrangement, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
        """Set up the hydraulics of both doublets; the coolest one comes first in series."""
        if arrangement not in ARRANGEMENTS:
            raise ValueError(f"arrangement must be one of {ARRANGEMENTS}")
        self.c, self.a = challenge, assumptions
        self.arrangement = arrangement
        self.depths = sorted(float(d) for d in depths_m)
        self.hyd = [DoubletHydraulics(d, challenge, assumptions) for d in self.depths]
        self.rho, self.cp = challenge["brine_density"], assumptions["brine_cp"]
        ua = assumptions["hex_ua_per_doublet_w_per_k"]
        self.hexes = [_Hex(ua, self.rho, self.cp) for _ in self.depths]
        self.header_hex = _Hex(len(self.depths) * ua, self.rho, self.cp)

    def evaluate(self, heating_w, flows_m3h):
        """Return the day's heat split for per-doublet flows (m3/h; 0 = off)."""
        c, a = self.c, self.a
        rho_cp = self.rho * self.cp
        t_supply, t_return = c["heating_supply_c"], a["heating_return_c"]
        q_district = heating_w / (rho_cp * (t_supply - t_return))
        wells = []
        for hyd, f in zip(self.hyd, flows_m3h):
            if f > 0:
                prod = hyd.producer(f)
                wells.append(
                    {
                        "hyd": hyd,
                        "flow": f,
                        "q": f / 3600.0,
                        "t_wh": prod["wellhead_temperature_c"],
                        "esp_w": prod["esp_power_w"],
                    }
                )
        t_district = t_return
        if wells and q_district > 0:
            if self.arrangement == "parallel_header" or len(wells) == 1:
                q = sum(w["q"] for w in wells)
                t_mix = sum(w["q"] * w["t_wh"] for w in wells) / q
                t_min = max(w["t_wh"] for w in wells) - c["brine_cooling_max_k"]
                hx = self.header_hex if len(wells) > 1 else self.hexes[0]
                t_out, t_district = hx.heat(t_mix, q, t_return, q_district, t_min, t_supply)
                for w in wells:
                    w["t_inj"] = t_out
            elif self.arrangement == "series":
                for w, hx in zip(wells, self.hexes):
                    t_min = w["t_wh"] - c["brine_cooling_max_k"]
                    w["t_inj"], t_district = hx.heat(
                        w["t_wh"], w["q"], t_district, q_district, t_min, t_supply
                    )
            else:  # parallel_split
                q = sum(w["q"] for w in wells)
                mixed = 0.0
                for w, hx in zip(wells, self.hexes):
                    share = q_district * w["q"] / q
                    t_min = w["t_wh"] - c["brine_cooling_max_k"]
                    w["t_inj"], t_out = hx.heat(w["t_wh"], w["q"], t_return, share, t_min, t_supply)
                    mixed += share * t_out
                t_district = mixed / q_district
        geo = sum(rho_cp * w["q"] * (w["t_wh"] - w["t_inj"]) for w in wells)
        pumps = sum(
            w["esp_w"] + w["hyd"].injector(w["flow"], w["t_inj"])["pump_power_w"] for w in wells
        )
        boiler = rho_cp * q_district * max(0.0, t_supply - t_district)
        return {
            "geothermal_heat_w": geo,
            "boiler_heat_w": boiler,
            "pump_power_w": pumps,
            "district_after_geothermal_c": t_district,
            "brine_cooling_k": [w["t_wh"] - w["t_inj"] for w in wells],
            "flows_m3h": list(flows_m3h),
        }

    def cost_eur_per_day(self, r):
        """Energy cost of a day: boiler gas (bought) and pump electricity, CO2 included."""
        a = self.a
        gas_mwh = r["boiler_heat_w"] / a["boiler_efficiency"] / 1e6 * 24.0
        el_mwh = r["pump_power_w"] / 1e6 * 24.0
        co2_t = (
            gas_mwh * 3.6 * a["natural_gas_emission_kg_per_gj"] / 1000.0
            + el_mwh * a["electricity_emission_kg_per_kwh"]
        )
        return (
            gas_mwh * a["gas_price_eur_per_mwh"]
            + el_mwh * a["electricity_price_eur_per_mwh"]
            + co2_t * a["co2_price_eur_per_t"]
        ), co2_t

    def best_day(self, heating_w, available):
        """Cheapest flow pair (on the flow grid, 50-300 m3/h when running) for a day."""
        grid = [FLOW_GRID if ok else (0.0,) for ok in available]
        best = None
        for flows in itertools.product(*grid):
            r = self.evaluate(heating_w, flows)
            cost, co2 = self.cost_eur_per_day(r)
            if best is None or cost < best[0]:
                best = (cost, co2, r)
        return best


def well_capex_eur(depths_m, assumptions=ASSUMPTIONS):
    """Drilling cost of all wells (two per doublet)."""
    a = assumptions
    return sum(2 * (a["well_cost_fixed_eur"] + a["well_cost_per_m_eur"] * d) for d in depths_m)


def compare_year(
    depths_m, demand, arrangements=ARRANGEMENTS, challenge=CHALLENGE, assumptions=ASSUMPTIONS
):
    """Annual heating totals of two doublets for each arrangement."""
    heating = demand["heating_mw"].to_numpy(dtype=float) * 1e6
    outage_design = Design(len(depths_m), float(np.mean(depths_m)), "boiler", "electric")
    availability = schedule_outages(demand, outage_design, challenge, assumptions)
    crf = capital_recovery_factor(assumptions["discount_rate"], assumptions["lifetime_years"])
    capex = well_capex_eur(depths_m, assumptions)
    results = {}
    for arrangement in arrangements:
        pair = DoubletPair(depths_m, arrangement, challenge, assumptions)
        tot = {"geo": 0.0, "boiler": 0.0, "pumps": 0.0, "cost": 0.0, "co2": 0.0}
        peak = None
        for i, h in enumerate(heating):
            cost, co2, r = pair.best_day(h, availability[i])
            tot["geo"] += r["geothermal_heat_w"]
            tot["boiler"] += r["boiler_heat_w"]
            tot["pumps"] += r["pump_power_w"]
            tot["cost"] += cost
            tot["co2"] += co2
            if peak is None or h > peak[0]:
                peak = (h, r)
        to_mwh = 24.0 / 1e6
        annual_wells = capex * (crf + assumptions["fixed_om_fraction"])
        results[arrangement] = {
            "depths_m": pair.depths,
            "geothermal_heat_mwh": tot["geo"] * to_mwh,
            "boiler_heat_mwh": tot["boiler"] * to_mwh,
            "pump_electricity_mwh": tot["pumps"] * to_mwh,
            "energy_cost_eur": tot["cost"],
            "co2_t": tot["co2"],
            "well_capex_eur": capex,
            "wells_plus_energy_eur_per_year": annual_wells + tot["cost"],
            "peak_day": {
                "district_after_geothermal_c": peak[1]["district_after_geothermal_c"],
                "brine_cooling_k": peak[1]["brine_cooling_k"],
                "flows_m3h": peak[1]["flows_m3h"],
                "boiler_mw": peak[1]["boiler_heat_w"] / 1e6,
            },
        }
    return results
