"""Leaves read against the declarations of the plant: units, bounds, options, history."""

import gemini as gm
from tests.fixtures.plant_files import file_of, issues


def plant_file(**params):
    """Return the file of a heating plant on one doublet with the given ``params``."""
    return file_of("x", type="HeatingPlant", size={"doublets": {"value": 1}}, params=params)


def found(**params):
    """Return ``{path: kind}`` of the issues of the file."""
    return {item.path: item.kind for item in issues(plant_file(**params))}


def test_a_leaf_without_a_value_is_a_template_not_an_issue():
    """``size`` completes it; ``check`` still lists it as missing."""
    data = plant_file(peak_boiler={"capacity": {"unit": "MW", "range": {"min": 1, "max": 5}}})
    assert issues(data) == []
    plant = gm.Plant.from_dict(data)
    assert "params.peak_boiler.capacity" in [item.path for item in plant.check()]
    assert plant.ranges["peak_boiler.capacity"].max == 5e6


def test_a_quantity_needs_a_unit_of_its_dimension_and_a_list_its_unit_too():
    """The unit is checked for a number and for each list a leaf holds."""
    assert found(peak_boiler={"capacity": {"value": 5}}) == {
        "params.peak_boiler.capacity.unit": "unit"
    }
    assert found(peak_boiler={"capacity": {"value": 5, "unit": "bar"}}) == {
        "params.peak_boiler.capacity.unit": "unit"
    }
    bad = {"correction_factors": {"value": [1.0, "a"]}}
    assert list(found(d0={"esp": bad})) == ["params.d0.esp.correction_factors.value[1].value"]


def test_a_list_leaf_names_its_unit_once_and_the_list_form():
    """A list with a wrong or no unit is one ``unit`` issue at its unit, not one per item."""
    leaf = {"value": [400.0, 150.0], "unit": "m3/h"}
    assert found(d0={"well": {"section_length": leaf}}) == {
        "params.d0.well.section_length.unit": "unit"
    }
    leaf = {"value": [400.0, 150.0]}
    assert found(d0={"well": {"section_length": leaf}}) == {
        "params.d0.well.section_length.unit": "unit"
    }
    (item,) = issues(plant_file(d0={"well": {"section_length": [400.0, 150.0]}}))
    assert item.path == "params.d0.well.section_length" and item.kind == "unit"
    assert "{'value': [<number>, ...], 'unit': <unit>}" in item.message
    assert "{'value': <number>" not in item.message


def test_a_leaf_with_an_uncertainty_or_an_unknown_key_is_refused():
    """A plant leaf has no uncertainty."""
    got = found(
        heat_exchanger={"fouling_threshold": {"value": 0.1, "uncertainty": {"kind": "uniform"}}}
    )
    assert got and all(
        path.startswith("params.heat_exchanger.fouling_threshold.uncertainty") for path in got
    )


def test_the_history_of_a_leaf_is_read_with_the_same_rules():
    """A dated value is judged by the declaration."""
    leaf = {"value": 100, "unit": "m", "history": [{"valid_from": "2020-01-01", "value": -2}]}
    assert list(found(heating_return_pipe={"length": leaf})) == [
        "params.heating_return_pipe.length.history[0]"
    ]
    leaf = {"value": 100, "unit": "m", "history": [{"value": 2}]}
    assert found(heating_return_pipe={"length": leaf}) == {
        "params.heating_return_pipe.length.history[0]": "missing"
    }
