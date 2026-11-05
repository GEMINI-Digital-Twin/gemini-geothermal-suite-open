"""Year plan for a shallow aquifer cold store (ATES) feeding the district cooling network.

GEMINI has no ATES model; :class:`gemini_model.ates.ates.ATES` is ours. A
design with ``ates_doublets > 0`` gets its ATES plan here, before the
geothermal plant is dispatched, because the cold store only interacts with
the cooling side:

- Days with cooling demand (after any free cooling): the store pre-cools
  the chilled-water return as far as its cold water allows; the electric
  or absorption chiller does the rest.
- Days without cooling demand whose mean air is below
  ``ates_charge_air_max_c``: a dry cooler charges the cold well.

The year is run three times so it is cyclic (each pass starts from the
state the previous one ended with). Dutch permits require the aquifer's
heat balance to close over the years, so if the summer heat put into the
aquifer and the winter heat taken out differ by more than
``ates_balance_tolerance``, the side in excess is throttled (the largest
flow limit, found by bisection, at which that side is no longer in excess).

The plan needs a daily outdoor temperature (``ambient_mean_c`` or
``ambient_c`` in the demand table, see :mod:`gemini_design.climate`):
without weather there is no way to charge the store.
"""

import numpy as np

from gemini_design.challenge import ASSUMPTIONS, CHALLENGE
from gemini_model.ates.ates import ATES

CYCLE_PASSES = 3
SECONDS_PER_DAY = 86400.0


class MissingWeatherError(ValueError):
    """An ATES design was run without outdoor temperatures."""


def build_model(design, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Return an ATES model for a design's well pairs and the stated assumptions."""
    a = assumptions
    model = ATES()
    model.update_parameters(
        {
            "well_pairs": int(design.ates_doublets),
            "flow_max_m3h": a["ates_flow_max_m3h"],
            "groundwater_c": a["ates_groundwater_c"],
            "warm_well_max_c": a["ates_warm_well_max_c"],
            "cold_injection_min_c": a["ates_cold_injection_min_c"],
            "charge_approach_k": a["ates_charge_approach_k"],
            "hex_approach_k": a["ates_hex_approach_k"],
            "pressure_drop_bar": a["ates_pressure_drop_bar"],
            "pump_efficiency": challenge["pump_efficiency"],
            "loss_fraction_per_day": a["ates_loss_fraction_per_day"],
            "store_volume_m3": a["ates_store_volume_m3"],
            "fan_power_fraction": a["free_cooling_fan_power_fraction"],
            "rho": a["water_density"],
            "cp": a["water_cp"],
        }
    )
    return model


def nominal_capacity_mw(design, assumptions=ASSUMPTIONS):
    """Cooling rating (MW) of the well field at full flow from undisturbed groundwater.

    Used to size the groundwater heat exchanger and the charging dry cooler
    for costing.
    """
    a = assumptions
    q = design.ates_doublets * a["ates_flow_max_m3h"] / 3600.0
    dt = a["cooling_return_c"] - a["ates_hex_approach_k"] - a["ates_groundwater_c"]
    return q * a["water_density"] * a["water_cp"] * max(dt, 0.0) / 1e6


def _ambient_mean(demand):
    for col in ("ambient_mean_c", "ambient_c"):
        if col in demand:
            return demand[col].to_numpy(dtype=float)
    raise MissingWeatherError(
        "An ATES design needs daily outdoor temperatures to charge the cold well: add them "
        "with gemini_design.climate.with_climate (KNMI or EPW data)."
    )


def _run_year(model, plant, demand, ambient_mean, discharge_fraction, charge_fraction, state):
    """One pass over the year; returns per-day arrays and the end state."""
    c, a = plant.c, plant.a
    n = len(demand)
    cols = (
        "cooling_w",
        "charge_w",
        "power_w",
        "flow_m3h",
        "extraction_c",
        "cold_volume_m3",
        "cold_temperature_c",
        "warm_volume_m3",
        "warm_temperature_c",
        "loss_mwh",
    )
    out = {k: np.zeros(n) for k in cols}
    cooling = demand["cooling_mw"].to_numpy(dtype=float) * 1e6
    ambient = demand["ambient_c"].to_numpy(dtype=float) if "ambient_c" in demand else ambient_mean
    for i in range(n):
        u = dict(state)
        if cooling[i] > 0:
            free, t_in = plant.free_cooling(cooling[i], ambient[i])
            u.update(
                {
                    "mode": "discharge",
                    "chilled_temperature_in": t_in,
                    "chilled_flow_rate": plant._chilled_flow(cooling[i]),
                    "chilled_temperature_out_target": c["cooling_supply_c"],
                    "cooling_request": cooling[i] - free,
                    "flow_fraction": discharge_fraction,
                }
            )
        elif ambient_mean[i] <= a["ates_charge_air_max_c"]:
            u.update(
                {
                    "mode": "charge",
                    "air_temperature": ambient_mean[i],
                    "flow_fraction": charge_fraction,
                }
            )
        else:
            u["mode"] = "idle"
        model.calculate_output(u)
        y = model.get_output()
        state = model.update_state(u, state)
        out["cooling_w"][i] = y["cooling_power"]
        out["charge_w"][i] = y["charge_power"]
        out["power_w"][i] = y["power_el"]
        out["flow_m3h"][i] = y["groundwater_flow_m3h"]
        discharging = u["mode"] == "discharge" and y["extraction_temperature_c"] is not None
        out["extraction_c"][i] = y["extraction_temperature_c"] if discharging else np.nan
        out["loss_mwh"][i] = y["loss_mwh"]
        for k in ("cold_volume_m3", "cold_temperature_c", "warm_volume_m3", "warm_temperature_c"):
            out[k][i] = state[k]
    return out, state


def _cyclic(model, plant, demand, ambient_mean, discharge_fraction, charge_fraction):
    state = model.initialize_state(None)
    for _ in range(CYCLE_PASSES):
        start = dict(state)
        out, state = _run_year(
            model, plant, demand, ambient_mean, discharge_fraction, charge_fraction, start
        )
    out["start_state"] = start
    return out


def _imbalance(out):
    heat_in = out["cooling_w"].sum()  # summer: heat taken from the network into the aquifer
    heat_out = out["charge_w"].sum()  # winter: heat removed from the aquifer water
    if heat_in <= 0:
        return 0.0 if heat_out <= 0 else -1.0
    return (heat_in - heat_out) / heat_in


def plan(design, plant, demand, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Return the cyclic, heat-balanced ATES plan for the year (dict of daily arrays + KPIs)."""
    ambient_mean = _ambient_mean(demand)
    model = build_model(design, challenge, assumptions)
    tol = assumptions["ates_balance_tolerance"]
    discharge, charge = 1.0, 1.0
    out = _cyclic(model, plant, demand, ambient_mean, discharge, charge)
    imbalance = _imbalance(out)
    if abs(imbalance) > tol:
        throttle_discharge = imbalance > 0
        lo, hi = 0.0, 1.0
        for _ in range(25):
            mid = 0.5 * (lo + hi)
            d, ch = (mid, 1.0) if throttle_discharge else (1.0, mid)
            trial = _cyclic(model, plant, demand, ambient_mean, d, ch)
            # throttling the side in excess moves the imbalance monotonically towards the
            # other sign: keep the largest flow that is no longer in excess
            value = _imbalance(trial)
            ok = value <= tol if throttle_discharge else value >= -tol
            lo, hi = (mid, hi) if ok else (lo, mid)
        discharge, charge = (lo, 1.0) if throttle_discharge else (1.0, lo)
        out = _cyclic(model, plant, demand, ambient_mean, discharge, charge)
        imbalance = _imbalance(out)
    out.update(
        {
            "imbalance": imbalance,
            "discharge_flow_fraction": discharge,
            "charge_flow_fraction": charge,
            "nominal_capacity_mw": nominal_capacity_mw(design, assumptions),
        }
    )
    return out
