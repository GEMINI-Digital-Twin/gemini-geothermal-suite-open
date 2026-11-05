"""Seasonal heat storage in the year run, through a model slot GEMINI does not fill.

GEMINI has no thermal storage model. A design with ``storage_mwh > 0`` looks
up the component type ``thermal_storage`` in
``gemini_simulator.registry.COMPONENT_REGISTRY``; the design agent fills that
slot with ``write_model`` (sandboxed, tested). Without a registered model
the run stops with :class:`MissingModelError`, so a storage design can only
be simulated with a model that passed its own tests.

The storage sits on the district heating side (a pit or tank of hot water)
and works at daily resolution in two passes:

1. On each day, the plant is evaluated at full flow on every available
   doublet with the day's demand plus the storage power. The heat it can
   give without buying gas (HEX + CHP + associated-gas boiler) less the
   demand is the day's surplus (charge) or deficit (discharge).
2. The model steps the state of charge day by day (twice, so the year is
   cyclic: the year starts with what is left at its end). The plant is
   then dispatched as usual on ``demand + charge - discharge``.

The model's interface (checked by :func:`check_model`)::

    parameters: capacity_mwh, power_mw, loss_fraction_per_day
    inputs:     soc_mwh, charge_request_mw, discharge_request_mw   (one 24 h day)
    outputs:    soc_mwh, charge_mw, discharge_mw, loss_mwh

Charged heat is booked at the 100 degC supply, which is conservative: a
pit store holds 80-95 degC water, which the HEX reaches more easily.
"""

import numpy as np

from gemini_design.challenge import ASSUMPTIONS, CHALLENGE
from gemini_design.doublet import flow_limits_m3h
from gemini_simulator.registry import COMPONENT_REGISTRY

STORAGE_TYPE = "thermal_storage"
HOURS_PER_DAY = 24.0
CYCLE_PASSES = 2  # second pass starts from the first pass's end state


class MissingModelError(RuntimeError):
    """The design needs a component model that is not registered."""


def storage_model_class(registry=None):
    """Return the registered thermal storage model class, or raise MissingModelError."""
    registry = COMPONENT_REGISTRY if registry is None else registry
    cls = registry.get(STORAGE_TYPE)
    if cls is None:
        raise MissingModelError(
            f"This design has heat storage, but GEMINI has no '{STORAGE_TYPE}' model. "
            "Write one with write_model (register_as='thermal_storage', parameters "
            "capacity_mwh, power_mw, loss_fraction_per_day; inputs soc_mwh, "
            "charge_request_mw, discharge_request_mw; outputs soc_mwh, charge_mw, "
            "discharge_mw, loss_mwh)."
        )
    return cls


def build_model(design, assumptions=ASSUMPTIONS, registry=None):
    """Instantiate and parameterise the storage model for a design."""
    model = storage_model_class(registry)()
    model.update_parameters(
        {
            "capacity_mwh": design.storage_mwh,
            "power_mw": design.storage_mw,
            "loss_fraction_per_day": assumptions["storage_loss_fraction_per_day"],
        }
    )
    return model


def check_model(model):
    """Return a list of interface or physics problems of a storage model (empty = ok).

    Run on every storage design before its year run, so a model that passed
    its own tests but breaks the energy balance or its limits never runs.
    """
    p = model.parameters
    cap, power = p["capacity_mwh"], p["power_mw"]
    problems = []
    cases = [
        (0.0, power, 0.0),
        (0.5 * cap, 0.0, power),
        (0.9 * cap, power, 0.0),
        (0.1 * cap, 0.0, 2.0 * power),
        (0.5 * cap, 0.0, 0.0),
    ]
    for soc, charge, discharge in cases:
        try:
            model.calculate_output(
                {"soc_mwh": soc, "charge_request_mw": charge, "discharge_request_mw": discharge}
            )
            out = model.get_output()
            new_soc = float(out["soc_mwh"])
            c, d, loss = float(out["charge_mw"]), float(out["discharge_mw"]), float(out["loss_mwh"])
        except Exception as exc:  # wrong keys, crash
            return [f"{type(exc).__name__}: {exc}"]
        balance = soc + HOURS_PER_DAY * (c - d) - loss - new_soc
        if abs(balance) > 1e-6 * max(cap, 1.0):
            problems.append(f"state of charge does not balance (off by {balance:.3g} MWh)")
        if not -1e-9 <= new_soc <= cap * (1 + 1e-9):
            problems.append(f"state of charge {new_soc:.3g} MWh outside 0-{cap:.3g}")
        if c < -1e-9 or d < -1e-9 or loss < -1e-9:
            problems.append("negative charge, discharge or loss")
        if c > charge + 1e-9 or d > discharge + 1e-9 or max(c, d) > power + 1e-9:
            problems.append("charge or discharge above the request or the power rating")
    return sorted(set(problems))


def plan(design, plant, demand, availability, model, challenge=CHALLENGE):
    """Return daily charge, discharge, loss (MW / MWh) and state of charge (MWh)."""
    n_days = len(demand)
    heat = demand["heating_mw"].to_numpy(dtype=float)
    cool = demand["cooling_mw"].to_numpy(dtype=float)
    ambient = demand["ambient_c"].to_numpy(dtype=float) if "ambient_c" in demand else None
    surplus = np.zeros(n_days)
    for i in range(n_days):
        n = int(availability[i].sum())
        if n == 0:
            surplus[i] = -heat[i]
            continue
        kw = {"ambient_c": float(ambient[i])} if ambient is not None else {}
        kw["day"] = i
        r = plant.evaluate(
            (heat[i] + design.storage_mw) * 1e6,
            cool[i] * 1e6,
            n,
            flow_limits_m3h(plant.hyd, challenge)[1],
            **kw,
        )
        free = r["hex_heat_w"] + r["chp_heat_w"] + r["associated_gas_heat_w"]
        surplus[i] = free / 1e6 - heat[i]

    # energy the store must hold at the end of each day to cover the deficits ahead
    # (cyclic backward pass), so it is never charged with heat it would only lose
    power, cap = design.storage_mw, design.storage_mwh
    keep = 1.0 - model.parameters["loss_fraction_per_day"]
    give = np.minimum(np.maximum(-surplus, 0.0), power) * HOURS_PER_DAY
    take = np.minimum(np.maximum(surplus, 0.0), power) * HOURS_PER_DAY
    need = np.zeros(n_days)
    for _ in range(CYCLE_PASSES):  # the last day looks ahead to day 1 of the previous pass
        for i in range(n_days - 1, -1, -1):
            nxt = (i + 1) % n_days
            need[i] = min(cap, max(0.0, need[nxt] + give[nxt] - take[nxt]) / keep)

    soc = 0.0
    for _ in range(CYCLE_PASSES):
        rows = []
        for i in range(n_days):
            room = max(0.0, need[i] - soc * keep) / HOURS_PER_DAY
            model.calculate_output(
                {
                    "soc_mwh": soc,
                    "charge_request_mw": min(max(0.0, surplus[i]), room),
                    "discharge_request_mw": max(0.0, -surplus[i]),
                }
            )
            out = model.get_output()
            rows.append((out["charge_mw"], out["discharge_mw"], out["loss_mwh"], soc))
            soc = float(out["soc_mwh"])
    charge, discharge, loss, soc_start = (np.array(c, dtype=float) for c in zip(*rows))
    soc_end = soc_start + HOURS_PER_DAY * (charge - discharge) - loss
    return {
        "charge_mw": charge,
        "discharge_mw": discharge,
        "loss_mwh": loss,
        "soc_start_mwh": soc_start,
        "soc_end_mwh": soc_end,
        "surplus_mw": surplus,
    }
