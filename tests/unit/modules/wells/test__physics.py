"""Path physics of the wells: a stream marched along a pipe path and the corrosion profile."""

import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from gemini import ops
from gemini.errors import ValidationError
from gemini.modules.wells import _physics
from gemini.physics import geometry
from gemini.streams.flows import Stream
from gemini.streams.fluid import BRINE, Fluid
from gemini.units import Quantity
from tests.fixtures.equivalence import assert_function_matches
from tests.fixtures.errors import raises
from tests.unit.test_golden import assert_values

GOLDEN = json.loads((Path(__file__).parents[3] / "fixtures/golden_values.json").read_text())


GAS = Fluid(gas_mass_fraction=0.01)


def _path(*diameters):
    """Return a vertical path of 100 m sections with the given internal diameters."""
    return geometry.PipePath(
        sections=[
            geometry.PipeSection(
                length=100, inclination=math.pi / 2, inner_diameter=d, roughness=2e-5
            )
            for d in diameters
        ]
    )


@pytest.mark.parametrize("role", ["production", "injection"])
def test_path_golden(role):
    """Path marching preserves every original section pressure and temperature."""
    case = GOLDEN["well_" + role]
    p = case["parameters"]
    u = case["inputs"]
    path = geometry.PipePath(
        sections=[
            geometry.PipeSection(length=length, inclination=a, inner_diameter=d, roughness=r)
            for length, a, d, r in zip(p["length"], p["angle"], p["diameter"], p["roughness"])
        ]
    )
    stream = SimpleNamespace(m_dot=u["flowrate"] * 1000, p=u["pressure"], T=u["temperature"])
    result = _physics.pipe_path_profile(
        path, stream, BRINE, u["direction"], 10, u["temperature_ambient"]
    )
    assert_values(
        dict(
            pressure_output=result.p_out,
            temperature_output=result.T_out,
            pressuredrop_fric_output=result.friction_pressure_drop,
            pressuredrop_grav_output=result.gravity_pressure_drop,
            section_pressure_output=result.section_pressure,
            section_temperature_output=result.section_temperature,
        ),
        case["expected"],
    )


def test_two_phase_reverse_flow_reverses_friction():
    """Negative two-phase flow formerly took the logarithm of a negative Reynolds number."""
    path = _path(0.18, 0.18)
    forward = Stream(
        m_dot=Quantity(40, "kg/s"), T=Quantity(350, "K"), p=Quantity(20e5, "Pa"), fluid=GAS
    )
    reverse = Stream(
        m_dot=Quantity(-40, "kg/s"), T=Quantity(350, "K"), p=Quantity(20e5, "Pa"), fluid=GAS
    )
    ahead = _physics.pipe_path_profile(path, forward, GAS, "down", 0, 300)
    back = _physics.pipe_path_profile(path, reverse, GAS, "down", 0, 300)
    assert back.friction_pressure_drop == pytest.approx(-ahead.friction_pressure_drop)
    assert back.gravity_pressure_drop == pytest.approx(ahead.gravity_pressure_drop)


def test_zero_flow_unknown_correlation_and_direction():
    """Preserve DPDT zero-flow behavior and reject unknown correlations and directions."""
    path = _path(0.18)
    stream = Stream(
        fluid=BRINE, m_dot=Quantity(0, "kg/s"), p=Quantity(1e6, "Pa"), T=Quantity(350, "K")
    )
    result = _physics.pipe_path_profile(path, stream, BRINE, "up", 10, 290)
    assert result.p_out == stream.p and result.T_out == stream.T
    assert result.friction_pressure_drop == result.gravity_pressure_drop == 0
    assert _physics.pipe_path_profile(path, stream, BRINE, " Up ", 10, 290) == result
    with raises(ValidationError, "unknown_name", match="'unknown'"):
        _physics.pipe_path_profile(path, stream, BRINE, "up", 10, 290, correlation="unknown")
    with pytest.raises(ValueError, match="direction = 'sideways'"):
        _physics.pipe_path_profile(path, stream, BRINE, "sideways", 10, 290)


def test_corrosion_profile_pairs_sections_in_traversal_order():
    """A capitalised direction formerly paired downward results with reversed sections."""
    path = _path(0.1, 0.3)
    stream = Stream(
        fluid=BRINE, m_dot=Quantity(40, "kg/s"), T=Quantity(350, "K"), p=Quantity(50e5, "Pa")
    )
    chemistry = {"co2_fraction": 0.05}
    lower = _physics.corrosion_profile(path, stream, BRINE, "down", 0, 350, chemistry, "DLD")
    upper = _physics.corrosion_profile(path, stream, BRINE, "Down", 0, 350, chemistry, "DLD")
    assert upper == lower
    assert lower[0] != lower[1]


def _profile(path, fluid, direction):
    """Return a physics function of the stream fields, so a traced stream is seen as traced."""

    @ops.physics
    def profile(m_dot, p, T):
        stream = Stream._si(m_dot=m_dot, p=p, T=T, fluid=fluid)
        result = _physics.pipe_path_profile(path, stream, fluid, direction, 10, 290)
        return dict(
            p_out=result.p_out,
            T_out=result.T_out,
            friction_pressure_drop=result.friction_pressure_drop,
            gravity_pressure_drop=result.gravity_pressure_drop,
            **{f"p{i}": value for i, value in enumerate(result.section_pressure)},
            **{f"T{i}": value for i, value in enumerate(result.section_temperature)},
        )

    return profile


@pytest.mark.parametrize("direction", ["up", "down"])
@pytest.mark.parametrize("fluid", [BRINE, GAS], ids=["liquid", "two_phase"])
def test_pipe_path_profile_matches_on_arrays(fluid, direction):
    """Forward, reverse and zero flow match on arrays, for liquid and two-phase fluids."""
    rows = [(40, 20e5, 350), (-40, 20e5, 350), (0, 20e5, 350), (5, 1e5, 330), (400, 1e5, 330)]
    profile = _profile(_path(0.18, 0.1), fluid, direction)
    profile.__name__ = "pipe_path_profile"
    assert_function_matches(profile, rows)


def test_two_phase_zero_flow_in_a_steep_downhill_section_returns_zero_drops():
    """Zero flow with free gas leaves pressure and temperature, even where Beggs-Brill fails."""
    path = geometry.PipePath(
        sections=[
            geometry.PipeSection(
                length=100, inclination=-math.pi / 4, inner_diameter=0.1778, roughness=2e-5
            )
        ]
    )
    stream = Stream(
        m_dot=Quantity(0, "kg/s"), p=Quantity(1e6, "Pa"), T=Quantity(350, "K"), fluid=GAS
    )
    result = _physics.pipe_path_profile(path, stream, GAS, "down", 10, 290)
    assert (result.p_out, result.T_out) == (1e6, 350)
    assert result.friction_pressure_drop == result.gravity_pressure_drop == 0


def test_two_phase_zero_flow_rows_match_on_arrays_in_a_steep_downhill_section():
    """Stopped rows cross the failing Beggs-Brill checks of a steep section without raising."""
    path = geometry.PipePath(
        sections=[
            geometry.PipeSection(
                length=100, inclination=-math.pi / 4, inner_diameter=0.1778, roughness=2e-5
            )
        ]
    )
    profile = _profile(path, GAS, "down")
    profile.__name__ = "pipe_path_profile"
    assert_function_matches(profile, [(0, 1e6, 350), (0, 5e5, 330)])


def test_corrosion_profile_matches_on_arrays():
    """The corrosion rate of every section of the marched profile matches on arrays."""

    @ops.physics
    def profile(m_dot, p, T):
        stream = Stream._si(m_dot=m_dot, p=p, T=T, fluid=BRINE)
        rates = _physics.corrosion_profile(
            _path(0.1, 0.3), stream, BRINE, "down", 0, 350, {"co2_fraction": 0.05}, "DLD"
        )
        return {f"rate{index}": rate for index, rate in enumerate(rates)}

    profile.__name__ = "corrosion_profile"
    assert_function_matches(profile, [(40, 50e5, 350), (10, 30e5, 340), (-40, 50e5, 350)])


def test_the_gas_superficial_velocity_is_the_gas_mass_flow_over_its_density_and_area(monkeypatch):
    """10 kg/s with x = 1e-3 of gas at 1.976 kg/m3 in a 0.2 m pipe is 0.1611 m/s, by hand.

    m_g = 1e-3 * 10 = 0.01 kg/s, A = pi 0.2**2 / 4 = 0.03142 m2, us_g = 0.01 / 1.976 / 0.03142.
    """
    seen = {}

    def spy(us_g, us_l, *rest):
        seen.update(us_g=us_g, us_l=us_l)
        return 0.0, 0.0

    monkeypatch.setattr(_physics, "beggs_brill_dp", spy)
    fluid = Fluid(gas_mass_fraction=1e-3)
    path = geometry.PipePath(
        sections=[
            geometry.PipeSection(
                length=100.0, inclination=math.pi / 2, inner_diameter=0.2, roughness=1e-5
            )
        ]
    )
    stream = Stream(
        m_dot=Quantity(10.0, "kg/s"), T=Quantity(350.0, "K"), p=Quantity(2e6, "Pa"), fluid=fluid
    )
    _physics.pipe_path_profile(path, stream, fluid, "up", 0.0, 300.0)
    assert seen["us_g"] == pytest.approx(0.01 / 1.976 / (math.pi * 0.2**2 / 4), rel=1e-9)
