"""``gm.check``: what the plant and the case need of each other."""

import gemini as gm
from gemini.run._utils.apply import apply_case
from gemini.units import Quantity
from tests.fixtures.sample_cases import HACKATHON_2026, SHALLOW_DISTRICT, sample_case, shallow_case


def sample():
    """Return the shallow sample plant and case, which are ready for each other."""
    return gm.Plant.from_json(SHALLOW_DISTRICT / "plant.json"), shallow_case()


def revised(case, change):
    """Return a case read again from the dict of ``case`` after ``change(data)``."""
    data = case.to_dict()
    if case.economics is not None:
        data["economics"] = case.economics.to_dict()
    change(data)
    return gm.Case.from_dict(data, files=case.files())


def paths(issues):
    """Return the paths of ``issues``."""
    return [item.path for item in issues]


def physics():
    """Return the shallow case as a pure physics case: no economics and no requirement."""

    def cut(data):
        del data["economics"]
        data["requirements"] = []

    return revised(shallow_case(), cut)


def storage_plant():
    """Return a plant of one thermal storage, a stateful module."""
    plant = gm.Plant()
    plant.add("ThermalStorage", name="storage")
    values = {"service": "hot", "volume": Quantity(2, "m3"), "charge_effectiveness": 1.0}
    values |= {"discharge_effectiveness": 1.0, "heat_loss_conductance": Quantity(10, "W/K")}
    values |= {"reference_temperature": Quantity(40, "degC")}
    values |= {"initial_temperature": Quantity(20, "degC")}
    return plant.set_params("storage", values)


def with_state(case, state):
    """Return the case with an ``initial_state``."""
    return revised(case, lambda data: data.update(initial_state=state))


def test_a_plant_and_a_case_that_fit_have_no_issue():
    """The sample is ready."""
    assert gm.check(*sample()) == []


def test_a_kind_without_a_capex_or_a_fixed_opex_is_named_with_its_path():
    """Both entries are needed for every kind of equipment the plant has."""
    plant, case = sample()

    def cut(data):
        del data["economics"]["capex"]["heat_pump"]
        del data["economics"]["opex"]["fixed"]["boiler"]

    found = gm.check(plant, revised(case, cut))
    assert sorted(paths(found)) == ["economics.capex.heat_pump", "economics.opex.fixed.boiler"]
    assert {item.kind for item in found} == {"missing"}
    assert {item.problem()["code"] for item in found} == {"missing_assumption"}


def test_a_case_without_economics_asks_no_price():
    """A pure physics run needs no capex, no opex and no energy price."""
    plant, case = sample()
    physics = revised(case, lambda data: data.pop("economics"))
    assert gm.check(plant, physics) == []


def test_a_requirement_on_a_role_the_plant_lacks_is_incompatible():
    """The role is in no unit of the plant: the path names the requirement."""
    plant, case = sample()
    limit = {"name": "chp_power", "on": "chp", "quantity": "power_output", "over": "each"}
    limit |= {"unit": "W", "min": 0}
    found = gm.check(plant, revised(case, lambda data: data["requirements"].append(limit)))
    (item,) = found
    assert item.kind == "incompatible" and item.path == f"requirements[{len(case.requirements)}].on"


def test_a_supply_role_the_plant_lacks_is_no_issue():
    """One case judges any plant: a heating-only plant meets the cooling service in the verdict."""
    plant = gm.Plant.from_json(HACKATHON_2026 / "plants/HeatingPlant.json")
    case = sample_case()
    assert "cooling_supply" in {item.on for item in case.requirements} or case.demand.cooling
    wanted = {"name": "cold", "on": "cooling_supply", "quantity": "unmet_share", "max": 0.1}
    found = gm.check(plant, revised(case, lambda data: data["requirements"].append(wanted)))
    assert found == []


def test_a_stateful_module_needs_an_initial_state_in_the_case():
    """Every state of a stateful module is given by the case."""
    plant, case = storage_plant(), physics()
    found = gm.check(plant, case)
    assert paths(found) == ["initial_state.storage.temperature"]
    state = {"storage": {"temperature": {"value": 60, "unit": "degC"}}}
    assert gm.check(plant, with_state(case, state)) == []


def test_an_initial_state_names_a_module_and_a_state_the_plant_has_in_a_unit_that_fits():
    """A module, a state or a dimension that does not fit is an issue with its path."""
    plant, case = storage_plant(), physics()
    state = {
        "storage": {"temperature": {"value": 60, "unit": "m"}, "fill": {"value": 1, "unit": "m"}},
        "boiler": {"temperature": {"value": 1, "unit": "K"}},
    }
    found = gm.check(plant, with_state(case, state))
    kinds = {item.path: item.kind for item in found}
    assert kinds == {
        "initial_state.storage.temperature": "unit",
        "initial_state.storage.fill": "unknown_key",
        "initial_state.boiler": "unknown_key",
    }


def test_the_case_state_is_where_a_stateful_module_starts():
    """The initial state of the applied plant is the case's, not the module's own default."""
    plant, case = storage_plant(), physics()
    state = {"storage": {"temperature": {"value": 60, "unit": "degC"}}}
    applied = apply_case(plant, with_state(case, state))
    assert applied.initial_state() == {"storage": {"temperature": 333.15}}
    assert plant.initial_state() == {"storage": {"temperature": 293.15}}


def test_a_least_cost_dispatch_needs_the_energy_prices():
    """The electricity price is read by the schedule, the gas price only with a gas unit."""
    plant, case = sample()

    def cut(data):
        del data["economics"]["energy"]["electricity"]

    found = gm.check(plant, revised(case, cut))
    assert paths(found) == ["economics.energy.electricity"]
    plant.set_params("", {"dispatch": "least_cost"})
    assert paths(gm.check(plant, revised(case, cut))) == ["economics.energy.electricity"]


def test_a_parameter_without_a_value_is_a_missing_issue_of_the_plant_file():
    """The path is that of the plant file."""
    data = gm.Plant.from_json(SHALLOW_DISTRICT / "plant.json").to_dict()
    del data["params"]["peak_boiler"]["capacity"]["value"]
    found = gm.check(gm.Plant.from_dict(data), shallow_case())
    assert paths(found) == ["params.peak_boiler.capacity"] and found[0].kind == "missing"


def test_simulate_raises_the_issues_of_the_check_first():
    """The same issues, in one error."""
    plant, case = sample()
    broken = revised(case, lambda data: data["economics"]["capex"].pop("heat_pump"))
    try:
        gm.simulate(plant, broken)
    except gm.errors.ValidationError as error:
        assert [item.path for item in error.issues] == ["economics.capex.heat_pump"]
    else:
        raise AssertionError("simulate did not raise")


def test_without_a_case_only_the_parameters_of_the_plant_are_checked():
    """A plant alone has no price, role or state to compare; the case's values are missing."""
    data = gm.Plant.from_json(SHALLOW_DISTRICT / "plant.json").to_dict()
    del data["params"]["peak_boiler"]["capacity"]["value"]
    found = gm.check(gm.Plant.from_dict(data), None)
    assert "params.peak_boiler.capacity" in paths(found)
    assert {item.kind for item in found} == {"missing"}
