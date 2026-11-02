"""Bounds, requirements, failures and the verdict of a finished run."""

import json
import math
from copy import deepcopy

import numpy as np
import pytest

import gemini as gm
from gemini._utils.jsonable import to_plain
from gemini.engine import apply
from gemini.evaluate.verdict import ranked
from gemini.modules import CoolingGrid, HeatingGrid
from gemini.units import Quantity
from tests.fixtures.cases import costed_economics, make_case, requirement
from tests.fixtures.costed_plants import day, heating_plant
from tests.fixtures.engine_plants import TICKS, holder_plant, pair_frame, pair_plant
from tests.fixtures.errors import raises
from tests.fixtures.result_tables import make_results
from tests.unit.evaluate.test_summary import overflowing
from tests.unit.study.conftest import shallow_case, shallow_plant


def test_values_inside_the_declared_limits_pass():
    """A return temperature above 0 K is inside the Temperature limit; NaN is a missing tick."""
    results = make_results({"heat": {"return_out.temperature": [300.0, math.nan, 310.0]}})
    assert to_plain(gm.evaluate.bounds(heating_plant(), None, results)) == {
        "name": "bounds",
        "passed": True,
        "value": {"value": 0, "unit": "-"},
        "limit": {"value": 0, "unit": "-"},
    }


def test_values_outside_the_limits_are_counted():
    """Two of three temperatures are not above 0 K."""
    results = make_results({"heat": {"return_out.temperature": [300.0, -1.0, 0.0]}})
    result = gm.evaluate.bounds(heating_plant(), None, results)
    assert result["passed"] is False and result["value"].value == 2


def test_nothing_with_a_limit_is_undecided():
    """An output without a limit gives ``passed`` None and says so."""
    results = make_results({"heat": {"unmet_demand": [1.0]}})
    result = gm.evaluate.bounds(heating_plant(), None, results)
    assert result["passed"] is None
    assert result["value"].reason == "no recorded output has a declared limit"


def test_a_path_the_plant_lacks_is_refused():
    """Results of another plant raise with the path."""
    results = make_results({"elsewhere": {"return_out.temperature": [300.0]}})
    try:
        gm.evaluate.bounds(heating_plant(), None, results)
    except gm.errors.ValidationError as error:
        assert "elsewhere" in str(error)
    else:
        raise AssertionError("expected ValidationError")


def test_the_example_plant_run_stays_inside_its_limits(fresh_plant, fast_dataset):
    """A six-hour replay records no output outside a declared limit."""
    replay = gm.replay(fresh_plant, fast_dataset.window(None, "2024-07-01T06:00:00Z"))
    result = gm.evaluate.bounds(fresh_plant, None, replay)
    assert result["passed"] is True and result["value"].value == 0


@pytest.fixture(scope="module")
def failed_run():
    """Run the pair: ``first`` fails at two steps, ``second`` at one, and one step lacks data."""
    frame = pair_frame(
        {("level", 3): -1.0, ("level", 5): -1.0, ("level2", 7): -1.0, ("pressure", 9): np.nan}
    )
    engine = gm.Engine(pair_plant(), on_error="record")
    return engine.replay(gm.Dataset.from_frame(frame))


def test_rows_are_grouped_by_module_and_code_with_the_most_frequent_first(failed_run):
    """Each group has its count, first and last step and the message of its first row."""
    found = gm.evaluate.failures(failed_run)
    groups = {(group["path"], group["code"]): group for group in found.groups}
    first = groups[("first", "out_of_range")]
    assert (first["count"], first["kind"]) == (2, "failed")
    assert first["first"] == TICKS[3].isoformat() and first["last"] == TICKS[5].isoformat()
    assert "level = -" in first["message"]
    assert groups[("second", "out_of_range")]["count"] == 1
    skipped = groups[("first", "missing_value")]
    assert skipped["kind"] == "skipped" and skipped["first"] == TICKS[9].isoformat()
    counts = [group["count"] for group in found.groups]
    assert counts == sorted(counts, reverse=True) and found.groups[0] is first
    assert found.total == len(failed_run.errors()) == 5


def test_the_json_and_the_table_hold_the_same_groups(failed_run):
    """``to_dict`` needs no encoder and ``to_frame`` has one row per group."""
    found = gm.evaluate.failures(failed_run)
    plain = found.to_dict()
    assert json.loads(json.dumps(plain, allow_nan=False)) == plain
    frame = found.to_frame()
    assert len(frame) == len(found) == len(plain["groups"])
    assert frame["count"].tolist() == [group["count"] for group in plain["groups"]]


def test_a_run_without_failures_has_no_group():
    """The report of a clean run is empty, and its table keeps the columns."""
    engine = gm.Engine(pair_plant(), on_error="record")
    found = gm.evaluate.failures(engine.replay(gm.Dataset.from_frame(pair_frame())))
    assert found.to_dict() == {"total": 0, "groups": []}
    assert found.to_frame().empty and "count" in found.to_frame().columns


def test_a_failure_below_a_twin_is_grouped_under_the_path_of_the_failing_module():
    """The twin ``duo`` holds the booster ``front``: the group names the module that raised."""
    frame = pair_frame({("level", 3): -1.0, ("level", 4): -1.0})
    engine = gm.Engine(holder_plant(), on_error="record")
    found = gm.evaluate.failures(engine.replay(gm.Dataset.from_frame(frame)))
    assert [(group["path"], group["count"]) for group in found.groups] == [("duo.front", 2)]


HOUR = 3600.0


UNMET = [1.0, 5.0, 3.0, 0.0]


RUNNING = [1.0, 1.0, 0.0, 1.0]


def run(unmet=UNMET, operating=RUNNING):
    """Return a run of the heat consumer: its unmet demand [W] and whether it carried flow."""
    return make_results({"heat": {"unmet_demand": unmet, "operating": operating}})


def unmet(**kwargs):
    """Return a requirement on the unmet demand of every heating supply."""
    return requirement("heating_supply", "unmet", **kwargs)


def watts(value):
    """Return ``value`` watts."""
    return Quantity(value, "W")


def checked(*requirements, plant=None, results=None, supply=None):
    """Return the checks of ``requirements`` on a run."""
    case = make_case(count=4, requirements=list(requirements) or None, supply=supply)
    return gm.evaluate.requirements(plant or heating_plant(), case, results or run())


def only(*requirements, **parts):
    """Return the one check of ``requirements``."""
    (result,) = checked(*requirements, **parts)
    return result


def test_each_reports_the_worst_step_of_a_violated_maximum():
    """The second hour is the highest: its value, the limit and its time."""
    result = only(unmet(max=watts(4.0)))
    assert to_plain(result) == {
        "name": "heating_supply_unmet",
        "role": "heating_supply",
        "unit_path": "heat",
        "quantity": "unmet",
        "passed": False,
        "value": {"value": 5.0, "unit": "W"},
        "limit": {"value": 4.0, "unit": "W"},
        "worst_step": "2024-01-01T01:00:00+00:00",
    }


def test_each_passes_with_the_value_nearest_the_limit():
    """The highest value is still under the maximum."""
    result = only(unmet(max=watts(6.0)))
    assert result["passed"] is True and result["value"].value == 5.0
    assert result["limit"].value == 6.0


def test_each_with_two_bounds_reports_the_one_that_is_further_out():
    """Zero is 2 under the minimum, 5 is 1 over the maximum: the low end is further out."""
    result = only(unmet(min=watts(2.0), max=watts(4.0)), results=run(operating=[1] * 4))
    assert result["passed"] is False
    assert result["value"].value == 0.0 and result["limit"].value == 2.0
    assert result["worst_step"] == "2024-01-01T03:00:00+00:00"


def test_an_exact_rule_is_the_same_number_as_min_and_max():
    """A constant run meets its value; another value does not."""
    flat = run(unmet=[2.0] * 4, operating=[1] * 4)
    assert only(unmet(min=watts(2.0), max=watts(2.0)), results=flat)["passed"] is True
    assert only(unmet(min=watts(3.0), max=watts(3.0)), results=flat)["passed"] is False


def test_a_value_on_the_limit_passes_within_the_rounding_margin():
    """A relative 1e-9 of rounding does not fail a limit."""
    assert only(unmet(max=watts(5.0 * (1 - 1e-12))))["passed"] is True


@pytest.mark.parametrize(
    "over, figure",
    [("sum", 9.0), ("mean", 2.25), ("max", 5.0), ("min", 0.0)],
)
def test_an_aggregate_judges_one_figure_of_the_run(over, figure):
    """The figure is the value, the bound is the limit and no step is the worst."""
    flat = run(operating=[1] * 4)
    result = only(unmet(min=watts(figure - 1), max=watts(figure + 1), over=over), results=flat)
    assert result["passed"] is True
    assert to_plain(result["value"]) == {"value": figure, "unit": "W"}
    assert result["worst_step"] is None
    broken = only(unmet(max=watts(figure - 1), over=over), results=flat)
    assert broken["passed"] is False and broken["limit"].value == figure - 1


def test_running_leaves_out_the_steps_without_flow():
    """The 3 W of the idle hour does not count while the module is running."""
    idle = run(unmet=[4.0, 4.0, 0.5, 4.0])
    assert only(unmet(min=watts(1.0)), results=idle)["passed"] is False
    running = only(unmet(min=watts(1.0), when="running"), results=idle)
    assert running["passed"] is True and running["value"].value == 4.0


def test_a_module_that_never_ran_is_undecided():
    """No step counts: ``passed`` is None and the value says why."""
    result = only(unmet(max=watts(1.0), when="running"), results=run(operating=[0] * 4))
    assert result["passed"] is None
    assert to_plain(result["value"]) == {
        "value": None,
        "unit": "W",
        "reason": "the module carried no flow in this run",
    }
    assert to_plain(result["limit"]) == {"value": 1.0, "unit": "W"}


def test_duration_is_the_time_of_the_steps_that_count():
    """Three of four hours the module ran: 10800 s, within half a step of 3.4 hours."""

    def hours(count):
        return Quantity(count, "h")

    ran = only(unmet(min=hours(3), max=hours(3), over="duration", when="running"))
    assert to_plain(ran["value"]) == {"value": 3 * HOUR, "unit": "s"}
    assert ran["passed"] is True and ran["worst_step"] is None
    assert (
        only(unmet(min=hours(3.4), max=hours(3.4), over="duration", when="running"))["passed"]
        is True
    )
    far = only(unmet(min=hours(4), max=hours(4), over="duration", when="running"))
    assert far["passed"] is False
    assert to_plain(far["limit"]) == {"value": 4 * HOUR, "unit": "s"}


def test_duration_without_a_condition_counts_every_step_with_a_value():
    """Four hours, less the one that failed."""
    gap = run(unmet=[1.0, math.nan, 3.0, 0.0])
    assert only(unmet(min=Quantity(3 * HOUR, "s"), over="duration"), results=gap)["passed"]
    far = only(unmet(min=Quantity(4 * HOUR, "s"), over="duration"), results=gap)
    assert far["passed"] is False


def test_bounds_of_another_unit_are_stored_in_the_unit_of_the_field():
    """2 kW is 2000 W."""
    result = only(unmet(max=Quantity(2, "kW")))
    assert result["passed"] is True and result["limit"].value == 2000.0


def test_a_field_the_run_lacks_is_undecided():
    """The field exists on the module but the results hold no column of it."""
    results = make_results({"heat": {"surplus": [1.0] * 4, "operating": [1.0] * 4}})
    result = only(unmet(max=watts(1.0)), results=results)
    assert result["passed"] is None
    assert result["value"].reason.startswith("no_value")


def test_a_failed_run_with_only_missing_values_is_undecided():
    """Every row failed: no value."""
    result = only(unmet(max=watts(1.0)), results=run(unmet=[math.nan] * 4))
    assert result["passed"] is None and result["value"].reason.startswith("no_value")


def test_a_port_quantity_is_a_field():
    """The temperature of the supply port of a consumer, in kelvin."""
    results = make_results(
        {"heat": {"supply_in.temperature": [300.0, 320.0], "operating": [1.0, 1.0]}}
    )
    limit = requirement("heating_supply", "temperature", max=Quantity(40, "degC"))
    case = make_case(count=2, requirements=[limit])
    result = gm.evaluate.requirements(heating_plant(), case, results)[0]
    assert result["name"] == "heating_supply_temperature"
    assert result["passed"] is False and result["value"].value == 320.0
    assert result["limit"].value == pytest.approx(313.15)


def test_a_role_checks_each_of_its_units_on_its_own():
    """Two consumers, two answers."""
    plant = heating_plant()
    plant._add_module("heat2", HeatingGrid())
    results = make_results(
        {
            "heat": {"unmet_demand": [1.0], "operating": [1.0]},
            "heat2": {"unmet_demand": [9.0], "operating": [1.0]},
        }
    )
    case = make_case(count=1, requirements=[unmet(max=watts(5.0))])
    found = gm.evaluate.requirements(plant, case, results)
    assert [(item["unit_path"], item["passed"]) for item in found] == [
        ("heat", True),
        ("heat2", False),
    ]
    assert {item["role"] for item in found} == {"heating_supply"}


def test_a_role_without_a_unit_in_the_plant_is_one_undecided_check():
    """A plant with no doublet has nothing to judge by a doublet limit: no value, no error."""
    flow = requirement("doublet", "production_flow", max=Quantity(300, "m3/h"))
    (found,) = checked(flow)
    assert found["passed"] is None and found["unit_path"] is None
    assert found["role"] == "doublet" and found["name"] == "doublet_production_flow"
    assert found["value"].value is None and found["value"].reason.startswith("no_value")
    assert found["limit"].value == pytest.approx(300 / 3600) and found["limit"].unit == "m3/s"


def test_a_parameter_is_judged_as_the_plant_states_it():
    """The pump efficiency of a doublet, equal to 0.7."""
    plant = gm.Plant("One")
    plant.add("Doublet", name="d0", params={"pump_efficiency": 0.6})
    rule = requirement("doublet", "pump_efficiency", min=0.7, max=0.7)
    result = only(rule, plant=plant, results=make_results({"d0.esp": {"head": [1.0]}}))
    assert result["passed"] is False and result["worst_step"] is None
    assert result["value"].value == 0.6 and result["limit"].value == 0.7
    assert result["unit_path"] == "d0" and result["name"] == "doublet_pump_efficiency"


def test_a_parameter_without_a_value_is_undecided():
    """Nothing states it."""
    plant = gm.Plant("One")
    plant.add("Doublet", name="d0")
    rule = requirement("doublet", "pump_efficiency", min=0.7, max=0.7)
    result = only(rule, plant=plant, results=make_results({"d0.esp": {"head": [1.0]}}))
    assert result["passed"] is None and result["value"].reason.startswith("no_value")


@pytest.mark.parametrize("over", ["sum", "mean", "max", "min", "duration"])
def test_a_parameter_takes_no_over(over):
    """A parameter has no steps to aggregate: the requirement refuses ``over``."""
    rule = requirement("doublet", "pump_efficiency", max=0.7) | {"over": over}
    with raises(gm.errors.ValidationError, "invalid_value", match="over"):
        make_case(count=4, requirements=[rule])


def test_every_requirement_of_the_case_is_checked_in_order():
    """Two requirements, two checks."""
    found = checked(unmet(max=watts(9.0)), unmet(min=watts(0.0), name="unmet_least"))
    assert [item["name"] for item in found] == ["heating_supply_unmet", "unmet_least"]
    assert [item["passed"] for item in found] == [True, True]


def test_a_case_without_requirements_gives_no_checks():
    """Nothing to check."""
    assert checked() == []


def test_an_output_of_a_plant_is_read_through_the_leaves_it_names():
    """The brine cooling of a doublet is the riser's outlet less the injector's inlet."""
    plant = gm.Plant("One")
    plant.add("Doublet", name="d0")
    results = make_results(
        {
            "d0.riser": {"wellhead_out.temperature": [380.0, 390.0], "operating": [1.0, 1.0]},
            "d0.injector": {"wellhead_in.temperature": [340.0, 340.0], "operating": [1.0, 0.0]},
        }
    )
    cooling = requirement("doublet", "brine_cooling", max=Quantity(45, "K"))
    case = make_case(count=2, requirements=[cooling])
    assert gm.evaluate.requirements(plant, case, results)[0]["value"].value == 50.0
    case = make_case(count=2, requirements=[cooling | {"when": "running"}])
    found = gm.evaluate.requirements(plant, case, results)[0]
    assert found["passed"] is True and found["value"].value == 40.0


def test_the_supply_temperature_of_a_service_is_a_requirement():
    """The heating consumer asks for at least 100 degC at its supply port, while it runs."""
    supply = {"heating": Quantity(100, "degC")}
    cold = make_results(
        {"heat": {"supply_in.temperature": [380.0, 360.0], "operating": [1.0, 1.0]}}
    )
    case = make_case(count=2, supply=supply)
    (found,) = gm.evaluate.requirements(heating_plant(), case, cold)
    assert found["name"] == "heating_supply_temperature"
    assert found["role"] == "heating_supply" and found["quantity"] == "temperature"
    assert found["passed"] is False and found["value"].value == 360.0
    assert found["limit"].value == pytest.approx(373.15)
    warm = make_results(
        {"heat": {"supply_in.temperature": [380.0, 375.0], "operating": [1.0, 1.0]}}
    )
    assert gm.evaluate.requirements(heating_plant(), case, warm)[0]["passed"] is True


def test_the_cooling_requirement_is_a_maximum_and_a_service_without_one_adds_nothing():
    """The cooling consumer asks for at most 20 degC; the heating service gives no temperature."""
    plant = heating_plant()
    plant._add_module("cool", gm.modules.CoolingGrid())
    results = make_results(
        {"cool": {"supply_in.temperature": [290.0, 295.0], "operating": [1.0, 1.0]}}
    )
    case = make_case(count=2, supply={"heating": None, "cooling": Quantity(20, "degC")})
    (found,) = gm.evaluate.requirements(plant, case, results)
    assert found["unit_path"] == "cool" and found["passed"] is False
    assert found["value"].value == 295.0 and found["limit"].value == pytest.approx(293.15)


def test_a_minimum_intake_pressure_rejects_a_design_whose_suction_drops_below_it():
    """The lowest intake pressure of a doublet is judged against the minimum of the case."""
    plant = gm.Plant("One")
    plant.add("Doublet", name="d0")
    results = make_results(
        {"d0.esp": {"intake_pressure": [30e5, 8e5, 25e5], "operating": [1.0, 1.0, 1.0]}}
    )
    low = requirement("doublet", "intake_pressure", min=Quantity(10, "bar"))
    (found,) = checked(low, plant=plant, results=results)
    assert found["passed"] is False and found["name"] == "doublet_intake_pressure"
    assert found["value"].value == pytest.approx(8e5)
    held = requirement("doublet", "intake_pressure", min=Quantity(5, "bar"))
    assert only(held, plant=plant, results=results)["passed"] is True


def test_a_maximum_gas_fraction_at_the_intake_is_judged_per_step():
    """The role reads the fraction of the gas volume at the pump intake."""
    plant = gm.Plant("One")
    plant.add("Doublet", name="d0")
    results = make_results(
        {"d0.esp": {"gas_volume_fraction": [0.02, 0.2], "operating": [1.0, 1.0]}}
    )
    limit = requirement("doublet", "intake_gas_fraction", max=0.1)
    assert only(limit, plant=plant, results=results)["passed"] is False


def share(max, unmet=(0.5, 0.0, 0.25, 0.0), scale=1.0):
    """Return the check of the share of heat left unmet, the demand scaled by ``scale``."""
    wanted = requirement("heating_supply", "unmet_share", max=max, name="heat_delivered")
    supply = {"heating": Quantity(65, "degC")}
    case = make_case(count=4, requirements=[wanted], supply=supply)
    frame = case.demand.frame
    case.demand.__dict__["frame"] = frame * scale
    found = gm.evaluate.requirements(heating_plant(), case, run(list(unmet)))
    return next(item for item in found if item["name"] == "heat_delivered")


def test_an_unmet_share_is_the_unmet_energy_over_the_demand_of_the_case():
    """0.75 J of 4 J demanded: a number, not an undecided check."""
    result = share(0.1)
    assert result["passed"] is False
    assert result["value"].value == pytest.approx(0.1875)
    assert share(0.2)["passed"] is True


def test_a_service_with_no_demand_has_no_unmet_share():
    """Nothing demanded, nothing unmet: the share is 0."""
    result = share(0.01, scale=0.0)
    assert result["passed"] is True and result["value"].value == 0.0


def test_a_simulated_run_gives_the_share_left_unmet_when_the_heat_falls_short(tmp_path):
    """A shallow plant with small heat sources, two days: the share of heat and none of cold."""
    plant = shallow_plant()
    plant.set_params("heat_pump", {"capacity": Quantity(100, "kW")})
    plant.set_params("peak_boiler", {"capacity": Quantity(100, "kW")})
    case = shallow_case(days=2, folder=tmp_path)
    results = gm.simulate(plant, case)
    shares = [
        requirement("heating_supply", "unmet_share", max=1, name="heat_delivered"),
        requirement("cooling_supply", "unmet_share", max=1, name="cold_delivered"),
    ]
    data = case.to_dict() | {"requirements": shares}
    found = gm.evaluate.requirements(plant, gm.Case.from_dict(data, folder=tmp_path), results)
    by_name = {item["name"]: item for item in found}
    frame = results.to_frame()
    wanted = case.demand.frame["heating_demand"].sum()
    left = frame["heating_consumer.unmet_demand"].sum() / wanted
    assert 0.0 < left < 1.0
    assert by_name["heat_delivered"]["value"].value == pytest.approx(left)
    assert by_name["cold_delivered"]["value"].value >= 0.0


BASE = 1e6


GAINS = [2e3, 5e3, 3e3, 4e3]


BOUGHT = [1e3, 4e3, 2e3, 3e3]


BOUNDS = ("min", "max")


def plant():
    """Return the plant with a heat pump, a compression chiller and the two grids."""
    return gm.plants.get("HeatingHeatPumpCoolingPlant")


def run_requirements_outputs(**extra):
    """Return a run: the heat pump heats by ``GAINS`` [W], and the grid sells nothing."""
    columns = {
        "heat_pump": {
            "sink_in.enthalpy_flow": [BASE] * 4,
            "sink_out.enthalpy_flow": [BASE + gain for gain in GAINS],
            "source_in.enthalpy_flow": [BASE] * 4,
            "source_out.enthalpy_flow": [BASE - gain for gain in GAINS],
            "operating": RUNNING,
        },
        "electricity_grid": {"net_import": BOUGHT, "operating": [1.0] * 4},
    }
    return make_results(columns | extra)


def verdicts(*requirements, results=None):
    """Return the checks of ``requirements`` on the plant."""
    case = make_case(count=4, requirements=list(requirements))
    return gm.evaluate.requirements(plant(), case, results or run_requirements_outputs())


def limit(role, quantity, **kwargs):
    """Return a requirement with bounds in watts."""
    bounds = {name: Quantity(value, "W") for name, value in kwargs.items() if name in BOUNDS}
    rest = {name: value for name, value in kwargs.items() if name not in BOUNDS}
    return requirement(role, quantity, **bounds, **rest)


def test_a_heat_output_over_its_limit_fails_with_name_value_and_limit():
    """The heat pump gives 5 kW at its peak; the limit is 4 kW."""
    (found,) = verdicts(limit("heat_pump", "heat_output", max=4e3))
    assert found["name"] == "heat_pump_heat_output" and found["passed"] is False
    assert found["unit_path"] == "heat_pump" and found["value"].value == 5e3
    assert found["limit"].value == 4e3 and found["worst_step"] == "2024-01-01T01:00:00+00:00"
    (found,) = verdicts(limit("heat_pump", "heat_output", max=6e3))
    assert found["passed"] is True


def test_a_cold_output_is_read_on_the_source_side_of_a_compression_chiller():
    """The heat pump of the plant is a heat pump; the chiller role finds none of the same name."""
    found = verdicts(limit("chiller", "cold_output", max=1e9), results=run_requirements_outputs())
    assert [item["unit_path"] for item in found] == ["compression_chiller"]
    assert found[0]["passed"] is None and "no_value" in found[0]["value"].reason


def test_the_cold_output_of_a_heat_pump_in_cooling_mode_is_its_source_side():
    """A heat pump whose source reaches the cooling grid takes cold out of its source circuit."""
    results = run_requirements_outputs(
        compression_chiller={
            "source_in.enthalpy_flow": [BASE] * 4,
            "source_out.enthalpy_flow": [BASE - gain for gain in GAINS],
            "operating": RUNNING,
        }
    )
    (found,) = verdicts(limit("chiller", "cold_output", max=4e3), results=results)
    assert found["passed"] is False and found["value"].value == 5e3


def test_plant_figures_are_read_from_the_edge_modules():
    """The bought electricity is the grid import, the plant is the unit with path ''."""
    (found,) = verdicts(limit("plant", "electricity_bought", max=3e3))
    assert found["unit_path"] == "" and found["name"] == "plant_electricity_bought"
    assert found["passed"] is False and found["value"].value == 4e3
    (found,) = verdicts(limit("plant", "electricity_bought", max=5e3))
    assert found["passed"] is True


def test_a_plant_without_a_gas_grid_figure_gives_no_value():
    """The run holds no gas column: undecided, not a crash."""
    (found,) = verdicts(limit("plant", "gas_bought", max=1.0))
    assert found["passed"] is None and "no_value" in found["value"].reason


@pytest.mark.parametrize(
    ("over", "bounds", "value"),
    [
        ("sum", {"max": 1e3}, 10e3),
        ("mean", {"max": 1e3}, 2.5e3),
        ("max", {"max": 1e3}, 4e3),
        ("min", {"min": 5e3}, 1e3),
    ],
)
def test_every_aggregate_reads_a_new_quantity(over, bounds, value):
    """The figure of the run, judged against a bound it breaks."""
    (found,) = verdicts(limit("plant", "electricity_bought", over=over, **bounds))
    assert found["passed"] is False and found["value"].value == value
    assert found["worst_step"] is None


def test_duration_counts_the_hours_a_quantity_is_over_its_bound():
    """The heat pump runs three of four hours."""
    rule = requirement(
        "heat_pump", "heat_output", over="duration", when="running", max=Quantity(2, "h")
    )
    (found,) = verdicts(rule)
    assert found["passed"] is False and found["value"].value == 3 * 3600.0


def test_when_running_leaves_out_the_steps_without_flow():
    """The idle third step has the lowest output; running steps start at 2 kW."""
    (found,) = verdicts(limit("heat_pump", "heat_output", over="min", min=2.5e3, when="running"))
    assert found["passed"] is False and found["value"].value == 2e3
    (found,) = verdicts(limit("heat_pump", "heat_output", over="min", min=2.5e3))
    assert found["value"].value == 2e3


def test_co2_is_the_mass_of_each_step_and_sums_to_the_co2_of_the_run():
    """The sum over the steps of the plant's co2 is ``gm.evaluate.co2``."""
    utilities = {"electricity": {"co2_intensity": Quantity(1e-7, "kg/J")}}
    rule = requirement("plant", "co2", over="sum", max=Quantity(1, "kg"))
    case = make_case(count=4, requirements=[rule], utilities=utilities)
    results = run_requirements_outputs()
    (found,) = gm.evaluate.requirements(plant(), case, results)
    total = gm.evaluate.co2(plant(), case, results).value
    assert found["value"].unit == "kg" and found["value"].value == pytest.approx(total)
    assert found["passed"] == (total <= 1.0)


GAS = {
    "gas_makeup": {
        "gas_in.mass_flow": [0.4, 0.2, 0.0, 0.5],
        "excess_out.mass_flow": [0.1, 0.0, 0.0, 0.3],
        "operating": [1.0] * 4,
    },
    "flare": {"burned_mass_flow": [0.1, 0.0, 0.0, 0.3], "operating": [1.0] * 4},
}
"""A run that makes 0.4, 0.2, 0, 0.5 kg/s of gas: the boiler burns what the flare does not."""


def burned(rule):
    """Return the check of ``rule`` on a run with co-produced gas."""
    (found,) = verdicts(rule, results=run_requirements_outputs(**GAS))
    return found


def test_the_co_produced_gas_burned_is_a_mass_flow_of_the_plant():
    """The boiler burns 0.3, 0.2, 0 and 0.2 kg/s, the flare 0.1, 0, 0 and 0.3: 0.5 kg/s at most."""
    assert gm.plants.roles()["plant"]["gas_burned"] == {"dimension": "mass_flow", "over": True}
    rule = requirement("plant", "gas_burned", over="max", max=Quantity(0.55, "kg/s"))
    found = burned(rule)
    assert found["passed"] is True and found["value"].unit == "kg/s"
    assert found["value"].value == pytest.approx(0.5)


def test_a_requirement_on_the_gas_burned_fails_above_its_limit():
    """0.5 kg/s in the last step is above 0.45 kg/s; the mean 0.275 kg/s is below it."""
    over = requirement("plant", "gas_burned", over="max", max=Quantity(0.45, "kg/s"))
    found = burned(over)
    assert found["passed"] is False
    mean = requirement("plant", "gas_burned", over="mean", max=Quantity(0.45, "kg/s"))
    assert burned(mean)["passed"] is True
    in_tonnes = requirement("plant", "gas_burned", over="max", max=Quantity(1.2, "t/h"))
    assert burned(in_tonnes)["passed"] is False


def test_a_flare_alone_burns_gas_too():
    """A plant that sends its gas to a flare without a makeup reports the flare's mass flow."""
    results = run_requirements_outputs(
        flare={"burned_mass_flow": [0.2, 0.2, 0.2, 0.2], "operating": [1.0] * 4}
    )
    rule = requirement("plant", "gas_burned", over="sum", max=Quantity(1.0, "kg/s"))
    (found,) = verdicts(rule, results=results)
    assert found["value"].value == pytest.approx(0.8)


def test_a_plant_that_burns_no_gas_gives_no_value():
    """The run holds no gas column: undecided, not a crash."""
    rule = requirement("plant", "gas_burned", over="max", max=Quantity(1.0, "kg/s"))
    (found,) = verdicts(rule)
    assert found["passed"] is None and "no_value" in found["value"].reason


def test_the_plant_role_is_listed():
    """The table and the capabilities name it."""
    assert list(gm.plants.roles()["plant"]) == [
        "electricity_bought",
        "gas_bought",
        "heat_surplus",
        "co2",
        "gas_burned",
    ]
    assert all("plant" in item["roles"] for item in gm.plants.capabilities().values())


def test_a_wrong_quantity_of_the_plant_is_refused():
    """Closed table."""
    with raises(gm.errors.ValidationError, "invalid_value"):
        make_case(count=4, requirements=[requirement("plant", "cop", max=Quantity(1, "W"))])


def test_a_figure_the_run_lacks_gives_no_value_also_when_running():
    """The empty series meets the flags of the steps: undecided, not a crash."""
    (found,) = verdicts(limit("plant", "gas_bought", max=1.0, when="running"))
    assert found["passed"] is None and "no_value" in found["value"].reason


def test_the_requirements_of_the_case_join_the_verdict():
    """A requirement that fails is a reason of kind requirement and makes the run infeasible."""
    results = make_results(
        {"heat": {"unmet_demand": [7.0], "return_out.temperature": [300.0], "operating": [1.0]}}
    )
    limit = requirement("heating_supply", "unmet", max=gm.units.Quantity(5.0, "W"))
    found = gm.evaluate.verdict(heating_plant(), make_case(count=1, requirements=[limit]), results)
    assert found["feasible"] is False
    assert "heating_supply_unmet" in {item["name"] for item in found["reasons"]}


def test_one_failure_fails_the_run():
    """A negative fuel power fails the energy ledger and the whole verdict."""
    results = make_results({"heat": {"fuel": [-1.0], "return_out.temperature": [300.0]}})
    found = gm.evaluate.verdict(heating_plant(), make_case(), results)
    assert found["feasible"] is False


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
    assert item["violation"] == pytest.approx((423.15 - 373.15) / 423.15)


def test_a_service_the_run_does_not_deliver_is_a_requirement_reason():
    """A heating plant asked for cold has no cold delivered."""
    plant = heating_plant()
    case = make_case(supply={"heating": Quantity(60, "degC"), "cooling": Quantity(7, "degC")})
    found = gm.evaluate.verdict(plant, case, day())
    assert kinds(found)["cold_delivered"] == "requirement"
    (item,) = [item for item in found["reasons"] if item["name"] == "cold_delivered"]
    assert "violation" not in item and item not in ranked(found)


def test_a_name_gives_one_reason_even_when_two_checks_raise_it():
    """A requirement and the service of the same name are one reason, as for an absent supply."""
    from gemini.evaluate.verdict import _distinct, reason

    first = reason("requirement", "cold_delivered", "the run gives no cold_delivered")
    again = reason("requirement", "cold_delivered", "requirement on the same name")
    assert _distinct([first, again]) == [first]


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


@pytest.fixture(scope="module")
def sample_run(tmp_path_factory):
    """Return the shallow sample plant sized for one day, the case and the run within its limits."""
    case = shallow_case(days=1, folder=tmp_path_factory.mktemp("days"))
    plant = gm.study.size(shallow_plant(), case)
    return plant, case, gm.simulate(plant, case)


def test_a_sample_plant_in_breach_of_its_esp_limit_runs_every_row_and_gets_a_bound_reason(
    sample_run,
):
    """The limit lives in the plant: a breach changes no number, and the verdict names a bound."""
    plant, case, held = sample_run
    assert gm.evaluate.verdict(plant, case, held)["feasible"] is True
    plant = deepcopy(plant)
    plant.set_params("d0.esp", {"minimum_intake_pressure": Quantity(1e4, "bar")})
    run = gm.simulate(plant, case)
    (item,) = gm.evaluate.verdict(plant, case, run)["reasons"]
    assert (
        item["kind"] == "bound" and item["name"] == "intake_pressure" and item["path"] == "d0.esp"
    )
    assert len(run.to_frame()) == len(held.to_frame()) and not run.errors()
    assert run.to_frame().fillna(0).equals(held.to_frame().fillna(0))
