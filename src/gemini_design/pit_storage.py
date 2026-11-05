"""Seasonal pit thermal energy storage (PTES): a built-in, temperature-resolved reference model.

A design with ``pit_store_m3 > 0`` gets one or more lined water pits on the
district heating side, like the Danish solar district heating stores
(Marstal 75,000 m3, Dronninglund 60,000 m3, Gram 122,000 m3, Vojens about
200,000 m3, Hoje Taastrup 70,000 m3). This is separate from the energy-only
``thermal_storage`` slot in :mod:`gemini_design.storage`, which an agent can
fill with its own model.

What the model resolves, at daily resolution with sub-steps:

* **Geometry.** Each pit is an inverted, square, truncated pyramid
  (``pit_store_depth_m`` deep, side slope ``pit_store_side_slope``
  horizontal per vertical). Pits are limited to
  ``pit_store_volume_min_m3``-``pit_store_volume_max_m3``; a larger store is
  split into equal pits, with no economy of scale between them.
* **Stratification.** Each pit is split into ``LAYERS`` horizontal layers
  of equal height. Charging takes water from the bottom and returns it at
  the top; discharging takes it from the top and returns it at the
  district return temperature to the bottom (upwind advection, so some
  numerical mixing stays in, which is on the pessimistic side). Layers
  exchange heat by conduction (water plus inflow mixing,
  ``pit_store_conductivity_w_per_m_k``), and a colder layer above a warmer
  one mixes at once (buoyancy).
* **Temperature limits.** Water enters the top at most at
  ``pit_store_top_max_c`` (polymer liner limit, about 90 degC) and at most
  at the brine wellhead temperature less ``pit_store_charge_approach_k``.
  Charging stops when the bottom is that warm. Discharge stops when the top
  falls below ``pit_store_discharge_min_c``.
* **Top-up to the 100 degC supply.** Discharged water is below the supply
  temperature, so the boiler lifts it from the top temperature to 100 degC.
  That top-up heat is booked on the boiler (associated gas first, then
  purchased gas) by :func:`gemini_design.annual.run_year`, with its gas,
  CO2 and cost.
* **Charge and discharge rate.** ``pit_store_mw`` is the rating at the full
  design temperature difference (top limit minus return); it fixes the
  diffuser flow, so at a lower top temperature the discharge power drops.
* **Heat losses** depend on the surfaces: the lid to the outdoor air
  (``pit_store_lid_u_w_per_m2_k``) and the sides and bottom to the ground
  (``pit_store_ground_u_w_per_m2_k`` to ``pit_store_ground_c``), per
  layer, at that layer's temperature. A bigger pit has less surface per m3
  and loses a smaller share of its heat.
* **Costs** follow a size curve fitted to the built Danish pits (about
  40 EUR/m3 at 60,000 m3, falling with size to the power
  ``pit_store_cost_exponent``), raised by ``pit_store_price_index`` to
  2027 prices, plus land (``pit_store_land_factor`` x top area) and the
  charge/discharge heat exchangers and pumps (per MW).

The state of charge is reported as the heat held above the district return
temperature (MWh), so the daily balance ``start + 24 h x (charge -
discharge) - loss = end`` closes exactly (checked by the physics gate).
"""

import math

import numpy as np

from gemini_design.challenge import ASSUMPTIONS, CHALLENGE
from gemini_design.doublet import flow_limits_m3h

LAYERS = 12
HOURS_PER_DAY = 24.0
SECONDS_PER_DAY = 86400.0
MIN_SUBSTEPS = 24
CYCLE_PASSES = 2  # the second pass starts from the first pass's end state (cyclic year)
FULL_MARGIN_K = 2.0  # stop charging when the bottom is within this of the inlet temperature


class PitStoreError(ValueError):
    """A pit store request outside the modelled range."""


def pit_layout(volume_m3, assumptions=ASSUMPTIONS):
    """Return (number of pits, volume per pit) for a total store volume."""
    a = assumptions
    v_max, v_min = a["pit_store_volume_max_m3"], a["pit_store_volume_min_m3"]
    if volume_m3 < v_min - 1e-6:
        raise PitStoreError(
            f"pit_store_m3 must be at least {v_min:,.0f} m3 (smallest pit modelled); "
            f"got {volume_m3:,.0f}"
        )
    n = max(1, math.ceil(volume_m3 / v_max - 1e-9))
    return n, volume_m3 / n


def pit_geometry(volume_m3, assumptions=ASSUMPTIONS):
    """Return the geometry of one pit: top and bottom side (m), areas (m2) and layers.

    The pit is an inverted square frustum: ``V = H/3 (a^2 + b^2 + a b)`` with
    ``b = a - 2 s H``.
    """
    h = assumptions["pit_store_depth_m"]
    s = assumptions["pit_store_side_slope"]
    k = 2.0 * s * h
    # 3 a^2 - 3 k a + k^2 - 3 V / H = 0
    disc = 9.0 * k * k - 12.0 * (k * k - 3.0 * volume_m3 / h)
    a = (3.0 * k + math.sqrt(disc)) / 6.0
    b = a - k
    if b <= 0.0:
        raise PitStoreError(
            f"a {volume_m3:,.0f} m3 pit is too small for {h:g} m depth at slope 1:{s:g}"
        )
    dz = h / LAYERS
    slant = math.sqrt(1.0 + s * s)
    z = np.linspace(0.0, h, LAYERS + 1)  # from the top down
    width = a - 2.0 * s * z
    w0, w1 = width[:-1], width[1:]
    layer_volume = dz / 3.0 * (w0**2 + w1**2 + w0 * w1)
    side_area = 4.0 * 0.5 * (w0 + w1) * dz * slant
    interface_area = width[1:-1] ** 2
    return {
        "top_side_m": a,
        "bottom_side_m": b,
        "depth_m": h,
        "top_area_m2": a * a,
        "bottom_area_m2": b * b,
        "side_area_m2": float(side_area.sum()),
        "layer_height_m": dz,
        "layer_volume_m3": layer_volume,
        "layer_side_area_m2": side_area,
        "interface_area_m2": interface_area,
    }


def capital_cost_eur(design, assumptions=ASSUMPTIONS):
    """Return the store CAPEX breakdown (EUR): pits, land and charge/discharge equipment."""
    a = assumptions
    volume = getattr(design, "pit_store_m3", 0.0)
    if volume <= 0:
        return {"pits": 0.0, "land": 0.0, "equipment": 0.0, "total": 0.0}
    n, v = pit_layout(volume, a)
    geo = pit_geometry(v, a)
    unit = (
        a["pit_store_cost_ref_eur_per_m3"]
        * (v / a["pit_store_cost_ref_volume_m3"]) ** (-a["pit_store_cost_exponent"])
        * a["pit_store_price_index"]
    )
    pits = n * v * unit
    land = n * geo["top_area_m2"] * a["pit_store_land_factor"] * a["pit_store_land_cost_eur_per_m2"]
    equipment = design.pit_store_mw * a["storage_power_cost_eur_per_mw"]
    return {
        "pits": pits,
        "land": land,
        "equipment": equipment,
        "total": pits + land + equipment,
        "eur_per_m3": unit,
    }


class PitStore:
    """One or more identical stratified pits, stepped one day at a time."""

    def __init__(self, volume_m3, power_mw, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
        """Lay out the pits and start them cold (all water at the return temperature)."""
        a, c = assumptions, challenge
        self.a, self.c = a, c
        self.n_pits, self.pit_volume = pit_layout(volume_m3, a)
        self.geo = pit_geometry(self.pit_volume, a)
        self.rho_cp = a["water_density"] * a["water_cp"]
        self.t_return = a["heating_return_c"]
        self.t_supply = c["heating_supply_c"]
        self.t_top_max = a["pit_store_top_max_c"]
        self.t_discharge_min = max(a["pit_store_discharge_min_c"], self.t_return + 1.0)
        if self.t_top_max <= self.t_return + FULL_MARGIN_K:
            raise PitStoreError("pit_store_top_max_c must be above the heating return temperature")
        self.power_mw = power_mw
        # diffuser flow per pit (m3/s), fixed by the rating at the full temperature difference
        self.flow_max = power_mw * 1e6 / (self.rho_cp * (self.t_top_max - self.t_return))
        self.flow_max /= self.n_pits
        self.vol = self.geo["layer_volume_m3"]
        self.ua_ground = a["pit_store_ground_u_w_per_m2_k"] * self.geo["layer_side_area_m2"].copy()
        self.ua_ground[-1] += a["pit_store_ground_u_w_per_m2_k"] * self.geo["bottom_area_m2"]
        self.ua_lid = a["pit_store_lid_u_w_per_m2_k"] * self.geo["top_area_m2"]
        self.cond = (
            a["pit_store_conductivity_w_per_m_k"]
            * self.geo["interface_area_m2"]
            / self.geo["layer_height_m"]
        )
        self.temperature = np.full(LAYERS, self.t_return)
        self.n_sub = max(
            MIN_SUBSTEPS, math.ceil(self.flow_max * SECONDS_PER_DAY / float(self.vol.min()))
        )

    # ------------------------------------------------------------- state
    @property
    def total_volume_m3(self):
        """Water volume of all pits (m3)."""
        return self.n_pits * self.pit_volume

    @property
    def capacity_mwh(self):
        """Heat held when all water is at the top limit, above the return temperature (MWh)."""
        return self.total_volume_m3 * self.rho_cp * (self.t_top_max - self.t_return) / 3.6e9

    def heat_above_return_mwh(self, temperature=None):
        """State of charge: heat in all pits above the district return temperature (MWh)."""
        t = self.temperature if temperature is None else temperature
        return self.n_pits * float(np.sum(self.vol * (t - self.t_return))) * self.rho_cp / 3.6e9

    def estimated_loss_fraction_per_day(self, ambient_c=None):
        """Share of the full-store heat lost per day with a half-hot store (for planning)."""
        t_mid = 0.5 * (self.t_top_max + self.t_return)
        amb = self.a["pit_store_ground_c"] if ambient_c is None else ambient_c
        loss_w = self.ua_lid * (self.t_top_max - amb) + float(self.ua_ground.sum()) * (
            t_mid - self.a["pit_store_ground_c"]
        )
        full_j = self.pit_volume * self.rho_cp * (self.t_top_max - self.t_return)
        return loss_w * SECONDS_PER_DAY / full_j

    # ------------------------------------------------------------- physics
    def _mix_inversions(self, t):
        """Buoyancy: merge any colder-above-warmer layers into their volume-weighted mean."""
        blocks = []  # [sum(v*T), sum(v), count]
        for vi, ti in zip(self.vol, t):
            blocks.append([vi * ti, vi, 1])
            while len(blocks) > 1 and (
                blocks[-2][0] / blocks[-2][1] < blocks[-1][0] / blocks[-1][1] - 1e-12
            ):
                e, v, n = blocks.pop()
                blocks[-1][0] += e
                blocks[-1][1] += v
                blocks[-1][2] += n
        out = []
        for e, v, n in blocks:
            out.extend([e / v] * n)
        return np.array(out)

    def step_day(self, charge_w=0.0, stream_w=0.0, t_charge_c=None, ambient_c=None):
        """Advance one day; return the day's flows (W, per day mean) and losses (MWh).

        ``charge_w`` is the heat on offer for charging (all pits together).
        ``stream_w`` is the district heat the store is asked to cover on a
        deficit day, measured from the return to the 100 degC supply: the
        store gives the part up to its top temperature (``discharge_w``) and
        the boiler the rest (``topup_w``). Only one of the two is used.
        ``t_charge_c`` is the hottest water the plant can send to the store.
        """
        rc, dt = self.rho_cp, SECONDS_PER_DAY / self.n_sub
        t = self.temperature.copy()
        e0 = float(np.sum(self.vol * t))
        amb = self.a["pit_store_ground_c"] if ambient_c is None else float(ambient_c)
        t_ground = self.a["pit_store_ground_c"]
        per_pit_charge = max(0.0, charge_w) / self.n_pits
        per_pit_stream = max(0.0, stream_w) / self.n_pits if charge_w <= 0 else 0.0
        t_in = self.t_top_max if t_charge_c is None else min(self.t_top_max, float(t_charge_c))
        charge_j = discharge_j = topup_j = loss_j = 0.0
        for _ in range(self.n_sub):
            if per_pit_charge > 0 and t_in - t[-1] > FULL_MARGIN_K:
                q = min(self.flow_max, per_pit_charge / (rc * (t_in - t[-1])))
                dv = q * dt
                charge_j += dv * rc * (t_in - t[-1])
                upstream = np.concatenate(([t_in], t[:-1]))
                t = t + dv / self.vol * (upstream - t)
            elif per_pit_stream > 0 and t[0] >= self.t_discharge_min:
                q = min(self.flow_max, per_pit_stream / (rc * (self.t_supply - self.t_return)))
                dv = q * dt
                discharge_j += dv * rc * (t[0] - self.t_return)
                topup_j += dv * rc * (self.t_supply - t[0])
                upstream = np.concatenate((t[1:], [self.t_return]))
                t = t + dv / self.vol * (upstream - t)
            # surface losses and conduction between layers (explicit, energy-conserving)
            flux = np.zeros(LAYERS)
            lid = self.ua_lid * (t[0] - amb)
            ground = self.ua_ground * (t - t_ground)
            flux[0] -= lid
            flux -= ground
            loss_j += (lid + float(ground.sum())) * dt
            between = self.cond * (t[:-1] - t[1:])  # W from layer i to i+1
            flux[:-1] -= between
            flux[1:] += between
            t = t + flux * dt / (rc * self.vol)
            t = self._mix_inversions(t)
        # close the balance exactly on the rounding left by the explicit updates
        e1 = float(np.sum(self.vol * t))
        residual = (e0 - e1) * rc - (discharge_j - charge_j + loss_j)
        loss_j += residual
        self.temperature = t
        n = self.n_pits
        return {
            "charge_w": n * charge_j / SECONDS_PER_DAY,
            "discharge_w": n * discharge_j / SECONDS_PER_DAY,
            "topup_w": n * topup_j / SECONDS_PER_DAY,
            "loss_mwh": n * loss_j / 3.6e9,
            "top_c": float(t[0]),
            "bottom_c": float(t[-1]),
            "inlet_c": t_in if charge_j > 0 else None,
        }


def plan(design, plant, demand, availability, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Plan the store over the year; return daily arrays.

    1. Each day the plant is evaluated at full flow on every available
       doublet with the day's demand plus the store rating. The heat it can
       give without buying gas (HEX + CHP + associated-gas boiler) less the
       demand is the day's surplus (offered for charging) or deficit (asked
       of the store). The charge temperature is the wellhead temperature
       less ``pit_store_charge_approach_k``.
    2. A cyclic backward pass sets how much heat the store should hold at
       the end of each day for the deficits ahead, so it is not charged
       with heat it would only lose.
    3. The stratified pits are stepped through the year twice (cyclic).
    """
    store = PitStore(design.pit_store_m3, design.pit_store_mw, challenge, assumptions)
    n_days = len(demand)
    heat = demand["heating_mw"].to_numpy(dtype=float)
    cool = demand["cooling_mw"].to_numpy(dtype=float)
    ambient = demand["ambient_c"].to_numpy(dtype=float) if "ambient_c" in demand else None
    surplus = np.zeros(n_days)
    t_charge = np.full(n_days, np.nan)
    approach = assumptions["pit_store_charge_approach_k"]
    for i in range(n_days):
        n = int(availability[i].sum())
        if n == 0:
            surplus[i] = -heat[i]
            continue
        kw = {"ambient_c": float(ambient[i])} if ambient is not None else {}
        kw["day"] = i
        r = plant.evaluate(
            (heat[i] + design.pit_store_mw) * 1e6,
            cool[i] * 1e6,
            n,
            flow_limits_m3h(plant.hyd, challenge)[1],
            **kw,
        )
        free = r["hex_heat_w"] + r["chp_heat_w"] + r["associated_gas_heat_w"]
        surplus[i] = free / 1e6 - heat[i]
        t_charge[i] = r["wellhead_temperature_c"] - approach

    # heat (MWh above return) to hold at the end of each day for the deficits ahead
    useful_share = (store.t_top_max - store.t_return) / (store.t_supply - store.t_return)
    power, cap = design.pit_store_mw, store.capacity_mwh
    keep = max(0.5, 1.0 - store.estimated_loss_fraction_per_day())
    give = np.minimum(np.maximum(-surplus, 0.0), power) * useful_share * HOURS_PER_DAY
    take = np.minimum(np.maximum(surplus, 0.0), power) * HOURS_PER_DAY
    need = np.zeros(n_days)
    for _ in range(CYCLE_PASSES):
        for i in range(n_days - 1, -1, -1):
            nxt = (i + 1) % n_days
            need[i] = min(cap, max(0.0, need[nxt] + give[nxt] - take[nxt]) / keep)

    for _ in range(CYCLE_PASSES):
        rows = []
        for i in range(n_days):
            soc = store.heat_above_return_mwh()
            room_mw = max(0.0, need[i] - soc * keep) / HOURS_PER_DAY
            charge = min(max(0.0, surplus[i]), power, room_mw)
            stream = min(max(0.0, -surplus[i]), power) if charge <= 0 else 0.0
            tc = None if np.isnan(t_charge[i]) else float(t_charge[i])
            if tc is None:
                charge = 0.0
            out = store.step_day(
                charge * 1e6,
                stream * 1e6,
                t_charge_c=tc,
                ambient_c=None if ambient is None else float(ambient[i]),
            )
            out["soc_start_mwh"] = soc
            out["soc_end_mwh"] = store.heat_above_return_mwh()
            rows.append(out)
    col = {k: np.array([r[k] for r in rows], dtype=float) for k in rows[0] if k != "inlet_c"}
    return {
        "store": store,
        "charge_mw": col["charge_w"] / 1e6,
        "discharge_mw": col["discharge_w"] / 1e6,
        "topup_mw": col["topup_w"] / 1e6,
        "loss_mwh": col["loss_mwh"],
        "soc_start_mwh": col["soc_start_mwh"],
        "soc_end_mwh": col["soc_end_mwh"],
        "top_c": col["top_c"],
        "bottom_c": col["bottom_c"],
        "surplus_mw": surplus,
    }


def summary(design, store_plan, assumptions=ASSUMPTIONS):
    """Return the store's yearly figures for the run summary."""
    store = store_plan["store"]
    charge = float(store_plan["charge_mw"].sum()) * HOURS_PER_DAY
    discharge = float(store_plan["discharge_mw"].sum()) * HOURS_PER_DAY
    cost = capital_cost_eur(design, assumptions)
    land_m2 = store.n_pits * store.geo["top_area_m2"] * assumptions["pit_store_land_factor"]
    return {
        "volume_m3": store.total_volume_m3,
        "pits": store.n_pits,
        "volume_per_pit_m3": store.pit_volume,
        "top_side_m": store.geo["top_side_m"],
        "depth_m": store.geo["depth_m"],
        "land_ha": land_m2 / 1e4,
        "capacity_mwh": store.capacity_mwh,
        "rating_mw": design.pit_store_mw,
        "charge_mwh": charge,
        "discharge_mwh": discharge,
        "boiler_topup_mwh": float(store_plan["topup_mw"].sum()) * HOURS_PER_DAY,
        "loss_mwh": float(store_plan["loss_mwh"].sum()),
        "storage_efficiency": discharge / charge if charge > 0 else 0.0,
        "full_cycles": discharge / store.capacity_mwh if store.capacity_mwh > 0 else 0.0,
        "max_top_c": float(store_plan["top_c"].max()),
        "min_top_c": float(store_plan["top_c"].min()),
        "max_soc_mwh": float(store_plan["soc_end_mwh"].max()),
        "capex_eur": cost["total"],
        "cost_eur_per_m3": cost.get("eur_per_m3", 0.0),
    }
