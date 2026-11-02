"""The one verdict of a run: each kind of reason, the apply-once rule and the report on it."""

from copy import deepcopy

import pytest

import gemini as gm
from gemini.modules import CoolingGrid
from gemini.run._utils import apply
from gemini.units import Quantity
from tests.fixtures.cases import costed_economics, make_case, requirement
from tests.fixtures.costed_plants import day, heating_plant
from tests.fixtures.engine_plants import pair_frame, pair_plant
from tests.fixtures.result_tables import make_results
from tests.unit.evaluate.test_totals import overflowing


def kinds(found):
    """Return ``{name: kind}`` of the reasons of a verdict."""
    return {item["name"]: item["kind"] for item in found["reasons"]}


def test_a_run_with_nothing_wrong_is_feasible():
    """A boiler run that closes its balances has no reason, and ``to_dict`` is plain JSON."""
    plant, run = overflowing()
    found = gm.evaluate.verdict(plant, make_case(), run)
    assert found["feasible"] is True and found["reasons"] == []
    assert found.to_dict() == {"feasible": True, "reasons": []}


def test_a_failed_requirement_is_a_reason_of_kind_requirement_with_its_name():
    """The boiler gives 100 degC water; the service asks for 150 degC."""
    plant, run = overflowing()
    case = make_case(supply={"heating": Quantity(150, "degC")})
    found = gm.evaluate.verdict(plant, case, run)
    assert found["feasible"] is False
    (item,) = [item for item in found["reasons"] if item["kind"] == "requirement"]
    assert item["name"] == "heating_supply_temperature" and item["path"] == "users"
    assert item["value"].si == pytest.approx(373.15) and item["limit"].si == pytest.approx(423.15)
    assert item["worst_step"] and "heating_supply_temperature" in item["message"]


def test_a_service_the_run_does_not_deliver_is_a_requirement_reason():
    """A heating plant asked for cold has no cold delivered."""
    plant = heating_plant()
    case = make_case(supply={"heating": Quantity(60, "degC"), "cooling": Quantity(7, "degC")})
    found = gm.evaluate.verdict(plant, case, day())
    assert kinds(found)["cold_delivered"] == "requirement"


def test_failed_rows_are_a_reason_of_kind_failed_step():
    """Five rows of the pair failed or were skipped."""
    frame = pair_frame({("level", 3): -1.0, ("level", 5): -1.0, ("pressure", 9): float("nan")})
    run = gm.Engine(pair_plant(), on_error="record").replay(gm.Dataset.from_frame(frame))
    found = gm.evaluate.verdict(pair_plant(), make_case(), run)
    assert kinds(found)["failed_steps"] == "failed_step"
    (item,) = [item for item in found["reasons"] if item["name"] == "failed_steps"]
    assert item["value"].value == len(run.errors())


def test_a_residual_beyond_the_balance_constants_is_a_numerical_reason():
    """A negative mass flow below the 1e-12 kg/s of the mass ledger."""
    units = {"heat": {"gas_mass_flow": "kg/s"}}
    run = make_results({"heat": {"gas_mass_flow": [-0.1, 0.0]}}, units=units)
    found = gm.evaluate.verdict(heating_plant(), make_case(count=2), run)
    assert kinds(found)["mass_balance"] == "numerical"
    (item,) = [item for item in found["reasons"] if item["name"] == "mass_balance"]
    assert item["limit"].value == 1e-12 and item["value"].value == pytest.approx(-0.1)


def test_a_value_outside_a_declared_limit_is_a_bound_reason():
    """Two of three temperatures are not above 0 K."""
    run = make_results({"heat": {"return_out.temperature": [300.0, -1.0, 0.0]}})
    found = gm.evaluate.verdict(heating_plant(), make_case(count=3), run)
    assert kinds(found)["bounds"] == "bound"


def test_an_operating_limit_of_a_module_is_a_bound_reason_and_never_changes_the_run():
    """The boiler burns 2 MW of fuel against a limit of 1 MW: one reason, all rows kept."""
    plant, run = overflowing()
    plant.boiler.capacity = Quantity(1e6, "W")
    plant.boiler.operating_limits = (("fuel", "max", "capacity"),)
    rows = len(run.to_frame())
    found = gm.evaluate.verdict(plant, make_case(), run)
    (item,) = [item for item in found["reasons"] if item["kind"] == "bound"]
    assert item["path"] == "boiler" and item["name"] == "fuel"
    assert item["value"].si > item["limit"].si == pytest.approx(1e6)
    assert item["worst_step"] and len(run.to_frame()) == rows


def test_an_operating_limit_with_no_value_for_its_parameter_is_no_limit():
    """The limit of 20 MW is not reached by 2 MW of fuel."""
    plant, run = overflowing()
    plant.boiler.operating_limits = (("fuel", "max", "capacity"),)
    assert gm.evaluate.verdict(plant, make_case(), run)["feasible"] is True


def count_copies(monkeypatch):
    """Return a list that gets one item per deep copy ``apply_case`` makes."""
    copies = []

    def counting(item):
        copies.append(item)
        return deepcopy(item)

    monkeypatch.setattr(apply, "deepcopy", counting)
    return copies


def test_report_applies_the_case_once(monkeypatch):
    """One copy of the plant for the whole report; the plant of the user is unchanged."""
    plant, run = overflowing()
    before = plant.to_dict() if hasattr(plant, "to_dict") else None
    copies = count_copies(monkeypatch)
    gm.evaluate.report(plant, make_case(), run)
    assert len(copies) == 1 and copies[0] is plant
    if before is not None:
        assert plant.to_dict() == before


def test_verdict_applies_the_case_once(monkeypatch):
    """The same for the verdict alone."""
    plant, run = overflowing()
    copies = count_copies(monkeypatch)
    gm.evaluate.verdict(plant, make_case(), run)
    assert len(copies) == 1


def test_report_carries_the_verdict_and_compare_reads_it():
    """The report holds the verdict; compare ranks the failing design after the feasible one."""
    plant, run = overflowing()
    good = gm.evaluate.report(plant, make_case(), run)
    case = make_case(supply={"heating": Quantity(150, "degC")})
    bad = gm.evaluate.report(plant, case, run)
    assert good["verdict"]["feasible"] is True and bad["verdict"]["feasible"] is False
    found = gm.evaluate.compare([bad, good], "capex")
    assert [entry["feasible"] for entry in found] == [False, True]
    assert found[0]["reasons"] == bad["verdict"]["reasons"]
    assert bad.to_dict()["verdict"]["reasons"][0]["kind"] == "requirement"


def test_two_economics_files_give_two_allocations_in_one_report():
    """The share of the cost charged to heat moves the cost of heat and of cold."""
    plant = heating_plant()
    plant._add_module("cool", CoolingGrid())
    run = day(cold=100.0)
    reports = []
    for share in (0.8, 0.5):
        economics = costed_economics(
            energy={"electricity": Quantity(2e-8, "currency/J")},
            discount_rate=0.05,
            analysis_period=Quantity(20, "yr"),
            accounting={"allocation": {"heat_cost_share": share}},
        )
        reports.append(gm.evaluate.report(plant, make_case(economics=economics), run))
    for report, share in zip(reports, (0.8, 0.5)):
        heat, cold = report["lcoh"], report["lcoc"]
        assert heat.value * heat.parts["energy"].value / share == pytest.approx(
            cold.value * cold.parts["energy"].value / (1 - share)
        )
    assert reports[0]["lcoh"].value != pytest.approx(reports[1]["lcoh"].value)


def test_the_requirement_of_the_case_is_a_reason_with_its_role_and_quantity():
    """A limit on the unmet heat that the run breaks."""
    limit = requirement("heating_supply", "unmet", max=Quantity(-1.0, "W"), name="no_unmet")
    found = gm.evaluate.verdict(heating_plant(), make_case(requirements=[limit]), day())
    (item,) = [item for item in found["reasons"] if item["name"] == "no_unmet"]
    assert item["kind"] == "requirement" and item["role"] == "heating_supply"
