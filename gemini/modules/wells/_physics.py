"""A stream marched along a well's pipe path: pressure, temperature and the CO2 corrosion rate.

The marcher takes the ``Stream`` and the ``Fluid`` of the well (the property model of its brine and
gas), so it cannot sit in ``gemini.physics``, which knows no stream. It composes the correlations of
``gemini.physics.hydraulics`` (Darcy-Weisbach, Beggs-Brill), ``heat_transfer`` and ``corrosion`` for
the production and injection wells. The erosion check takes plain values and is
``gemini.physics.erosion.pipe_path_erosion_check``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gemini import ops
from gemini.errors import ValidationError
from gemini.physics import corrosion
from gemini.physics import fluid as fluid_physics
from gemini.physics import geometry, heat_transfer
from gemini.physics.constants import MIN_PATH_PRESSURE
from gemini.physics.hydraulics import beggs_brill_dp, darcy_weisbach_dp
from gemini.streams.flows import Stream
from gemini.streams.fluid import Fluid


@dataclass(frozen=True)
class PathResult:
    """Uncorrected path result: pressures [Pa], temperatures [K]."""

    p_out: float
    T_out: float
    friction_pressure_drop: float
    gravity_pressure_drop: float
    section_pressure: list[float]
    section_temperature: list[float]


@ops.physics
def pipe_path_profile(
    path: geometry.PipePath,
    stream: Stream,
    fluid: Fluid,
    direction: Literal["up", "down"],
    heat_transfer_coefficient: float,
    ambient_temperature: float,
    correlation: Literal["darcy_weisbach"] = "darcy_weisbach",
    correlation_2p: Literal["BeggsBrill"] = "BeggsBrill",
) -> PathResult:
    """March the pressure and temperature of a stream along a pipe path.

    Per section ``p_out = p -/+ (friction_pressure_drop + gravity_pressure_drop)`` and ``T_out = T
    -/+ dT``, with the drops of ``darcy_weisbach_dp`` (liquid only) or ``beggs_brill_dp`` (free
    gas) and the temperature change of ``heat_transfer.pipe_temperature_change``; the signs are
    those of the traversal direction.

    Parameters
    ----------
    path : PipePath
        Sections ordered from surface to bottom [m, rad].
    stream : Stream
        Inlet mass flow [kg/s], pressure [Pa] and temperature [K].
    fluid : Fluid
        Property model with properties(p, T).
    direction : str
        Traversal direction, 'up' or 'down' (case and surrounding spaces ignored); the flow
        sign is independent.
    heat_transfer_coefficient, ambient_temperature : float
        Heat transfer coefficient [W/m2/K] and ambient temperature [K].
    correlation, correlation_2p : str
        Single-phase and two-phase correlation names.

    Returns
    -------
    PathResult
        Uncorrected pressure [Pa], temperature [K], drops [Pa], and traversed profiles.

    Notes
    -----
    Valid where its section correlations are: steady single-phase or no-slip two-phase flow in
    circular pipes with the property snapshot of ``fluid``. Marched pressures never fall below
    ``MIN_PATH_PRESSURE`` (0.001 Pa), so a path whose drops exceed the inlet pressure keeps a
    positive absolute pressure, as in DPDT. Reference: the section equations (Swamee and Jain
    1976; Beggs and Brill 1973) marched as in GEMINI's DPDT; the loop over sections is
    configuration-sized and reads the plain path geometry.
    """
    direction, sections = _traversal(path, direction)
    if correlation != "darcy_weisbach" or correlation_2p != "BeggsBrill":
        raise ValidationError(
            f"pipe_path_profile: correlation = {correlation!r}, correlation_2p = "
            f"{correlation_2p!r}; expected 'darcy_weisbach' and 'BeggsBrill'",
            code="unknown_name",
        )
    p, T = stream.p, stream.T
    flow = fluid_physics.volume_flow(stream.m_dot, fluid.properties(p, T).density)
    pressures, temperatures = [], []
    friction_pressure_drop = gravity_pressure_drop = 0.0
    for section in sections:
        friction, gravity, delta_T = _section_drops(
            section, p, T, flow, fluid, heat_transfer_coefficient, ambient_temperature
        )
        if direction == "down":
            p, T = ops.maximum(MIN_PATH_PRESSURE, p + friction + gravity), T + delta_T
        else:
            p, T = ops.maximum(MIN_PATH_PRESSURE, p - friction - gravity), T - delta_T
        pressures.append(p)
        temperatures.append(T)
        friction_pressure_drop += friction
        gravity_pressure_drop += gravity
    return PathResult(p, T, friction_pressure_drop, gravity_pressure_drop, pressures, temperatures)


def _traversal(path, direction):
    """Return the normalised direction and the path sections in traversal order."""
    direction = direction.strip().lower()
    if direction not in {"up", "down"}:
        raise ValidationError(
            f"pipe path: direction = {direction!r}; expected 'up' or 'down'", code="unknown_name"
        )
    sections = path.sections if direction == "down" else list(reversed(path.sections))
    return direction, sections


def _section_drops(section, p, T, flow, fluid, heat_transfer_coefficient, ambient_temperature):
    """Return friction and gravity drops [Pa] and the temperature change [K] of one section.

    Two-phase reverse flow passes the velocity magnitudes to Beggs–Brill and reverses
    the friction sign, as Darcy–Weisbach does through ``abs(velocity) * velocity``.

    The two-phase model is chosen by ``fluid.gas_mass_fraction``, which is fixed in a trace: a
    liquid-only fluid never reaches Beggs–Brill. With free gas the gas mass flow is zero only
    at zero flow, which is the zero-flow case, so the structural test equals the former test of
    the gas mass flow. At zero flow every branch is still evaluated, Beggs–Brill's check on the
    liquid velocity fails there and ``where`` drops its error for the zero drops; the two drops
    are read by index because a failed result cannot be unpacked. The heat loss
    still receives a liquid flow of 1 kg/s at zero flow, because a direct call on arrays raises
    a failing check at once and this function is called that way.

    NOTE(refactor): DPDT's zero-flow branch suppresses gravity as well as friction.

    NOTE(refactor): the gas superficial velocity is ``m_g / rho_g / area``. The original
    ``gmf / rho_g / area`` left out the mass flow, so regime and holdup did not follow the flow;
    ``test_the_gas_superficial_velocity_is_the_gas_mass_flow_over_its_density_and_area`` holds a
    hand calculation. ``rho_g`` is the density of the free gas at this section's pressure and
    temperature, ideal-gas for a fluid with a ``gas_composition``.
    """
    stopped = flow == 0
    f = fluid.properties(p, T)
    mass = flow * f.density
    m_l, m_g = (1 - f.gmf) * mass, f.gmf * mass
    us_l = geometry.mean_velocity(m_l, f.rho_l, section.inner_diameter)
    rho_g = fluid.gas_density_at(p, T)
    us_g = geometry.mean_velocity(m_g, rho_g, section.inner_diameter)
    shape = (section.inner_diameter, section.roughness, section.length)
    if fluid.gas_mass_fraction == 0:
        friction, gravity = darcy_weisbach_dp(us_l, f.rho_l, section.inclination, f.mu_l, *shape)
    else:
        drops = beggs_brill_dp(
            ops.abs(us_g),
            ops.abs(us_l),
            rho_g,
            f.rho_l,
            section.inclination,
            f.mu_g,
            f.mu_l,
            f.sigma,
            *shape,
        )
        friction, gravity = drops[0], drops[1]
        friction = ops.where(us_l < 0, -friction, friction)
    delta_T = heat_transfer.pipe_temperature_change(
        T,
        heat_transfer_coefficient,
        geometry.lateral_area(section.inner_diameter, section.length),
        ops.where(stopped, 1.0, m_l),
        m_g,
        f.cp_l,
        f.cp_g,
        ambient_temperature,
    )
    return (
        ops.where(stopped, 0.0, friction),
        ops.where(stopped, 0.0, gravity),
        ops.where(stopped, 0.0, delta_T),
    )


@ops.physics
def corrosion_profile(
    path: geometry.PipePath,
    stream: Stream,
    fluid: Fluid,
    direction: Literal["up", "down"],
    heat_transfer_coefficient: float,
    ambient_temperature: float,
    chemistry: dict,
    model: Literal["NORSOK", "DLM", "DLD"] = "NORSOK",
) -> list[float]:
    """Return the CO2 corrosion rate [mm/year] of each section along the hydraulic profile.

    Each section takes the marched pressure and temperature of ``pipe_path_profile`` and the
    liquid flow ``q = |m| / rho`` at them, then the rate of ``corrosion.co2_corrosion_rate``.

    Parameters
    ----------
    path : PipePath
        Surface-to-bottom intervals [m, rad].
    stream : Stream
        Signed mass flow [kg/s], inlet pressure [Pa] and temperature [K].
    fluid : Fluid
        SI property model.
    direction : str
        Traversal direction, up or down [-].
    heat_transfer_coefficient, ambient_temperature : float
        Heat transfer coefficient [W/m2/K] and ambient temperature [K].
    chemistry : dict
        Keyword arguments for co2_corrosion_rate in its documented SI units.
    model : str
        NORSOK, DLM or DLD correlation [-].

    Returns
    -------
    list of float
        Wall penetration rates [mm/year] in traversal order.

    Notes
    -----
    Valid where ``co2_corrosion_rate`` is (NORSOK M-506: 5 to 150 degC, pH 3.5 to 6.5) and a
    nonzero flow. Reference: GEMINI WIMS composition of DPDT and the CO2 correlations (NORSOK
    M-506; de Waard and Lotz); see pipe_path_profile and corrosion.co2_corrosion_rate. The
    loop over sections reads the plain path geometry.
    """
    result = pipe_path_profile(
        path, stream, fluid, direction, heat_transfer_coefficient, ambient_temperature
    )
    _, sections = _traversal(path, direction)
    rates = []
    for section, p, T in zip(sections, result.section_pressure, result.section_temperature):
        f = fluid.properties(p, T)
        rates.append(
            corrosion.co2_corrosion_rate(
                model,
                temperature=T,
                pressure=p,
                water_flow_rate=fluid_physics.volume_flow(ops.abs(stream.m_dot), f.density),
                water_density=f.rho_l,
                water_viscosity=f.mu_l,
                diameter=section.inner_diameter,
                roughness=section.roughness,
                **chemistry,
            )
        )
    return rates
