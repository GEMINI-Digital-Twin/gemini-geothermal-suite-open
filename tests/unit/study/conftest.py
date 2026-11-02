"""A shallow plant and case, and a run replaced by a cost model, shared by the study tests."""

from datetime import timedelta

import pandas as pd
import pytest

import gemini as gm
from gemini._utils.files import from_json
from gemini.case._utils.kinds import EQUIPMENT_KINDS
from gemini.engine.chunks import ResultChunk
from gemini.errors.base import problem
from gemini.evaluate.verdict import LARGEST_VIOLATION, Verdict, reason
from gemini.plants.roles import units_of
from gemini.study._utils import execute, trial
from gemini.units import Quantity
from gemini.units.shapes import measure
from tests.fixtures.result_tables import START, make_results
from tests.fixtures.sample_cases import SHALLOW_DISTRICT

SAMPLE = SHALLOW_DISTRICT
COUNT_COST = {1: 5.0, 2: 3.0, 3: 4.0}
"""The cost of a plant of 1, 2 and 3 doublets before the depth and the price are added."""


PLACEHOLDERS = {
    "money_per_length": {"value": 500, "unit": "EUR/m"},
    "money_per_power": {"value": 0.5, "unit": "EUR/W"},
    "money_per_conductance": {"value": 0.05, "unit": "EUR/(W/K)"},
    "money_per_volume": {"value": 500, "unit": "EUR/m3"},
    "money": {"value": 1e5, "unit": "EUR"},
}
"""A cost factor of each basis for a kind the sample case gives none: the test needs a number."""


def shallow_case(days=None, folder=None, uncertain=None, **sections):
    """Return the shallow sample case, priced for every kind, plus ``sections``.

    ``uncertain`` maps the dotted path of a number of the case to its ``uncertainty`` dict, as
    ``case.json`` writes it next to the value. ``days`` keeps only the first days of the sample
    demand, written to ``folder``, so that a real run is short.
    """
    data = from_json(SAMPLE / "case.json")
    data["economics"] = _priced(from_json(SAMPLE / data["economics"]))
    where = SAMPLE
    if days is not None:
        where = _cut(data, days, folder)
    for path, uncertainty in (uncertain or {}).items():
        *parents, last = path.split(".")
        node = data
        for part in parents:
            node = node[part]
        value = node[last]
        node[last] = {**value, "uncertainty": uncertainty}
    given = {key: item for key, item in (data | sections).items() if item is not None}
    return gm.Case.from_dict(given, folder=where)


def _priced(economics):
    """Return ``economics`` with a placeholder cost and fixed opex for each kind it gives none."""
    capex = economics["capex"]
    for kind, (basis, _) in EQUIPMENT_KINDS.items():
        capex.setdefault(kind, PLACEHOLDERS[basis])
    fixed = economics["opex"].setdefault("fixed", {})
    for kind in EQUIPMENT_KINDS:
        fixed.setdefault(kind, {"value": 2, "unit": "%/yr"})
    return economics


def _cut(data, days, folder):
    """Keep the first ``days`` of the demand of ``data``, written to ``folder``; return it."""
    file = data["demand"]["heating"]["power"]["file"]
    frame = pd.read_csv(SAMPLE / file).iloc[: 24 * days]
    (folder / file).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(folder / file, index=False)
    start = pd.Timestamp(data["time"]["start"])
    data["time"]["end"] = str(start + pd.Timedelta(days=days))[:10]
    for item in data["requirements"]:
        if item.get("over") == "duration":
            item["max"] = 20 * days
    return folder


def shallow_plant(backup=None):
    """Return the shallow sample plant, on one doublet, searching 1 to 3 doublets and 1 to 2 km.

    ``backup`` replaces the policy the file states.
    """
    plant = gm.Plant.from_json(SAMPLE / "plants/HeatingHeatPumpCoolingPlant.json")
    plant.set_range("size.doublets", min=1, max=3)
    plant.set_range("depth", min=gm.units.Quantity(1000, "m"), max=gm.units.Quantity(2000, "m"))
    if backup is not None:
        plant.set_params("", {"backup": backup})
    return plant


def cost_model(plant, case, results, name):
    """Return a metric of a plant by a cost that is known by hand.

    ``lcts`` is the count cost, plus the square of the distance of the depth to 1500 m in km, plus
    the electricity price in EUR/MWh over 1000; ``peak_heat`` is the capacity of the peak boiler.
    """
    count = len(units_of(plant, "doublet"))
    price = case.economics.energy.electricity * 3.6e9
    if name == "lcts":
        cost = COUNT_COST[count] + ((plant.depth - 1500) / 1000) ** 2 + price / 1000
        return measure(cost, "currency/J")
    if name == "co2":
        return measure(plant.depth / 1000, "kg")
    return measure(plant.get_submodule("peak_boiler").capacity, "W")


def clean_verdict(plant, case, results):
    """Return the verdict of a fake run: a failed step is the one reason, with its violation."""
    if not results.failures:
        return Verdict(feasible=True, reasons=[])
    found = reason("failed_step", "failed_steps", f"{len(results.failures)} steps failed")
    found["violation"] = LARGEST_VIOLATION
    return Verdict(feasible=False, reasons=[found])


@pytest.fixture
def runs(monkeypatch):
    """Replace the simulation of a trial by an empty result and its metrics by ``cost_model``.

    The fixture value lists the ``(plant, case, plan)`` of every simulation.
    """
    calls = []

    def fake(plant, case=None, plan=None):
        calls.append((plant, case, plan))
        return make_results({"users": {"unmet_demand": [0.0]}})

    monkeypatch.setattr(trial, "simulate", fake)
    monkeypatch.setattr(trial, "metric", cost_model)
    monkeypatch.setattr(trial, "verdict", clean_verdict)
    return calls


FAILS_ABOVE = 200
"""The electricity price [EUR/MWh] above which a run fails."""
FAILS_DEEPER = 1700
"""The depth [m] beyond which a run fails."""


@pytest.fixture
def failing_runs(runs, monkeypatch):
    """Like ``runs``, but the injected module ``d0.esp`` fails two steps of a run that is too dear.

    A run fails where the electricity price is above ``FAILS_ABOVE`` EUR/MWh or the depth is
    beyond ``FAILS_DEEPER``; the others run clean.
    """

    def fake(plant, case=None, plan=None):
        runs.append((plant, case, plan))
        results = make_results({"users": {"unmet_demand": [0.0, 0.0, 0.0]}})
        price = case.economics.energy.electricity * 3.6e9
        if price > FAILS_ABOVE or plant.depth > FAILS_DEEPER:
            errors = [(row, problem("d0.esp", "out_of_range", "flow too high")) for row in (0, 1)]
            later = [START + timedelta(hours=3), START + timedelta(hours=4)]
            results.commit(ResultChunk(later, [3600.0] * 2, {}, [{}] * 2, errors))
        return results

    monkeypatch.setattr(trial, "simulate", fake)
    return runs


class Report(dict):
    """A report of a fake run: figures and a verdict, with ``to_dict``."""

    def to_dict(self):
        """Return the figures as plain JSON."""
        return {key: item.to_dict() for key, item in self.items() if key != "verdict"}


class Series:
    """The results of a fake run."""

    def to_frame(self):
        """Return one row."""
        return pd.DataFrame({"x": [1.0]}, index=pd.DatetimeIndex(["2027-01-01"], name="time"))


@pytest.fixture
def fake_runs(runs, monkeypatch):
    """Replace the simulation and the report of a run: the cost model gives the figures.

    A plant on more than one doublet breaks a requirement.
    """

    def report(plant, case, results):
        count = len(units_of(plant, "doublet"))
        found = [] if count == 1 else [reason("requirement", "flow", "too many", violation=0.1)]
        cost = 6.0 - count + (plant.depth - 1500) ** 2 / 1e6
        return Report(
            lcts=Quantity(cost, "currency/J"),
            co2=Quantity(plant.depth, "kg"),
            verdict=Verdict(feasible=not found, reasons=found),
        )

    monkeypatch.setattr(execute, "simulate", lambda plant, case: Series())
    monkeypatch.setattr(execute, "reported", report)
    return runs


def searching(plant, **ranges):
    """Return ``plant`` that searches only ``ranges`` ``{path: (min, max)}``."""
    for path in plant.ranges:
        plant.set_range(path)
    for path, (low, high) in ranges.items():
        plant.set_range(path, min=low, max=high)
    return plant


@pytest.fixture
def folder(tmp_path):
    """Return a folder with the shallow case, a plant that searches its depth, one that does not."""
    shallow_case().to_json(tmp_path / "case.json")
    depth = (Quantity(1000, "m"), Quantity(2000, "m"))
    searching(shallow_plant(), depth=depth).to_json(tmp_path / "one.json")
    searching(shallow_plant()).to_json(tmp_path / "two.json")
    return tmp_path
