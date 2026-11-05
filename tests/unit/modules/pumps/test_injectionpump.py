"""Mass conservation for InjectionPump."""

import pytest

from gemini.errors import PhysicsError, ValidationError
from gemini.evaluate._utils.pricing import capex_of, fixed_opex_of
from gemini.modules.pumps import InjectionPump
from gemini.physics import pumps
from gemini.streams.flows import Stream
from gemini.streams.fluid import BRINE
from gemini.units import Quantity
from tests.fixtures.cases import make_case
from tests.fixtures.equivalence import assert_module_matches
from tests.fixtures.errors import raises

CURVES = {
    "stage_count": 10,
    "pump_type": "unspecified",
    "head_coefficients": [100, -0.01, 0, 0, 0, 0],
    "power_coefficients": [1, 0.001, 0, 0, 0, 0],
}


def test_equipment_forward():
    """Equipment preserves mass and valid pressure/temperature."""
    c = InjectionPump().set_params("", {"stage_count": 10, "pump_type": "A", "efficiency": 0.65})
    result = c(
        fluid_in=Stream(
            fluid=BRINE, m_dot=Quantity(1, "kg/s"), T=Quantity(300, "K"), p=Quantity(1e6, "Pa")
        ),
        pressure_setpoint=2e6,
        frequency=60,
    )
    assert sum(s.m_dot for s in result.outlets.values() if isinstance(s, Stream)) == 1
    assert result.outlets["fluid_out"].T == 300
    assert result.outlets["fluid_out"].p >= 0


def _rows():
    return [
        dict(
            fluid_in=Stream(
                fluid=BRINE,
                m_dot=Quantity(m_dot, "kg/s"),
                T=Quantity(300, "K"),
                p=Quantity(p, "Pa"),
            ),
            pressure_setpoint=setpoint,
            frequency=60,
        )
        for m_dot, p, setpoint in [(1, 1e6, 2e6), (5, 2e6, 6e6), (0.5, 1e6, 1e6)]
    ]


def test_setpoint_matches_traced():
    """The setpoint branch traces and equals one call per row."""
    module = InjectionPump().set_params("", {"pump_type": "unspecified", "efficiency": 0.65})
    assert_module_matches(module, _rows())


def test_curves_match_traced():
    """The head and power curve branch traces and equals one call per row."""
    module = InjectionPump().set_params("", CURVES)
    rows = [{k: v for k, v in row.items() if k != "pressure_setpoint"} for row in _rows()]
    assert_module_matches(module, rows)


def test_a_setpoint_below_the_suction_needs_no_pumping():
    """A negative required head is no pumping: zero power, the outlet pressure is the inlet's."""
    pump = InjectionPump().set_params("", {"pump_type": "unspecified", "efficiency": 0.65})
    result = pump(
        fluid_in=Stream(
            fluid=BRINE, m_dot=Quantity(1, "kg/s"), T=Quantity(300, "K"), p=Quantity(2e6, "Pa")
        ),
        pressure_setpoint=1e6,
        frequency=60,
    )
    assert result.outputs.power == 0
    assert result.outputs.head == 0
    assert result.outputs.is_pumping is False
    assert result.outlets["fluid_out"].p == 2e6


def test_a_positive_head_is_pumping():
    """A setpoint above the suction pumps and says so."""
    pump = InjectionPump().set_params("", {"pump_type": "unspecified", "efficiency": 0.65})
    result = pump(
        fluid_in=Stream(
            fluid=BRINE, m_dot=Quantity(1, "kg/s"), T=Quantity(300, "K"), p=Quantity(1e6, "Pa")
        ),
        pressure_setpoint=2e6,
        frequency=60,
    )
    assert result.outputs.is_pumping is True
    assert result.outputs.power > 0


def test_a_curve_with_a_negative_head_is_still_an_error():
    """The head of a curve below zero is the curve outside its range, not a setpoint."""
    curves = {**CURVES, "head_coefficients": [-100, 0, 0, 0, 0, 0]}
    with pytest.raises(PhysicsError, match="below suction pressure"):
        InjectionPump().set_params("", curves)(
            fluid_in=Stream(
                fluid=BRINE, m_dot=Quantity(1, "kg/s"), T=Quantity(300, "K"), p=Quantity(2e6, "Pa")
            ),
            frequency=60,
        )


def test_a_stopped_pump_lets_the_pressure_through():
    """Without flow a setpoint below the suction is no error: the pump adds no pressure."""
    pump = InjectionPump().set_params("", {"pump_type": "unspecified", "efficiency": 0.65})
    result = pump(
        fluid_in=Stream(
            fluid=BRINE,
            m_dot=Quantity(0.0, "kg/s"),
            T=Quantity(320.0, "K"),
            p=Quantity(100e5, "Pa"),
        ),
        pressure_setpoint=30e5,
        frequency=60,
    )
    assert result.outlets["fluid_out"].p == 100e5
    assert result.outputs["head"] == 0.0


def test_a_pump_on_its_setpoint_needs_an_efficiency():
    """The efficiency has no default: the power of a setpoint needs one."""
    with raises(ValidationError, "missing_value"):
        InjectionPump()(
            fluid_in=Stream(
                fluid=BRINE, m_dot=Quantity(1, "kg/s"), T=Quantity(300, "K"), p=Quantity(1e6, "Pa")
            ),
            pressure_setpoint=2e6,
        )


def test_a_pump_on_its_curves_needs_no_efficiency():
    """Head and power curves give the power without it."""
    pump = InjectionPump().set_params("", CURVES)
    assert (
        pump(
            fluid_in=Stream(
                fluid=BRINE, m_dot=Quantity(1, "kg/s"), T=Quantity(300, "K"), p=Quantity(1e6, "Pa")
            ),
            frequency=60,
        ).outputs["power"]
        > 0
    )


def _economics(**capex):
    """Return the economics of a case that prices what ``capex`` names, with 2 %/yr fixed opex."""
    return make_case(
        economics={"capex": capex, "opex": {"fixed": {"injection_pump": Quantity(2, "%/yr")}}}
    ).economics


def _sized_pump():
    """Return a pump of 0.1 m3/s and 20 bar at an efficiency of 0.5: 400 kW of shaft power."""
    return InjectionPump().set_params(
        "",
        {
            "efficiency": 0.5,
            "nominal_flow": Quantity(0.1, "m3/s"),
            "nominal_head": Quantity(20, "bar"),
        },
    )


def test_the_capex_is_the_price_per_watt_of_the_shaft_power_at_the_nominal_flow():
    """The shaft power is the hydraulic power over the efficiency; the opex is a share of it."""
    economics = _economics(injection_pump=Quantity(0.5, "currency/W"))
    pump = _sized_pump()
    assert pump.equipment_kind == "injection_pump"
    assert capex_of(pump, economics) == pytest.approx(0.5 * 400000.0)
    assert fixed_opex_of(pump, economics) == pytest.approx(0.02 * 0.5 * 400000.0)


def test_the_capex_from_curves_is_the_power_curve_at_the_nominal_flow():
    """A pump with a power curve is sized by it, not by the efficiency."""
    pump = InjectionPump().set_params("", CURVES | {"nominal_flow": Quantity(0.1, "m3/s")})
    power = pumps.power(0.1, 60.0, 10, CURVES["power_coefficients"])
    assert capex_of(pump, _economics(injection_pump=Quantity(1, "currency/W"))) == pytest.approx(
        power
    )


def test_a_pump_without_a_price_raises_naming_the_path():
    """The case has no ``injection_pump`` capex: nothing is estimated."""
    economics = _economics(degasser=Quantity(1000.0, "currency"))
    with raises(ValidationError, "missing_assumption", "economics.capex.injection_pump"):
        capex_of(_sized_pump(), economics)


def test_a_pump_without_a_nominal_flow_raises_naming_it():
    """The design flow has no default."""
    pump = InjectionPump().set_params("", {"pump_type": "unspecified", "efficiency": 0.5})
    with raises(ValidationError, "missing_value", "nominal_flow"):
        capex_of(pump, _economics(injection_pump=Quantity(0.5, "currency/W")))


def test_a_pump_that_adds_no_head_costs_nothing():
    """A zero nominal head is no shaft power, so no capex and no fixed opex."""
    pump = InjectionPump().set_params(
        "",
        {
            "efficiency": 0.5,
            "nominal_flow": Quantity(0.1, "m3/s"),
            "nominal_head": Quantity(0, "bar"),
        },
    )
    economics = _economics(injection_pump=Quantity(0.5, "currency/W"))
    assert capex_of(pump, economics) == 0.0 and fixed_opex_of(pump, economics) == 0.0


def test_the_frequency_has_no_default():
    """The operating frequency is the designer's: a pump run without one says so."""
    pump = InjectionPump().set_params("", {"pump_type": "unspecified", "efficiency": 0.65})
    with raises(ValidationError, "missing_value", match="frequency"):
        pump(
            fluid_in=Stream(
                fluid=BRINE, m_dot=Quantity(1, "kg/s"), T=Quantity(300, "K"), p=Quantity(1e6, "Pa")
            ),
            pressure_setpoint=2e6,
        )


@pytest.mark.parametrize("flow", [0, -0.1])
def test_a_nominal_flow_of_zero_or_below_is_refused(flow):
    """A pump designed for no flow would be priced as free, so the door refuses it."""
    with raises(ValidationError, "out_of_bounds", "nominal_flow"):
        InjectionPump().set_params("", {"nominal_flow": Quantity(flow, "m3/s")})


def test_a_pump_may_have_no_nominal_flow():
    """``None`` still means not sized."""
    assert InjectionPump().set_params("", {"nominal_flow": None}).nominal_flow is None
