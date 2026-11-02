"""Reading a plant file: every issue at once, with the path into the file."""

import copy

import pytest

import gemini as gm
from gemini.errors import ValidationError
from gemini.plants._utils import reader
from tests.fixtures.plant_files import file_of, issues


@pytest.fixture
def spec():
    """Return a valid file with a group, a named port and an output."""
    return file_of(
        "DoubletHeatPlant",
        modules={
            "degasser": {"type": "Degasser"},
            "filters": {"type": "ModuleDict", "modules": {"hot": {"type": "Filter"}}},
            "pipe": {"type": "Pipe"},
        },
        connections=[{"source": "degasser.liquid_out", "target": "filters.hot.fluid_in"}],
        inlets={"feed": "degasser.fluid_in", "pipe_in": "pipe.fluid_in", "air": "pipe.air_in"},
        outlets={
            "product": "filters.hot.fluid_out",
            "gas": "degasser.gas_out",
            "pipe_out": "pipe.fluid_out",
            "pipe_loss": "pipe.loss_out",
        },
        outputs={"loss": {"difference": ["pipe.fluid_in.p", "pipe.fluid_out.p"]}},
        params={"pipe": {"length": {"value": 100, "unit": "ft"}}},
    )


def problems_of(spec, **changes):
    """Return the problems of a copy of ``spec`` with top-level ``changes``, each as a dict."""
    data = copy.deepcopy(spec)
    return [item.problem() for item in issues(data | changes if isinstance(data, dict) else data)]


def wiring_problems_of(spec, **changes):
    """Return the problems of ``problems_of`` without the ports the case leaves unconnected."""
    return [item for item in problems_of(spec, **changes) if item["code"] != "unconnected_port"]


def test_an_unconnected_port_is_reported_with_its_path(spec):
    """A port no connection or plant name uses is one problem with the port path."""
    del spec["outlets"]["gas"]
    found = problems_of(spec)
    assert [(item["code"], item["path"]) for item in found] == [
        ("unconnected_port", "degasser.gas_out")
    ]
    with pytest.raises(ValidationError) as caught:
        gm.Plant.from_dict(spec)
    assert caught.value.code == "unconnected_port" and caught.value.problems == found


def test_a_valid_spec_has_no_problems(spec):
    """The base file builds."""
    assert issues(spec) == []


def test_every_problem_is_reported_at_once_with_its_path(spec):
    """Several mistakes give several problems, none raised."""
    spec["modules"]["degasser"]["type"] = "Degaser"
    spec["params"]["pipe"] = {
        "length": {"value": 2, "unit": "bar"},
        "lenght": {"value": 1, "unit": "m"},
        "diameter": {"value": -1, "unit": "m"},
    }
    found = [item.problem() for item in issues(spec)]
    codes = {item["path"]: item["code"] for item in found}
    assert codes["modules.degasser.type"] == "unknown_name"
    assert codes["params.pipe.length.unit"] == "invalid_unit"
    assert codes["params.pipe.lenght"] == "unknown_name"
    assert found[0]["suggestions"][0] == "Degasser"


def test_an_out_of_bounds_value_has_its_own_code(spec):
    """A value below its minimum is ``out_of_bounds``."""
    spec["params"]["pipe"] = {"length": {"value": -5.0, "unit": "m"}}
    (item,) = problems_of(spec)
    assert item["code"] == "out_of_bounds" and item["path"] == "params.pipe.length"


def test_a_range_outside_the_bounds_and_an_option_outside_the_list_are_issues(spec):
    """Range ends and options are judged as the value is, all at once."""
    spec["params"]["pipe"] = {
        "length": {"value": 5.0, "unit": "m", "range": {"min": -1.0, "max": 10.0}},
    }
    spec["modules"]["hx"] = {"type": "HeatExchanger"}
    spec["params"]["hx"] = {"arrangement": {"value": "parallel", "options": ["parallel", "nope"]}}
    found = {item["path"]: item["code"] for item in problems_of(spec)}
    assert found["params.pipe.length.range.min"] == "out_of_bounds"
    assert found["params.hx.arrangement.options"] == "invalid_value"


def test_a_leaf_with_an_unknown_key_or_no_unit_is_an_issue(spec):
    """An unknown key and a quantity without its unit are reported on the leaf."""
    spec["params"]["pipe"] = {
        "length": {"value": 5.0, "mode": 1},
        "inner_diameter": {"value": 0.1},
    }
    found = {item["path"]: item["code"] for item in problems_of(spec)}
    assert found["params.pipe.length.mode"] == "unknown_name"
    assert found["params.pipe.inner_diameter.unit"] == "invalid_unit"


def test_wiring_rules_report_the_connection_and_the_field(spec):
    """Each wiring rule has its code and points at ``connections[i].source|target``."""
    spec["modules"]["pipe2"] = {"type": "Pipe"}
    spec["modules"]["filter2"] = {"type": "Filter"}
    del spec["inlets"]["pipe_in"], spec["outlets"]["pipe_out"]
    cases = {
        "unknown_name": ("pipe.fluid_out", "filter.hot.fluid_in", "target"),
        "unknown_port": ("pipe.outlt", "pipe2.fluid_in", "source"),
        "port_in_use": ("pipe.fluid_out", "filters.hot.fluid_in", "target"),
        "stream_mismatch": ("degasser.gas_out", "filter2.fluid_in", "target"),
        "invalid_connection": ("pipe", "pipe2.fluid_in", "source"),
    }
    for code, (source, target, field) in cases.items():
        extra = {"source": source, "target": target}
        found = wiring_problems_of(spec, connections=spec["connections"] + [extra])
        assert [(item["code"], item["path"]) for item in found] == [
            (code, f"connections[1].{field}")
        ], code


def test_ambiguous_ports_are_listed(spec):
    """A bare module name needs a port in a file; an ambiguous pair is refused elsewhere."""
    spec["modules"]["splitter"] = {"type": "Splitter"}
    spec["connections"].append({"source": "splitter", "target": "pipe.fluid_in"})
    (item,) = wiring_problems_of(spec)
    assert item["code"] == "invalid_connection"
    assert item["suggestions"] == ["splitter.branch1_out", "splitter.branch2_out"]


def test_a_failed_module_does_not_bury_the_report_in_follow_ups(spec):
    """Connections and sections naming a module that did not build are not reported again."""
    spec["modules"]["degasser"]["type"] = "Degaser"
    spec["fluids"] = {"degasser": {}}
    assert [item["path"] for item in problems_of(spec)] == ["modules.degasser.type"]


def test_shape_and_format_problems(spec):
    """Unknown keys, wrong types and old files are problems, not exceptions."""
    found = problems_of(spec, modul={}, modules=[])
    assert {"modul", "modules"} <= {item["path"] for item in found}
    assert problems_of({"version": 1})[0]["code"] == "old_format"
    assert problems_of({"format": 2, "type": "Doublet"})[0]["code"] == "old_format"
    assert problems_of([])[0]["code"] == "invalid_value"
    assert problems_of({"format": 1, "kind": "plant", "name": 3})[0]["path"] == "name"
    assert problems_of({"format": 1, "kind": "case", "name": "x"})[0]["code"] == "invalid_format"


def test_sections_are_checked_per_path(spec):
    """Fluids, boundary and the history of a leaf name the path in the problem."""
    spec["params"]["pipe"]["length"]["history"] = [{"valid_from": "2020-01-01", "value": -1}]
    found = problems_of(spec, fluids={"nowhere": {}}, boundary={"pipe": []})
    assert {item["path"] for item in found} == {
        "fluids.nowhere",
        "boundary.pipe",
        "params.pipe.length.history[0]",
    }


def test_read_raises_one_error_that_lists_every_problem(spec):
    """``from_dict`` raises a ``ValidationError`` with all messages and the first path."""
    spec["modules"]["degasser"]["type"] = "Degaser"
    spec["params"]["pipe"] = {"lenght": {"value": 1, "unit": "m"}}
    with pytest.raises(ValidationError) as caught:
        reader.from_dict(gm.Plant, spec)
    assert caught.value.path == "modules.degasser.type"
    assert "params.pipe.lenght" in str(caught.value)


def test_a_value_the_case_holds_is_refused_naming_where_it_lives(spec):
    """A ground value is ``invalid_value``, and so is a bare number with a unit."""
    spec["params"]["pipe"] = {"length": 5.0}
    (item,) = problems_of(spec)
    assert (item["path"], item["code"]) == ("params.pipe.length", "invalid_unit")
    plant = file_of("Doublet", type="Doublet", params={"gradient": {"value": 30, "unit": "K/km"}})
    (found,) = problems_of(plant)
    assert found["code"] == "invalid_value" and "site.ground.gradient" in found["message"]


OWNED = [
    ("GasGrid", "composition", {"CH4": 1.0}, "utilities.gas.composition"),
    ("HeatingGrid", "return_pressure", "6 bar", "demand.heating.return_pressure"),
    (
        "HeatingGrid",
        "minimum_return_temperature",
        "30 degC",
        "demand.heating.minimum_return_temperature",
    ),
    ("CoolingGrid", "return_pressure", "4 bar", "demand.cooling.return_pressure"),
    (
        "CoolingGrid",
        "maximum_return_temperature",
        "18 degC",
        "demand.cooling.maximum_return_temperature",
    ),
    ("CoolingGrid", "dew_point_margin", "1 K", "demand.cooling.dew_point_margin"),
    ("CoolingGrid", "indoor_temperature", "26 degC", "demand.cooling.indoor_temperature"),
    ("CoolingGrid", "indoor_relative_humidity", 0.5, "demand.cooling.indoor_relative_humidity"),
    ("Desander", "sand_concentration", "20 mg/l", "site.fluid.sand_concentration"),
    ("Atmosphere", "pressure", "101325 Pa", "site.air.pressure"),
    ("ElectricityGrid", "import_limit", "6 MW", "utilities.electricity.import_limit"),
    ("ElectricityGrid", "export_limit", "6 MW", "utilities.electricity.export_limit"),
]
"""A module, a leaf it declares with a ``case`` path, a value for it, and the case path."""


def _leaf(value):
    """Return the leaf object of ``"6 bar"``, a number, or a composition."""
    if isinstance(value, str):
        number, unit = value.split()
        return {"value": float(number), "unit": unit}
    return {"value": value}


@pytest.mark.parametrize(("module", "leaf", "value", "where"), OWNED)
def test_a_value_the_case_owns_is_refused_whatever_the_declaration(module, leaf, value, where):
    """A parameter or a boundary the case gives is no design value: a plant leaf names its path."""
    plant = file_of(
        "Owned", modules={"unit": {"type": module}}, params={"unit": {leaf: _leaf(value)}}
    )
    found = [item for item in problems_of(plant) if item["path"] == f"params.unit.{leaf}"]
    assert [item["code"] for item in found] == ["invalid_value"]
    assert where in found[0]["message"]
