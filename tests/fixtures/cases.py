"""Cases for the tests of what reads a finished run."""

from datetime import timedelta

import numpy as np

import gemini as gm
from gemini.case.roletable import TABLE
from gemini.units import Quantity
from tests.fixtures.result_tables import START


def make_case(
    count=24,
    step=3600.0,
    economics=None,
    utilities=None,
    supply=None,
    requirements=None,
    site=None,
):
    """Return a case of ``count`` steps of ``step`` seconds, as ``make_results`` makes a run.

    ``economics`` is the dict of an ``economics.json`` below its header (``costed_economics`` builds
    one) and ``utilities`` the dict of the ``utilities`` section, each value a ``Quantity`` or a
    number; ``supply`` is ``{"heating": Quantity, "cooling": Quantity}``, the supply temperatures of
    services whose demand is 1 W; ``requirements`` is a list of dicts for ``gm.case.Requirement``;
    ``site`` is the ``site`` section, ``make_site()`` when absent.
    """
    data = {
        "format": 1,
        "kind": "case",
        "name": "test",
        "time": {
            "start": START.isoformat(),
            "end": (START + timedelta(seconds=step * count)).isoformat(),
            "step": Quantity(step, "s"),
        },
        "site": make_site() if site is None else site,
    }
    if supply is not None:
        data["demand"] = _demand(supply)
    if utilities is not None:
        data["utilities"] = utilities
    if economics is not None:
        data["economics"] = economics
    if requirements is not None:
        data["requirements"] = requirements
    files = {}
    for name in ("site", "demand", "utilities", "economics"):
        if name in data:
            data[name] = _with_series(_leaves(data[name]), files, count, step)
    if "economics" in data:
        data["economics"] = {"format": 1, "kind": "economics", "name": "test"} | data["economics"]
    return gm.Case.from_dict(data, files=files)


def _leaves(data):
    """Return ``data`` with each bare number or text a ``{"value": ...}`` leaf."""
    if isinstance(data, dict):
        if "value" in data or "file" in data:
            return data
        return {key: _leaves(item) for key, item in data.items()}
    if isinstance(data, (int, float, str)):
        return {"value": data}
    return data


def _with_series(data, files, count, step):
    """Return ``data`` with each ``Quantity`` of an array turned into a CSV column in ``files``."""
    if isinstance(data, Quantity) and np.ndim(data.value) > 0:
        name = f"data/series{len(files)}.csv"
        times = [(START + timedelta(seconds=step * tick)).isoformat() for tick in range(count)]
        rows = "".join(f"{time},{float(value)!r}\n" for time, value in zip(times, data.value))
        files[name] = f"time,v\n{rows}".encode()
        return {"file": name, "column": "v", "unit": data.unit}
    if isinstance(data, dict):
        return {key: _with_series(item, files, count, step) for key, item in data.items()}
    if isinstance(data, list):
        return [_with_series(item, files, count, step) for item in data]
    return data


def requirement(on, quantity, min=None, max=None, name=None, over=True, when=None):
    """Return the dict of a ``gm.case.Requirement`` on ``quantity`` of the role ``on``.

    A bound is a number in the unit of the other, a ``Quantity`` or ``{"value", "unit"}``; every
    bound given as a quantity must share one unit. ``over`` is ``each`` for a per-step quantity
    and absent for the others unless a string says otherwise; ``name`` is ``<on>_<quantity>``.
    """
    bounds = {side: bound for side, bound in (("min", min), ("max", max)) if bound is not None}
    unit = next((_unit_of(bound) for bound in bounds.values() if _unit_of(bound)), None)
    data = {"name": name or f"{on}_{quantity}", "on": on, "quantity": quantity}
    if unit:
        data["unit"] = unit
    reads = TABLE.get(on, {}).get(quantity)
    if over is not None and reads is not None and reads.over:
        data["over"] = "each" if over is True else over
    if when is not None:
        data["when"] = when
    return data | {side: _number_of(bound) for side, bound in bounds.items()}


def _unit_of(bound):
    """Return the unit of a bound given as a quantity, else ``None``."""
    if isinstance(bound, Quantity):
        return bound.unit
    return bound.get("unit") if isinstance(bound, dict) else None


def _number_of(bound):
    """Return the number of a bound given as a quantity or a number."""
    if isinstance(bound, Quantity):
        return bound.value
    return bound["value"] if isinstance(bound, dict) else bound


def costed_economics(energy=None, revenue=None, **parts):
    """Return the ``economics`` of a case for the plants of ``costed_plants``.

    The heat consumer is a degasser of 1000 with a fixed opex of 1 %/yr (10 a year) and the cooling
    consumer a flare of 2000 at 3 %/yr (60 a year). ``energy`` and ``revenue`` are the prices, as
    the dicts of ``economics.energy`` and ``economics.revenue``; ``parts`` are the other sections
    and values of the economics, an ``opex`` dict adding to the fixed opex.
    """
    shares = {"degasser": Quantity(1, "%/yr"), "flare": Quantity(3, "%/yr")}
    opex = parts.pop("opex", {})
    economics = {
        "capex": {"degasser": Quantity(1000.0, "currency"), "flare": Quantity(2000.0, "currency")},
        "opex": {"fixed": shares} | opex,
    }
    if energy:
        economics["energy"] = energy
    if revenue:
        economics["revenue"] = revenue
    return economics | parts


def _demand(supply):
    """Return a demand of 1 W for each service of ``supply``."""
    demand = {}
    for service, value in supply.items():
        demand[service] = {"power": Quantity(1.0, "W")}
        if value is not None:
            demand[service]["supply_temperature"] = value
    return demand


def make_site():
    """Return the site of a case with a doublet: ground, reservoir, brine and air."""
    return {
        "ground": {
            "surface_temperature": Quantity(12, "degC"),
            "gradient": Quantity(30, "K/km"),
        },
        "reservoir": {
            "reference_depth": Quantity(2500, "m"),
            "thickness": Quantity(100, "m"),
            "permeability": Quantity(200, "mD"),
            "pressure": Quantity(250, "barg"),
        },
        "fluid": {
            "density": Quantity(1030, "kg/m3"),
            "viscosity": Quantity(0.4, "mPa.s"),
            "gas_liquid_ratio": Quantity(0.8, "Nm3/m3"),
            "dissolved_gas": {"CH4": 0.8, "CO2": 0.2},
        },
        "air": {"temperature": Quantity(10, "degC")},
    }
