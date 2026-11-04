"""One call of one module from plain JSON: shapes, units and errors."""

import json

import pytest

import gemini as gm
from gemini.modules import Port
from gemini.streams.fluid import BRINE, Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase
from gemini.units import Quantity
from gemini.units.quantities import Energy, Temperature
from tests.fixtures import si
from tests.fixtures.errors import raises
from tests.fixtures.esp_design import ESP_MODULE

ESP_PARAMETERS = {
    "stage_count": 12,
    "head_coefficients": [1.2e-10, -2.5e-6, 4e-3, 0.2, 5.0, 100.0],
    "power_coefficients": [1.0e-10, -1.0e-6, 3.0e-3, 0.3, 4.0, 200.0],
} | ESP_MODULE
SUCTION = {
    "fluid_in": {
        "fluid": {"kind": "brine"},
        "flow": {"value": 150, "unit": "m3/h"},
        "T": {"value": 80, "unit": "degC"},
        "p": {"value": 20, "unit": "bar"},
    }
}


def call(**changes):
    """Evaluate the ESP with the default JSON arguments, changed by keywords."""
    arguments = dict(
        module="ESP",
        parameters=ESP_PARAMETERS,
        inlets=SUCTION,
        controls={"frequency": {"value": 50, "unit": "Hz"}},
        units="si",
    )
    return gm.call(**(arguments | changes))


def test_evaluate_returns_outlets_and_outputs_with_units():
    """Outlet streams and outputs are ``{value, unit}`` in SI and the result is plain JSON."""
    result = call()
    assert result["errors"] == []
    discharge = result["outlets"]["fluid_out"]
    assert set(discharge) == {"m_dot", "T", "p"}
    assert discharge["m_dot"]["unit"] == "kg/s" and discharge["T"]["unit"] == "K"
    assert discharge["p"]["unit"] == "Pa" and discharge["p"]["value"] > 20e5
    assert result["outputs"]["head"]["unit"] == "Pa"
    json.dumps(result, allow_nan=False)


def test_evaluate_equals_a_direct_call_bit_for_bit():
    """The JSON call is the same call: a class, a name and a built module agree."""
    from gemini.modules.pumps import ESP

    direct = si.set_params(ESP(), "", ESP_PARAMETERS)(
        gm.Stream(
            fluid=BRINE,
            flow={"value": 150, "unit": "m3/h"},
            T={"value": 80, "unit": "degC"},
            p={"value": 20, "unit": "bar"},
        ),
        frequency={"value": 50, "unit": "Hz"},
    )
    for module in ("ESP", ESP):
        result = call(module=module)
        assert result["outlets"]["fluid_out"]["p"]["value"] == direct.outlets.fluid_out.p
        assert result["outputs"]["head"]["value"] == direct.outputs.head


def test_evaluate_accepts_quantities_in_any_unit_of_the_dimension():
    """A ``Quantity`` or its dict converts: the same call in K and in degC gives the same result."""
    fluid = {"kind": "brine"}
    kelvin = {
        "m_dot": Quantity(12.0, "kg/s"),
        "T": Quantity(353.15, "K"),
        "p": Quantity(2e6, "Pa"),
        "fluid": fluid,
    }
    celsius = {
        "m_dot": Quantity(12.0, "kg/s"),
        "T": Quantity(80, "degC"),
        "p": Quantity(20, "bar"),
        "fluid": fluid,
    }
    first = call(inlets={"fluid_in": kelvin})
    assert first["errors"] == []
    assert call(inlets={"fluid_in": celsius})["outlets"] == first["outlets"]


@pytest.mark.parametrize(
    ("changes", "path", "quantity"),
    [
        ({"parameters": ESP_PARAMETERS | {"setting_depth": 0}}, "setting_depth", "length"),
        ({"controls": {"frequency": 50.0}}, "frequency", "frequency"),
        (
            {"inlets": {"fluid_in": SUCTION["fluid_in"] | {"T": 353.15}}},
            "fluid_in.T",
            "temperature",
        ),
        ({"inlets": {"fluid_in": SUCTION["fluid_in"] | {"p": 2e6}}}, "fluid_in.p", "pressure"),
        (
            {"inlets": {"fluid_in": SUCTION["fluid_in"] | {"flow": 0.04}}},
            "fluid_in.flow",
            "volume flow",
        ),
        (
            {"inlets": {"fluid_in": SUCTION["fluid_in"] | {"m_dot": 12.0}}},
            "fluid_in.m_dot",
            "mass flow",
        ),
    ],
)
def test_a_bare_number_with_a_dimension_is_refused_naming_path_quantity_and_units(
    changes, path, quantity
):
    """Zero too: the message names the path, the quantity and the accepted units."""
    with raises(gm.errors.ValidationError, "invalid_value", match=quantity) as caught:
        call(**changes)
    assert caught.value.path == path and "accepted units" in str(caught.value)
    recorded = call(on_error="record", **changes)["errors"]
    assert [item["code"] for item in recorded] == ["invalid_value"]
    assert recorded[0]["path"] == path


def test_a_dimensionless_parameter_stays_a_plain_number():
    """The stage count and a fraction are numbers without a unit."""
    assert call(parameters=ESP_PARAMETERS | {"motor_efficiency": 0.9})["errors"] == []


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"module": "ESp"}, "unknown_name"),
        ({"module": 3}, "invalid_value"),
        ({"parameters": {}}, "missing_value"),
        ({"parameters": {"stage_count": "many"}}, "invalid_value"),
        ({"inlets": {}}, "invalid_call"),
        ({"controls": {"frequency": {"value": 50, "unit": "bar"}}}, "invalid_unit"),
        (
            {
                "inlets": {
                    "fluid_in": {
                        "flow": {"value": 1, "unit": "m3/h"},
                        "T": {"value": -5, "unit": "K"},
                        "p": {"value": 1, "unit": "bar"},
                    }
                }
            },
            "invalid_call",
        ),
    ],
)
def test_a_recorded_failure_returns_errors_instead_of_raising(changes, code):
    """Every failure is one ``GeminiError.to_dict()`` and the other parts are empty."""
    result = call(on_error="record", **changes)
    assert result["outlets"] == {} and result["outputs"] == {}
    assert [error["code"] for error in result["errors"]] == [code]
    assert set(result["errors"][0]) == {"path", "code", "message", "suggestions"}


def test_a_failing_call_raises_by_default():
    """``gm.evaluate`` has no never-raises rule: the same error reaches the caller."""
    with raises(gm.errors.ValidationError, "unknown_name") as caught:
        call(module="ESp")
    assert caught.value.suggestions == ("ESP",)
    with pytest.raises(gm.errors.ValidationError, match="on_error"):
        call(on_error="ignore")


def test_an_unknown_name_comes_with_suggestions():
    """The registry's close matches reach the error."""
    assert call(module="ESp", on_error="record")["errors"][0]["suggestions"] == ["ESP"]


def test_display_gives_quantities_in_the_display_units():
    """Pressure stays Pa (no display unit), power is in MW, and each value is a ``Quantity``."""
    shown = call(units="display")
    assert shown["errors"] == []
    power = shown["outputs"]["power"]
    assert isinstance(power, Quantity) and power.unit == "MW"
    assert shown["outlets"]["fluid_out"]["T"].unit == "degC"
    assert shown["outlets"]["fluid_out"]["m_dot"].unit == "kg/s"


def test_si_and_display_are_equal_after_conversion():
    """Every outlet field and output of the two results is the same quantity in SI."""
    plain, shown = call(units="si"), call(units="display")
    assert plain["outlets"].keys() == shown["outlets"].keys()
    for port, fields in plain["outlets"].items():
        for name, stored in fields.items():
            assert shown["outlets"][port][name].si == pytest.approx(
                Quantity.from_dict(stored).si, rel=1e-12
            )
    assert plain["outputs"].keys() == shown["outputs"].keys()
    for name, stored in plain["outputs"].items():
        found = shown["outputs"][name]
        if isinstance(stored["value"], (int, float)) and not isinstance(stored["value"], bool):
            assert found.si == pytest.approx(Quantity.from_dict(stored).si, rel=1e-12)
        else:
            assert found.value == stored["value"]


def test_a_temperature_difference_output_stays_in_kelvin():
    """A lift is a difference: converting it to degC would shift it by 273.15."""
    from gemini.units.display import DisplayedValues

    lift = DisplayedValues().value(5.0, "K", "temperature_difference")
    assert (lift.value, lift.unit) == (5.0, "K")
    level = DisplayedValues().value(300.0, "K", "temperature")
    assert level.unit == "degC" and level.value == pytest.approx(26.85)


def test_units_is_required_and_is_si_or_display():
    """There is no default, and a text outside the two choices is ``invalid_value``."""
    with pytest.raises(TypeError):
        gm.call("ESP", ESP_PARAMETERS, SUCTION, {})
    with raises(gm.errors.ValidationError, "invalid_value", match="si"):
        call(units="bar")
    failed = call(units={"pressure": "bar"}, on_error="record")["errors"][0]
    assert failed["code"] == "invalid_value" and failed["path"] == "units"
    assert call(units="displai", on_error="record")["errors"][0]["suggestions"] == ["display"]


def test_a_volume_flow_goes_in_as_flow_with_the_fluid_of_the_inlet():
    """``flow`` converts with the density of the fluid given for the inlet, at any unit."""
    brine = {"density": {"value": 1030.0, "unit": "kg/m3"}}
    for flow in ({"value": 150, "unit": "m3/h"}, {"value": 41.666666666666664, "unit": "l/s"}):
        inlets = {
            "fluid_in": {
                "flow": flow,
                "T": {"value": 80, "unit": "degC"},
                "p": {"value": 20, "unit": "bar"},
                "fluid": brine,
            }
        }
        discharge = call(inlets=inlets)["outlets"]["fluid_out"]
        assert discharge["m_dot"]["value"] == pytest.approx(150 / 3600 * 1030)


@pytest.mark.parametrize(
    "flow",
    [{"value": 150, "unit": "m3/h"}, {"value": 150, "unit": "m3/s"}, {"value": 40, "unit": "l/s"}],
)
def test_a_volume_flow_given_as_m_dot_points_to_flow(flow):
    """The code stays that of a wrong inlet; the path, message and suggestion name ``flow``."""
    inlets = {
        "fluid_in": {
            "fluid": {"kind": "brine"},
            "m_dot": flow,
            "T": {"value": 80, "unit": "degC"},
            "p": {"value": 20, "unit": "bar"},
        }
    }
    with raises(gm.errors.ValidationError, "invalid_call", match="give it as 'flow'") as caught:
        call(inlets=inlets)
    assert caught.value.path == "fluid_in.m_dot"
    assert caught.value.suggestions == ("flow",)
    recorded = call(inlets=inlets, on_error="record")["errors"][0]
    assert recorded["code"] == "invalid_call" and recorded["suggestions"] == ["flow"]


@pytest.mark.parametrize("flow", [{"value": 40, "unit": "kg/s"}, {"value": 144, "unit": "t/h"}])
def test_a_mass_flow_stays_a_mass_flow(flow):
    """A mass unit goes through ``m_dot`` unchanged."""
    inlets = {
        "fluid_in": {
            "fluid": {"kind": "brine"},
            "m_dot": flow,
            "T": {"value": 80, "unit": "degC"},
            "p": {"value": 20, "unit": "bar"},
        }
    }
    assert call(inlets=inlets)["outlets"]["fluid_out"]["m_dot"]["value"] == pytest.approx(40.0)


def test_another_wrong_unit_of_m_dot_keeps_its_error():
    """Only a volume flow has the suggestion."""
    inlets = {
        "fluid_in": {
            "m_dot": {"value": 40, "unit": "bar"},
            "T": {"value": 80, "unit": "degC"},
            "p": {"value": 20, "unit": "bar"},
        }
    }
    with raises(gm.errors.ValidationError, "invalid_call") as caught:
        call(inlets=inlets)
    assert caught.value.suggestions == ()


class _Broken(gm.modules.Module):
    """A module whose forward has a programming error."""

    def __init__(self):
        super().__init__()
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Raise a TypeError that is no input error."""
        raise TypeError("forward bug")


def test_an_error_inside_forward_is_not_reported_as_bad_input():
    """A TypeError of the module's own code stays a TypeError, also under on_error record."""
    for on_error in ("raise", "record"):
        with pytest.raises(TypeError, match="forward bug"):
            gm.call(
                module=_Broken,
                parameters={},
                inlets=SUCTION,
                controls={},
                units="si",
                on_error=on_error,
            )


class _Tank(gm.modules.Module):
    """A tank whose temperature rises by a rate [K/s], a number over the step."""

    def __init__(self):
        """Declare the rate, the temperature and the stored energy."""
        super().__init__()
        self.rate = gm.modules.Control(float)
        self.temperature = gm.modules.State(Temperature)
        self.stored = gm.modules.Output(Energy)

    def forward(self, inputs, inlets, state):
        """Return the energy of 1 J per K above 0 K."""
        return dict(stored=state["temperature"]), dict()

    def update(self, inputs, inlets, outlets, state, dt):
        """Return the temperature at the end of the step."""
        return {"temperature": state["temperature"] + inputs["rate"] * dt}


class _Pair(gm.modules.Module):
    """A composite of two tanks, to show the nested state."""

    def __init__(self):
        """Declare the children."""
        super().__init__()
        self.first = _Tank()

    def forward(self, inputs, inlets, state):
        """Call the tank."""
        self.first(rate=0.5, state=state["first"])
        return dict(), dict()


def stepping(units, **changes):
    """Call the tank at 20 degC with a rate of 0.5 K/s over one minute."""
    arguments = dict(
        module=_Tank,
        parameters={},
        inlets={},
        controls={"rate": 0.5},
        units=units,
        state={"temperature": Quantity(20, "degC")},
        dt=Quantity(1, "min"),
    )
    return gm.call(**(arguments | changes))


def test_a_stateful_module_returns_the_next_state_beside_the_result():
    """The state at the end of the step is 20 degC plus 30 K, in SI as a value dict."""
    result = stepping("si")
    assert result["state"] == {"temperature": {"value": pytest.approx(323.15), "unit": "K"}}
    assert result["outputs"]["stored"]["value"] == pytest.approx(293.15)
    json.dumps(result, allow_nan=False)


def test_the_next_state_in_display_units_feeds_the_next_call():
    """Display gives degC; passing that state back continues the same trajectory."""
    first = stepping("display")
    assert (first["state"]["temperature"].value, first["state"]["temperature"].unit) == (
        pytest.approx(50.0),
        "degC",
    )
    second = stepping("si", state=first["state"])
    assert second["state"]["temperature"]["value"] == pytest.approx(353.15)


def test_state_and_dt_are_required_only_for_a_stateful_module():
    """A module with state names what is missing; one without refuses them; a bare number too."""
    with raises(gm.errors.ValidationError, "missing_value", match="state"):
        stepping("si", state=None)
    with raises(gm.errors.ValidationError, "missing_value", match="dt"):
        stepping("si", dt=None)
    with raises(gm.errors.ValidationError, "invalid_value", match="temperature"):
        stepping("si", state={"temperature": 293.15})
    with raises(gm.errors.ValidationError, "invalid_call", match="no state"):
        call(state={"temperature": Quantity(1, "K")})
    assert call()["state"] == {}


def test_a_composite_takes_and_returns_the_state_by_child_name():
    """A plant's state is ``{child: {state: quantity}}``."""
    result = stepping(
        "si",
        module=_Pair,
        controls={},
        state={"first": {"temperature": Quantity(20, "degC")}},
    )
    assert result["state"]["first"]["temperature"]["value"] == pytest.approx(323.15)


@pytest.mark.parametrize("on_error", ["raise", "record"])
def test_a_control_given_as_a_parameter_says_it_belongs_in_controls(on_error):
    """No bare ``KeyError``: an ``invalid_call`` naming the control and ``controls``.

    The error is also a ``KeyError``, so a caller that caught the old one still does.
    """
    parameters = ESP_PARAMETERS | {"frequency": {"value": 50, "unit": "Hz"}}
    if on_error == "record":
        [error] = call(parameters=parameters, on_error="record")["errors"]
        assert error["code"] == "invalid_call" and error["path"] == "parameters.frequency"
        assert error["suggestions"] == ["controls"]
        return
    with raises(gm.errors.ValidationError, "invalid_call", match="is a control") as caught:
        call(parameters=parameters)
    assert isinstance(caught.value, KeyError)
    assert caught.value.path == "parameters.frequency" and "controls" in str(caught.value)


def test_set_params_of_a_control_says_where_it_belongs():
    """``set_params`` keeps ``unknown_name`` and says the name is a control for ``set_inputs``."""
    plant = gm.plants.HeatingPlant()
    with raises(gm.errors.ValidationError, "unknown_name", match="is a control") as caught:
        plant.set_params("d0.esp", {"frequency": {"value": 50, "unit": "Hz"}})
    assert "set_inputs" in str(caught.value)
