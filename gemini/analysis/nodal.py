"""Nodal analysis of geothermal wells: the flow or pressure at which well and reservoir agree.

A plant normally commands the production rate (``ProductionReservoir.production_rate``) and
reads the wellhead pressure that results. Nodal analysis inverts this: for a given wellhead
pressure it finds the rate at which the reservoir inflow and the well lift agree, and on the
injection side the rate or the wellhead pressure at which the injection well delivers the
bottomhole pressure the receiving aquifer needs. The functions are ported from the upstream
GEMINI simulator (``gemini_simulator.nodal_solver``), which solves the same balances with
``scipy.optimize.brentq``.

Every trial evaluates the plant's own modules without a running call. A plant states the same
balances with ``Plant.constrain``, as ``NodalDoublet`` does. Each solve needs a
bracket whose two ends lie inside the well model's domain and give residuals of opposite sign:
very small rates can cool a stream below 0 K through the explicit heat loss and very large rates
can drive the traversed pressure below zero, and a trial there raises ``PhysicsError``
naming the trial value.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import numpy as np

from gemini import units as physics_units
from gemini._utils.jsonable import to_plain
from gemini._utils.strings import split_path
from gemini.errors import GeminiError, ValidationError
from gemini.errors.base import check_on_error
from gemini.modules.pumps import ESP
from gemini.modules.subsurface import InjectionReservoir, ProductionReservoir
from gemini.modules.wells import InjectionWell, ProductionWell
from gemini.plants._utils.targets import evaluate, root
from gemini.streams.flows import Stream
from gemini.units.shapes import OutputUnits

CURVE_POINTS = 21
"""Number of rates on the IPR and VLP curves of ``nodal``, from the low to the high bracket end."""
WELLHEAD_PRESSURES = (101325.0, 1e8)
"""The bracket [Pa] of an injection wellhead: the lowest is one atmosphere, the highest 1000 bar."""
NO_PUMP = "the column of brine delivers what the aquifer needs: no pump, a choke holds the well"


@dataclass(frozen=True)
class _Chain:
    """The production chain of a well: reservoir, lower well, optional ESP and upper well."""

    reservoir: Any
    lower: Any
    esp: Any
    upper: Any


@dataclass(frozen=True)
class _Injection:
    """The injection chain of a well: the well and the aquifer it feeds."""

    well: Any
    sink: Any


def _injection_chain(plant, well, module, inside):
    """Return the injection chain at ``well``, or ``None`` when it has no part of one.

    A path of the well or of the aquifer finds the other in the same parent, which is how to reach
    the injection side of a doublet, whose own path is its production chain.
    """
    alone = isinstance(module, (InjectionWell, InjectionReservoir))
    scope = list(plant.get_submodule(split_path(well)[0]).modules()) if alone else inside
    wells = [item for item in scope if isinstance(item, InjectionWell)]
    sinks = [item for item in scope if isinstance(item, InjectionReservoir)]
    if not wells and not sinks:
        return None
    if len(wells) != 1 or len(sinks) != 1:
        raise ValidationError(
            f"nodal: well = {well!r}; {len(wells)} injection wells, {len(sinks)} aquifers; "
            "expected one of each",
            path=well,
            code="invalid_design",
        )
    return _Injection(wells[0], sinks[0])


def _chain(plant, well):
    """Return the production or injection chain at the plant path ``well``."""
    module = plant.get_submodule(well)
    inside = list(module.modules())
    reservoirs = [item for item in inside if isinstance(item, ProductionReservoir)]
    if not reservoirs:
        injection = _injection_chain(plant, well, module, inside)
        if injection is not None:
            return injection
        raise ValidationError(
            f"nodal: well = {well!r}; expected a path that holds a ProductionReservoir, or an "
            "injection well and its aquifer",
            path=well,
        )
    wells = {item.segment: item for item in inside if isinstance(item, ProductionWell)}
    esps = [item for item in inside if isinstance(item, ESP)]
    if esps and {"below_esp", "above_esp"} <= wells.keys():
        return _Chain(reservoirs[0], wells["below_esp"], esps[0], wells["above_esp"])
    if not esps and "full" in wells:
        return _Chain(reservoirs[0], wells["full"], None, None)
    raise ValidationError(
        f"nodal: well = {well!r}; segments = {sorted(wells)}, ESPs = {len(esps)}; expected one "
        "ProductionWell 'full', or an ESP with the segments 'below_esp' and 'above_esp'",
        code="invalid_design",
    )


def _required(conditions, name):
    if name not in conditions:
        raise ValidationError(
            f"nodal: conditions.{name} is missing; expected it", path=name, code="missing_value"
        )
    return conditions[name]


def _case_inputs(chain, conditions):
    """Return the SI wellhead pressure [Pa], rate bracket [kg/s] and ESP frequency [Hz]."""
    pressure = physics_units.value_in_si(
        _required(conditions, "wellhead_pressure"), "Pa", "conditions.wellhead_pressure", "pressure"
    )
    low, high = (
        physics_units.value_in_si(value, "kg/s", "conditions.rates", "mass_flow")
        for value in _required(conditions, "rates")
    )
    frequency = None
    if chain.esp is not None:
        frequency = physics_units.value_in_si(
            _required(conditions, "frequency"), "Hz", "conditions.frequency", "frequency"
        )
    return float(pressure), (float(low), float(high)), frequency


def _lift(chain, rate):
    """Return the wellhead pressure [Pa] that the well lifts the inflow of ``rate`` to."""
    inflow = chain.reservoir.sandface_stream(rate)
    stream = chain.lower._trial(bottom_in=inflow).outlets.wellhead_out
    if chain.esp is not None:
        stream = chain.esp._trial(fluid_in=stream).outlets.fluid_out
        stream = chain.upper._trial(bottom_in=stream).outlets.wellhead_out
    return stream.p


def _curve(rates, pressures, output):
    """Return one curve of 21 points, each list a value."""
    return {
        "rate": output.value(rates, "kg/s", "mass_flow"),
        "pressure": output.value(pressures, "Pa", "pressure"),
    }


def _curves(chain, pressure, rates, output):
    """Return the IPR, the VLP and the operating point for a rate bracket."""
    low, high = rates
    sampled = np.linspace(low, high, CURVE_POINTS)
    inflow = [chain.reservoir.sandface_stream(rate).p for rate in sampled]
    lift = [_lift(chain, rate) for rate in sampled]
    rate = solve_production_rate(
        chain.reservoir, chain.lower, pressure, rates, esp=chain.esp, riser=chain.upper
    )
    point = {
        "rate": output.value(rate, "kg/s", "mass_flow"),
        "wellhead_pressure": output.value(pressure, "Pa", "pressure"),
        "sandface_pressure": output.value(
            chain.reservoir.sandface_stream(rate).p, "Pa", "pressure"
        ),
    }
    return _curve(sampled, inflow, output), _curve(sampled, lift, output), point


def _in_si(conditions, name, unit, quantity):
    """Return the condition ``name`` as a float in SI."""
    return float(physics_units.value_in_si(conditions[name], unit, f"conditions.{name}", quantity))


def _injection_inputs(conditions):
    """Return the SI temperature [K], rate bracket [kg/s] and what the case gives of a point."""
    _required(conditions, "temperature")
    temperature = _in_si(conditions, "temperature", "K", "temperature")
    low, high = (
        physics_units.value_in_si(value, "kg/s", "conditions.rates", "mass_flow")
        for value in _required(conditions, "rates")
    )
    if "rate" not in conditions and "wellhead_pressure" not in conditions:
        raise ValidationError(
            "nodal: conditions has no rate and no wellhead_pressure; expected one of them",
            path="wellhead_pressure",
            code="missing_value",
        )
    return temperature, (float(low), float(high))


def _needed_pressure(chain, temperature, rate):
    """Return the wellhead pressure [Pa] that injects ``rate``, or ``None`` with no pump."""
    stream = Stream._si(m_dot=rate, T=temperature, p=WELLHEAD_PRESSURES[0], fluid=chain.well.fluid)
    return solve_injection_pressure(chain.well, chain.sink, stream, WELLHEAD_PRESSURES)


def _injected_rate(chain, temperature, pressure, rates):
    """Return the rate [kg/s] the wellhead pressure [Pa] pushes into the aquifer."""
    stream = Stream._si(m_dot=rates[0], T=temperature, p=pressure, fluid=chain.well.fluid)
    return solve_injection_rate(chain.well, chain.sink, stream, rates)


def _aquifer_pressure(chain, temperature, rate):
    """Return the sandface pressure [Pa] the aquifer needs to take ``rate``."""
    stream = Stream._si(m_dot=rate, T=temperature, p=WELLHEAD_PRESSURES[0], fluid=chain.sink.fluid)
    return chain.sink.required_pressure(stream)


def _injection_point(chain, conditions, temperature, rates, output):
    """Return the operating point: the rate and pressure of the case, the other one solved."""
    if "rate" in conditions:
        rate = _in_si(conditions, "rate", "kg/s", "mass_flow")
        pressure = _needed_pressure(chain, temperature, rate)
    else:
        pressure = _in_si(conditions, "wellhead_pressure", "Pa", "pressure")
        rate = _injected_rate(chain, temperature, pressure, rates)
    return {
        "rate": output.value(rate, "kg/s", "mass_flow"),
        "wellhead_pressure": output.value(
            pressure, "Pa", "pressure", None if pressure is not None else NO_PUMP
        ),
        "sandface_pressure": output.value(
            _aquifer_pressure(chain, temperature, rate), "Pa", "pressure"
        ),
    }


def _injection_curves(chain, conditions, output):
    """Return the aquifer's curve, the well's curve and the operating point of a case."""
    temperature, rates = _injection_inputs(conditions)
    sampled = np.linspace(*rates, CURVE_POINTS)
    aquifer = [_aquifer_pressure(chain, temperature, rate) for rate in sampled]
    needed = [_needed_pressure(chain, temperature, rate) for rate in sampled]
    well = [np.nan if pressure is None else pressure for pressure in needed]
    point = _injection_point(chain, conditions, temperature, rates, output)
    return _curve(sampled, aquifer, output), _curve(sampled, well, output), point


def _production_curves(chain, conditions, output):
    """Return the IPR, the VLP and the operating point of a case of a production well."""
    pressure, rates, frequency = _case_inputs(chain, conditions)
    if chain.esp is not None:
        chain.esp._assign_si("frequency", frequency)
    return _curves(chain, pressure, rates, output)


def _case(chain, conditions, on_error, output):
    """Return the curves and the operating point of one set of conditions."""
    case = {
        "conditions": conditions,
        "ipr": None,
        "vlp": None,
        "operating_point": None,
        "error": None,
    }
    try:
        curves = _injection_curves if isinstance(chain, _Injection) else _production_curves
        case["ipr"], case["vlp"], case["operating_point"] = curves(chain, conditions, output)
    except GeminiError as error:
        if on_error == "raise":
            raise
        case["error"] = error.to_dict()
    return case


def nodal(plant, well, conditions, on_error="raise", units=None):
    """Return the IPR and VLP curves and the operating point of a production or injection well.

    The IPR (inflow performance) is the sandface pressure the reservoir delivers at each rate.
    The VLP (vertical lift performance) is the wellhead pressure the well, the ESP and the riser
    deliver from that inflow at each rate: the node is the wellhead, and the operating point is
    where the VLP falls to the wellhead pressure the surface plant holds. The solve is the one
    of ``solve_production_rate``. The plant is not changed: the ESP frequency
    of a case is set on a copy.

    An injection well has the same shape. ``ipr`` is the sandface pressure the aquifer needs at
    each rate and ``vlp`` the wellhead pressure that delivers it down the well, ``
    solve_injection_pressure``; the operating point is the pressure a case's rate needs, or the
    rate a case's pressure pushes in. A rate the column of brine injects alone needs no pump: its
    point on ``vlp`` is ``None``, and in ``operating_point`` a value ``None`` with a ``reason``.

    Parameters
    ----------
    plant : Module
        A plant with parameter values.
    well : str
        Dotted path of the module that holds the whole chain, for example ``"doublet"``: one
        ``ProductionReservoir`` and either one full ``ProductionWell`` or an ``ESP`` with the
        ``below_esp`` and ``above_esp`` segments. For injection, the path of an
        ``InjectionWell`` or of its ``InjectionReservoir``, ``"doublet.injector"``, or of what
        holds one of each and no production chain.
    conditions : dict or list of dict
        One case, or several for a what-if. Each has ``wellhead_pressure`` [Pa], ``rates``, the
        ``[low, high]`` bracket [kg/s] of the curves and of the solve (a trial outside the well
        model's domain fails the case), and ``frequency`` [Hz] when the chain has an ESP. Numbers
        are SI, or a ``Quantity``. An injection case has ``rates``,
        ``temperature`` [K], the temperature at the wellhead, and ``rate`` or
        ``wellhead_pressure``, which says what to solve for.
    on_error : {"raise", "record"}, optional
        A case that fails raises; ``"record"`` puts its problem in ``error`` and runs the others.
    units : dict, optional
        A map from quantity to unit for the returned values, such as ``{"pressure": "bar"}``.

    Returns
    -------
    dict
        Plain JSON ``{well, cases}``. Each case holds ``conditions`` as given, ``ipr`` and ``vlp``
        as ``{rate, pressure}``, each a value with 21 points from the low to the high rate,
        ``operating_point`` as ``{rate, wellhead_pressure, sandface_pressure}``, each a value, and
        ``error``. Under ``on_error="record"`` a case whose bracket leaves the well model's domain
        or has no sign change has ``None`` curves and operating point and its problem in ``error``.
    """
    check_on_error(on_error)
    output = OutputUnits(units)
    chain_plant = deepcopy(plant)
    chain = _chain(chain_plant, well)
    cases = [conditions] if isinstance(conditions, dict) else list(conditions)
    return to_plain(
        {
            "well": well,
            "cases": [_case(chain, case, on_error, output) for case in cases],
        }
    )


def solve_production_rate(reservoir, well, wellhead_pressure, rates, esp=None, riser=None):
    """Return the production rate [kg/s] that delivers the wellhead pressure [Pa].

    Parameters
    ----------
    reservoir : ProductionReservoir
        Aquifer with its linear inflow performance.
    well : ProductionWell
        The full well, or with an ESP the segment below it (``segment="below_esp"``).
    wellhead_pressure : float
        Wellhead pressure [Pa] the surface plant holds.
    rates : tuple of float
        ``(low, high)`` mass flows [kg/s] bracketing the solution.
    esp, riser : ESP and ProductionWell, optional
        Pump and segment above it (``segment="above_esp"``), given together. The ESP runs at
        its persisted ``frequency``.

    Returns
    -------
    float
        The rate at which the sandface stream, lifted through well, ESP and riser, arrives at
        ``wellhead_pressure``. The wellhead pressure falls with rate (more drawdown and
        friction, less ESP head), so the root is unique within a valid bracket.

    Notes
    -----
    Upstream GEMINI walks the well downward from the wellhead and compares bottomhole
    pressures; this solve walks upward from the sandface as the plant does, so both sides of
    the balance use the same traversal as an ordinary plant call.
    """
    if (esp is None) != (riser is None):
        raise ValidationError(
            f"solve_production_rate: esp = {esp!r}, riser = {riser!r}; expected both or neither",
            code="invalid_design",
        )

    def residual(rate):
        stream = well._trial(bottom_in=reservoir.sandface_stream(rate)).outlets.wellhead_out
        if esp is not None:
            stream = esp._trial(fluid_in=stream).outlets.fluid_out
            stream = riser._trial(bottom_in=stream).outlets.wellhead_out
        return stream.p - wellhead_pressure

    return root("solve_production_rate", "rate", residual, rates, "kg/s")


def solve_injection_rate(well, sink, wellhead, rates):
    """Return the injection rate [kg/s] a wellhead stream's pressure pushes into the aquifer.

    Parameters
    ----------
    well : InjectionWell
        Injection well from wellhead to bottom.
    sink : InjectionReservoir
        Receiving aquifer with its linear injectivity.
    wellhead : Stream
        Wellhead temperature, pressure and fluid; its mass flow is replaced by trial rates.
    rates : tuple of float
        ``(low, high)`` mass flows [kg/s] bracketing the solution.

    Returns
    -------
    float
        The rate at which the well's bottom pressure equals ``sink.required_pressure``.
    """

    def residual(rate):
        return _injection_residual(well, sink, wellhead._with_si(m_dot=rate))

    return root("solve_injection_rate", "rate", residual, rates, "kg/s")


def solve_injection_pressure(well, sink, wellhead, pressures):
    """Return the wellhead pressure [Pa] that injects a stream, or ``None`` if none is needed.

    Parameters
    ----------
    well : InjectionWell
        Injection well from wellhead to bottom.
    sink : InjectionReservoir
        Receiving aquifer with its linear injectivity.
    wellhead : Stream
        Injected mass flow, temperature and fluid; its pressure is replaced by trial pressures.
    pressures : tuple of float
        ``(low, high)`` wellhead pressures [Pa]. Pass the pressure available without an
        injection pump, normally the pump suction, as ``low``.

    Returns
    -------
    float or None
        The wellhead pressure an injection pump must deliver. ``None`` means no pump is
        needed: already at ``low`` the column of brine delivers at least the bottomhole
        pressure the aquifer needs (common for deep injectors, which a choke throttles
        instead). Treat ``None`` as zero pump head and power, for example by commanding the
        pump to its suction pressure. Upstream GEMINI returned the bracket's lower end here.
    """

    def residual(pressure):
        return _injection_residual(well, sink, wellhead._with_si(p=pressure))

    low = pressures[0]
    if evaluate("solve_injection_pressure", "pressure", residual, low, "Pa") >= 0:
        return None
    return root("solve_injection_pressure", "pressure", residual, pressures, "Pa")


def _injection_residual(well, sink, wellhead):
    """Return the injection well's bottom pressure minus the aquifer's required pressure [Pa]."""
    bottom = well._trial(wellhead_in=wellhead).outlets.bottom_out
    return bottom.p - sink.required_pressure(bottom)
