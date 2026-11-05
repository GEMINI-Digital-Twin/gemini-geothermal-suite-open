"""What a finished run gave: the totals of its flows and the capacities of the plant."""

from dataclasses import dataclass
from functools import partial
from typing import Any

import numpy as np

from gemini.engine.apply import apply_case
from gemini.evaluate._utils.cost import equipment
from gemini.evaluate._utils.ratings import rating_of
from gemini.evaluate._utils.series import (
    COLD_DELIVERED,
    EDGE_POWERS,
    HEAT_DELIVERED,
    edge_power,
    energy,
    leaf_total,
    port_difference,
    useful_cold,
    useful_heat,
)
from gemini.modules.environment import Atmosphere, Formation
from gemini.modules.grids import ChemicalGrid, CoolingGrid, ElectricityGrid, HeatingGrid, WasteGrid
from gemini.plants.roles import delivery_ports, units_of
from gemini.units.shapes import measure

__all__ = ["KPI_NAMES", "totals"]


@dataclass(frozen=True)
class _Series:
    """The plant-level power series [W] the KPIs share, each ``None`` when the plant lacks it."""

    seconds: np.ndarray
    heat: Any
    heat_unmet: Any
    cold: Any
    cold_unmet: Any
    electricity: Any
    pump_heat: Any = None
    pump_work: Any = None


def _read(plant, results):
    """Return the shared series of a run."""
    frame = results.to_frame()
    sensible = leaf_total(plant, frame, "unmet_sensible", CoolingGrid)
    latent = leaf_total(plant, frame, "unmet_latent", CoolingGrid)
    return _Series(
        seconds=results.durations,
        heat=useful_heat(plant, frame),
        heat_unmet=leaf_total(plant, frame, "unmet_demand", HeatingGrid),
        cold=useful_cold(plant, frame),
        cold_unmet=None if sensible is None or latent is None else sensible + latent,
        electricity=leaf_total(plant, frame, "power_out", ElectricityGrid),
        **_heat_pumps(plant, frame),
    )


def _heat_pumps(plant, frame):
    """Return ``{pump_heat, pump_work}``: the heat [W] the heating heat pumps give and their work.

    Each is the sum over the units of the role ``heat_pump`` whose run holds the columns, or
    ``None`` when there is none.
    """
    heat, work = [], []
    for path in units_of(plant, "heat_pump"):
        ports = delivery_ports(plant.get_submodule(path), "heat_pump") or ()
        names = [f"{path}.{port}.enthalpy_flow" for port in ports] + [f"{path}.power_in"]
        if len(names) == 3 and all(name in frame for name in names):
            heat.append(frame[names[0]] - frame[names[1]])
            work.append(frame[names[2]])
    if not heat:
        return {"pump_heat": None, "pump_work": None}
    return {"pump_heat": sum(heat), "pump_work": sum(work)}


def _coverage(series, delivered, unmet, consumer):
    """Return delivered energy over demanded energy, or a reason when it is undefined."""
    delivered, unmet = getattr(series, delivered), getattr(series, unmet)
    if delivered is None or unmet is None:
        return None, f"the plant has no {consumer}"
    demand = delivered + unmet
    demanded = energy(demand, series.seconds)
    if demanded <= 0:
        return None, "the demand is zero over the window"
    return energy(delivered.where(demand.notna()), series.seconds) / demanded, None


def _peak(series, delivered, consumer):
    """Return the largest delivered power, or a reason when there is none."""
    delivered = getattr(series, delivered)
    if delivered is None:
        return None, f"the plant has no {consumer}"
    if delivered.notna().sum() == 0:
        return None, "no tick has a delivered power"
    return float(delivered.max()), None


def _heat_pump_cop(series):
    """Return the heat the heating heat pumps gave over the electricity they took (QA-322).

    ``cop`` is the plant's heat over all the electricity it bought, which reads as no machine's
    COP (18.9 for a plant whose heat is mostly geothermal); this is the heat pumps' own.
    """
    if series.pump_heat is None:
        return None, "the plant has no heat pump that heats"
    known = series.pump_heat.notna() & series.pump_work.notna()
    work = energy(series.pump_work.where(known), series.seconds)
    if work <= 0:
        return None, "the heat pumps took no electricity over the window"
    return energy(series.pump_heat.where(known), series.seconds) / work, None


def _cop(series):
    if series.heat is None:
        return None, "the plant has no HeatingGrid"
    if series.electricity is None:
        return None, "the plant has no ElectricityGrid"
    consumed = energy(series.electricity.where(series.heat.notna()), series.seconds)
    if consumed <= 0:
        return None, "no electricity is consumed over the window"
    return energy(series.heat.where(series.electricity.notna()), series.seconds) / consumed, None


_KPIS = {
    "heating_coverage": (
        "-",
        partial(_coverage, delivered="heat", unmet="heat_unmet", consumer="HeatingGrid"),
    ),
    "cooling_coverage": (
        "-",
        partial(_coverage, delivered="cold", unmet="cold_unmet", consumer="CoolingGrid"),
    ),
    "cop": ("-", _cop),
    "heat_pump_cop": ("-", _heat_pump_cop),
    "peak_heat": ("W", partial(_peak, delivered="heat", consumer="HeatingGrid")),
    "peak_cold": ("W", partial(_peak, delivered="cold", consumer="CoolingGrid")),
}
"""Each KPI name with its unit and the function that computes ``(value, reason)``."""


KPI_NAMES = tuple(_KPIS)
"""The names of the KPIs among the totals."""


def _kpis(plant, results):
    """Return the KPIs of a finished run as ``{name: {value, unit}}``; see ``totals``."""
    series = _read(plant, results)
    values = {}
    for name, (unit, compute) in _KPIS.items():
        number, reason = compute(series)
        values[name] = measure(number, unit, reason)
    return values


_EDGE_TOTALS = {
    "electricity_bought": ("J", *EDGE_POWERS["electricity_bought"]),
    "electricity_sold": ("J", ElectricityGrid, "net_export"),
    "gas_bought": ("J", *EDGE_POWERS["gas_bought"]),
    "co2_emitted": ("kg", Atmosphere, "co2_emission"),
    "methane_emitted": ("kg", Atmosphere, "methane_emission"),
    "waste": ("kg", WasteGrid, "waste_in.mass_flow"),
    "chemicals": ("kg", ChemicalGrid, "chemical_out.mass_flow"),
}
"""Each total read from one column of the edge modules: unit, module class and column."""


def _integral(series, seconds, unit):
    """Return the integral of ``series`` over a run, or ``None`` with what it needs."""
    if series is None:
        return measure(None, unit, "the plant has no module at its edge that shows it")
    return measure(energy(series, seconds), unit)


def totals(plant, case, results):
    """Return what crossed the plant's edge over a run, read from the edge modules' ports.

    Parameters
    ----------
    plant : Module
        The plant that produced ``results``.
    case : Case
        The case of the run; the totals do not read it.
    results : Results
        A finished ``simulate`` or ``replay``.

    Returns
    -------
    dict
        ``{name: Value}``, each a ``gm.units.Quantity`` in SI (``to_plain`` gives the JSON):
        ``heat_delivered``, ``cold_delivered``, what the water
        gave the users; ``heat_useful``, ``cold_useful``, the part of it up to their demand;
        ``heat_surplus``, ``cold_surplus``, the rest; ``electricity_bought``,
        ``electricity_sold``, ``gas_bought`` (lower heating value) and ``losses`` in J,
        ``co2_emitted``, ``methane_emitted``, ``waste`` and ``chemicals`` in kg.
        ``losses`` is the net heat into the ``Atmosphere`` and the ``Formation``. A value is
        ``None``, with a ``reason``, when no module at the edge shows it.

        The KPIs follow, with E(x) = sum over ticks of x * tick duration [J]:

        - ``heating_coverage`` [-] = E(heat delivered) / E(heat delivered + unmet_demand) summed
          over the plant's ``HeatingGrid`` leaves: the share of the demanded heat delivered.
        - ``cooling_coverage`` [-] = E(cold delivered) / E(cold delivered + unmet_sensible +
          unmet_latent) over the ``CoolingGrid`` leaves.
        - ``cop`` [-] = E(heat delivered) / E(``ElectricityGrid.power_out``): heat delivered per
          unit of electricity consumed. Cooling is not counted.
        - ``peak_heat``, ``peak_cold`` [W] = the largest tick sum of heat or cold delivered over
          the grid leaves (delivered power, not the demand peak).

        A plant without a consumer leaf, for example the doublet heat plant, gives ``None`` for
        the KPIs that need one.
    """
    frame = results.to_frame()
    seconds = results.durations
    report = {
        "heat_delivered": _integral(port_difference(plant, frame, *HEAT_DELIVERED), seconds, "J"),
        "heat_useful": _integral(useful_heat(plant, frame), seconds, "J"),
        "heat_surplus": _integral(edge_power(plant, frame, "heat_surplus"), seconds, "J"),
        "cold_delivered": _integral(port_difference(plant, frame, *COLD_DELIVERED), seconds, "J"),
        "cold_useful": _integral(useful_cold(plant, frame), seconds, "J"),
        "cold_surplus": _integral(leaf_total(plant, frame, "surplus", CoolingGrid), seconds, "J"),
    }
    for name, (unit, module_class, field) in _EDGE_TOTALS.items():
        report[name] = _integral(leaf_total(plant, frame, field, module_class), seconds, unit)
    air = leaf_total(plant, frame, "heat_in", Atmosphere)
    ground = leaf_total(plant, frame, "heat_in", Formation)
    known = [series for series in (air, ground) if series is not None]
    report["losses"] = _integral(sum(known) if known else None, seconds, "J")
    return report | _kpis(plant, results)


def capacities(plant, case, results):
    """Return the design capacity of each equipment module of a plant and its peak use in a run.

    A module that is equipment and has a rating is listed: boilers, the CHP, heat pumps and chillers
    by their capacity [W], the doublets by their nominal flow [m3/s], the circulation pumps by
    their flow, and the exchangers, tanks and pipes by their conductance [W/K], volume [m3] and
    length [m]. A fixed item, a well and a module without a rating have no capacity and are not
    listed.

    Parameters
    ----------
    plant : Module
        The plant of the run.
    case : Case
        The case of the run; it gives the design values of the plant.
    results : Results
        A finished run.

    Returns
    -------
    dict
        ``{path: {kind, capacity, peak, share}}`` for each module: ``capacity`` and ``peak`` are
        ``gm.units.Quantity`` values in SI, the design capacity and the largest use of any step,
        and ``share`` is ``peak / capacity`` [-]. ``peak`` and ``share`` are ``None``, with a
        ``reason``, for a module whose use the run does not show.
    """
    frame = results.to_frame()
    found = {}
    for path, module in equipment(apply_case(plant, case)).items():
        rating = rating_of(module)
        if rating is not None:
            found[path] = _entry(module, rating, frame, path)
    return found


def _entry(module, rating, frame, path):
    """Return the capacity, the peak use and the share of one module."""
    capacity = getattr(module, rating.parameter)
    used = rating.use(frame, path)
    entry = {"kind": module.equipment_kind, "capacity": measure(capacity, rating.unit)}
    if used is None or not used.notna().any():
        reason = _no_use_reason(rating, frame, path, used)
        return entry | {
            "peak": measure(None, rating.unit, reason),
            "share": measure(None, "-", reason),
        }
    peak = float(np.nanmax(used.to_numpy(dtype=float)))
    return entry | {
        "peak": measure(peak, rating.unit),
        "share": measure(peak / capacity, "-"),
    }


def _no_use_reason(rating, frame, path, used):
    """Return why a module has no peak use: its rating is not measured, or it did not run.

    A conductance, a volume or a length is no use a step measures, so a module rated by one (an
    exchanger, a tank, a pipe) has no peak even when it worked; the reason then says how many
    steps it ran, from its ``operating`` column, so that no reader takes it as idle (geomind
    QA-123: an exchanger that ran all year was reported as unused).
    """
    column = f"{path}.operating"
    ran = int(frame[column].fillna(False).astype(bool).sum()) if column in frame else None
    if used is None:
        steps = "" if ran is None else f"; the module ran {ran} of {len(frame)} steps"
        return f"a rating in {rating.unit} is not a use the run measures{steps}"
    if ran:
        return f"the run measures no use of this rating; the module ran {ran} of {len(frame)} steps"
    return "the run shows no use of this module"
