"""What covered the demand of each day: the geothermal plant, the backup, or nothing."""

import numpy as np
import pandas as pd

from gemini.evaluate._utils.columns import series
from gemini.evaluate._utils.series import leaf_total, useful_cold, useful_heat
from gemini.modules.cooling import AbsorptionUnit, AdsorptionChiller
from gemini.modules.grids import CoolingGrid, HeatingGrid
from gemini.modules.heating import ElectricBoiler, HeatPump
from gemini.plants.roles import delivery_ports, units_of
from gemini.units.display import by_si_unit, shown
from gemini.units.shapes import measure

__all__ = ["daily_coverage"]

TOLERANCE = 1e-6
"""The share of a day's demand below which a backup or a shortfall does not colour the day."""

BACKUP_ROLES = {"heating": ("boiler", "chp"), "cooling": ()}
"""The roles of ``gm.plants.roles()`` whose units are the backup of a service; the rest of what
the service received is the geothermal plant's. No role is a backup of cooling as a whole. An
``ElectricBoiler`` (no role: it burns no fuel) is a backup of heating too, found by its class,
and a compression chiller (a ``HeatPump`` of the role ``chiller``, driven by electricity) is a
backup of cooling (geomind QA-238); an absorption or adsorption chiller stays geothermal."""

KEYS = ("demand", "geothermal", "electricity", "backup", "short")
"""The energies of a day, in the display unit of energy."""


def _heating(plant, frame):
    """Return ``(useful, unmet)`` power series [W] of the heating service, or ``None`` for both."""
    return useful_heat(plant, frame), leaf_total(plant, frame, "unmet_demand", HeatingGrid)


def _cooling(plant, frame):
    """Return ``(useful, unmet)`` power series [W] of the cooling service, or ``None`` for both."""
    sensible = leaf_total(plant, frame, "unmet_sensible", CoolingGrid)
    latent = leaf_total(plant, frame, "unmet_latent", CoolingGrid)
    both = None if sensible is None or latent is None else sensible + latent
    return useful_cold(plant, frame), both


SERVICES = {"heating": _heating, "cooling": _cooling}
"""For each service the function that reads its useful power and its unmet power."""


def _backup_power(plant, frame, service):
    """Return the power [W] the backup units of ``service`` give their water, tick by tick."""
    total = np.zeros(len(frame))
    for role in BACKUP_ROLES[service]:
        for path in units_of(plant, role):
            first, second = (
                f"{port}.enthalpy_flow" for port in delivery_ports(plant.get_submodule(path), role)
            )
            total += _delivered(plant, frame, path, first, second)
    if service == "heating":
        for path, module in plant.named_modules():
            if isinstance(module, ElectricBoiler):
                total += _delivered(plant, frame, path, *ELECTRIC_PORTS)
    if service == "cooling":
        for path in units_of(plant, "chiller"):
            module = plant.get_submodule(path)
            if isinstance(module, HeatPump):
                first, second = (
                    f"{port}.enthalpy_flow" for port in delivery_ports(module, "chiller")
                )
                total += _delivered(plant, frame, path, first, second)
    return total


HEAT_DRIVEN = (AbsorptionUnit, AdsorptionChiller)
"""The chillers driven by hot water: their cold is made from the heat of the plant's water."""
DRIVE_PORTS = ("generator_in.enthalpy_flow", "generator_out.enthalpy_flow")
"""The ports whose enthalpy flows, first less second, give a heat-driven chiller's drive heat."""


def _heat_driven(plant):
    """Return the paths of the heat-driven chillers of the plant that chill the cooling grid."""
    return [
        path
        for path in units_of(plant, "chiller")
        if isinstance(plant.get_submodule(path), HEAT_DRIVEN)
    ]


def _backup_share(plant, frame, heat):
    """Return the share [-] of the heating water's heat that its backup gave, tick by tick.

    The water the heat exchanger and the backup heat goes to the heating users and to the
    generators of the heat-driven chillers (``HeatingAbsorptionCoolingPlant``): the backup's heat
    is shared over both by what each took, so neither is all backup nor all geothermal (geomind
    QA-214: heating showed no geothermal heat on 125 summer days while both doublets ran, the
    boiler topping up the chiller drive).
    """
    drive = np.zeros(len(frame))
    for path in _heat_driven(plant):
        drive += np.maximum(_delivered(plant, frame, path, *DRIVE_PORTS), 0.0)
    water = heat + drive
    backup = _backup_power(plant, frame, "heating")
    with np.errstate(divide="ignore", invalid="ignore"):
        share = np.where(water > 0, backup / water, 0.0)
    return np.clip(np.nan_to_num(share), 0.0, 1.0)


def _shared_backup(plant, frame, service, given):
    """Return the backup power [W] of ``service``, tick by tick.

    Heating takes its part of the backup's heat; cooling the cold of the compression chillers plus
    the backup's share of the heat-driven chillers' cold.
    """
    if service == "heating":
        return _backup_share(plant, frame, given) * given
    heat = useful_heat(plant, frame)
    heat = np.zeros(len(frame)) if heat is None else np.nan_to_num(heat.to_numpy(dtype=float))
    share = _backup_share(plant, frame, np.maximum(heat, 0.0))
    driven = np.zeros(len(frame))
    for path in _heat_driven(plant):
        first, second = (
            f"{port}.enthalpy_flow" for port in delivery_ports(plant.get_submodule(path), "chiller")
        )
        driven += np.maximum(_delivered(plant, frame, path, first, second), 0.0)
    return _backup_power(plant, frame, "cooling") + share * driven


def _pump_work(plant, frame, service):
    """Return the electricity [W] the heating heat pumps take, tick by tick; cooling has none.

    A heat pump's heat is its brine heat plus its compressor work: the work is no geothermal heat
    (geomind QA-228, QA-270), so a day shows it apart.
    """
    total = np.zeros(len(frame))
    if service != "heating":
        return total
    for path in units_of(plant, "heat_pump"):
        work, _ = series(plant, frame, path, "power_in")
        if work.size:
            total += np.nan_to_num(work)
    return total


ELECTRIC_PORTS = ("fluid_out.enthalpy_flow", "fluid_in.enthalpy_flow")
"""The ports whose enthalpy flows, first less second, give an electric boiler's heat."""


def _delivered(plant, frame, path, first, second):
    """Return the power [W] a unit gives its water: the enthalpy flow of ``first`` less ``second``.

    A unit whose run holds neither flow gives zeros.
    """
    one, _ = series(plant, frame, path, first)
    other, _ = series(plant, frame, path, second)
    if one.size and other.size:
        return np.nan_to_num(one - other)
    return np.zeros(len(frame))


def _energies(plant, frame, seconds, service, useful, unmet):
    """Return the energies [J] of each tick of a service as a table, and the ticks with no demand.

    A tick where the demand is unknown (a failed step) counts nothing, the same as in
    ``gm.evaluate.totals``.
    """
    delivered, short = useful.to_numpy(dtype=float), unmet.to_numpy(dtype=float)
    known = np.isfinite(delivered + short)
    given = np.where(known, np.maximum(delivered, 0.0), 0.0)
    backup = np.minimum(_shared_backup(plant, frame, service, given), given)
    work = np.minimum(_pump_work(plant, frame, service), given - backup)
    table = pd.DataFrame(
        {
            "demand": np.where(known, delivered + short, 0.0) * seconds,
            "geothermal": (given - backup - work) * seconds,
            "electricity": work * seconds,
            "backup": backup * seconds,
            "short": np.where(known, short, 0.0) * seconds,
        },
        index=frame.index,
    )
    return table, frame.index[~known]


def _days(index):
    """Return the date of each instant of a UTC ``index`` as text."""
    return index.strftime("%Y-%m-%d")


def _source(day):
    """Return the colour of a day: ``short`` before ``backup`` before ``geothermal``."""
    margin = TOLERANCE * day["demand"]
    if day["failed_steps"] or day["short"] > margin:
        return "short"
    return "backup" if day["backup"] > margin else "geothermal"


BACKUP_NAMES = {"boiler": "Peak boiler", "chp": "CHP"}
"""The name a day's ``labels`` give the units of each backup role of heating."""


def _labels(plant, service):
    """Return ``{main, other}``: what the ``geothermal`` and the ``backup`` of a day are (QA-322).

    Named from the plant's units: heating ``Geothermal`` and its peak units; cooling the
    heat-driven chillers (``Absorption chiller (geothermal)``), and in ``other`` the compression
    chillers (``Electric chiller``) and the peak units' share of the chillers' drive heat, which
    the ``backup`` of cooling counts. ``other`` is ``None`` for a plant with no such unit.
    """
    heating = [BACKUP_NAMES[role] for role in BACKUP_ROLES["heating"] if units_of(plant, role)]
    if any(isinstance(module, ElectricBoiler) for _, module in plant.named_modules()):
        heating.append("Electric boiler")
    if service == "heating":
        return {"main": "Geothermal", "other": " and ".join(heating) or None}
    driven = [plant.get_submodule(path) for path in _heat_driven(plant)]
    main = [
        f"{name} chiller (geothermal)"
        for cls, name in ((AdsorptionChiller, "Adsorption"), (AbsorptionUnit, "Absorption"))
        if any(isinstance(module, cls) for module in driven)
    ]
    other = ["Electric chiller"] if any(
        isinstance(plant.get_submodule(path), HeatPump) for path in units_of(plant, "chiller")
    ) else []
    other += [f"{name} (chiller drive)" for name in heating] if driven else []
    return {"main": " and ".join(main) or "Geothermal", "other": " and ".join(other) or None}


def _per_day(table, failed, labels):
    """Return the days of ``table`` summed, with their failed ticks, as rows in display units."""
    days = table.groupby(_days(table.index)).sum()
    counts = pd.Series(1, index=_days(failed)).groupby(level=0).sum()
    days = days.reindex(days.index.union(counts.index), fill_value=0.0)
    days["failed_steps"] = counts.reindex(days.index, fill_value=0).astype(int)
    rows = []
    for date, day in days.sort_index().iterrows():
        row = {"date": date, "source": _source(day)}
        row |= {key: measure(float(day[key]), "J") for key in KEYS}
        row |= {"no_demand": bool(not day["failed_steps"] and day["demand"] <= 0), "labels": labels}
        rows.append(row | {"failed_steps": measure(int(day["failed_steps"]), "-")})
    return shown(rows, by_si_unit())


def daily_coverage(plant, case, results):
    """Return, for each service of the plant, what covered its demand on each day of a run.

    A day is a calendar day of the case's time, which is UTC, so a day of a run in a DST zone
    needs no care. A tick belongs to the day it starts in. A service the plant has no consumer
    for is left out.

    Parameters
    ----------
    plant : Module
        The plant that produced ``results``.
    case : Case
        The case of the run; the days are those of its ticks, so it is not read.
    results : Results
        A finished ``simulate`` or ``replay``.

    Returns
    -------
    dict
        ``{service: [day, ...]}`` for ``"heating"`` and ``"cooling"``, the days in time order,
        each ``{date, source, demand, geothermal, electricity, backup, short, failed_steps,
        no_demand, labels}``;
        ``to_plain``
        gives the JSON. The energies are ``gm.units.Quantity`` values in the display unit of
        energy (``gm.units.display.DISPLAY_UNITS``, MWh) and ``failed_steps`` a count (unit
        ``-``). ``date`` is ``YYYY-MM-DD``; ``demand`` is the heat (or cold) the
        consumers asked for, which is ``geothermal + electricity + backup + short``;
        ``electricity`` is the compressor work of the heating heat pumps (zero for cooling), so
        that ``geothermal`` is the brine's heat alone; ``backup`` is the part
        given by the units whose role is ``boiler`` or ``chp`` and by an electric boiler (heating;
        shared with the heat-driven chillers' drive by what each took of the water), or by a
        compression chiller and the backup's share of a heat-driven chiller's cold (cooling),
        ``geothermal`` the rest of what was delivered and ``short`` the unmet demand.
        ``failed_steps`` is the number of ticks of the day that failed, were skipped, or show no
        demand; they add no energy, as in ``gm.evaluate.totals``, but a day with one is ``short``.
        ``source`` is the one the day is drawn with: ``short`` when a step failed or the unmet
        demand is above a millionth of the day's demand, else ``backup`` when the backup gave more
        than that, else ``geothermal``. ``no_demand`` is true for a day whose consumers asked
        for nothing (and no step failed): it is drawn as neither the plant nor the backup.
        ``labels`` ``{main, other}`` name what ``geothermal`` and ``backup`` are in this plant,
        from its units (heating ``Geothermal`` and ``Peak boiler``; cooling ``Absorption chiller
        (geothermal)`` and ``Electric chiller``), ``other`` ``None`` when the plant has none.

        The sum of ``geothermal + electricity + backup`` over the days is the
        ``heat_useful`` (``cold_useful``) of ``gm.evaluate.totals``, and over ``demand`` it gives
        ``heating_coverage`` (``cooling_coverage``) as their ratio.
    """
    frame = results.to_frame()
    seconds = results.durations
    stamps = pd.DatetimeIndex(pd.to_datetime([row["time"] for row in results.errors()], utc=True))
    covered = {}
    for service, read in SERVICES.items():
        useful, unmet = read(plant, frame)
        if useful is None or unmet is None:
            continue
        table, unknown = _energies(plant, frame, seconds, service, useful, unmet)
        failed = unknown.union(stamps).unique()
        covered[service] = _per_day(table, failed, _labels(plant, service))
    return covered
