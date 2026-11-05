"""Fits of model parameters to measurements: pump curves, reservoir pressure, exchanger UA.

Modules hold the parameters a fit produces; the fit itself lives here, on plain NumPy arrays or
through the physics functions.
"""

import numpy as np

from gemini import units as physics_units
from gemini.errors import PhysicsError, ValidationError
from gemini.modules.pumps import ESP
from gemini.physics import constants, heat_transfer
from gemini.units.shapes import OutputUnits, value

PUMP_CURVE_POINTS = 50
"""Number of flows on the head curve of ``pump_curve``, from zero to twice the maximum flow."""

CURVE_COEFFICIENTS = 6
"""Number of ascending polynomial coefficients of an ESP curve, so at least so many flows."""


def fit_head_coefficients(flows, frequencies, heads, stage_count, units=None):
    """Fit the six ascending US-basis ESP head coefficients from SI observations.

    Parameters
    ----------
    flows, frequencies, heads : array_like
        Volume flows [m3/s], frequencies [Hz] and heads [Pa], at least six matching observations
        with six distinct flows.
    stage_count : int
        Number of pump stages, positive.
    units : dict, optional
        A map from quantity to unit, as on every ``gm.analysis`` return; the coefficients are on
        their own basis, so the map is only checked.

    Returns
    -------
    dict
        A value: the six coefficients of ``physics.pumps.head``, ascending, on their own mixed US
        basis (ft of head per stage at 60 Hz with flow in bbl/day), so the unit is ``"-"``.

    Notes
    -----
    Least-squares polynomial of degree five through the observations reduced to one stage at the
    reference frequency by the affinity law ``H ~ f^2``.
    """
    OutputUnits(units)
    q, f, h = (np.asarray(item, dtype=float) for item in (flows, frequencies, heads))
    if q.shape != f.shape or q.shape != h.shape or q.ndim != 1 or len(q) < CURVE_COEFFICIENTS:
        raise PhysicsError(
            "ESP: at least six matching observations required", code="too_little_data"
        )
    if stage_count <= 0 or np.any(f <= 0) or np.any(q < 0) or not np.isfinite([q, f, h]).all():
        raise PhysicsError(
            "ESP: fitting requires finite positive stages and frequencies", code="too_little_data"
        )
    x = physics_units.m3s_to_bbl_per_day(q)
    y = physics_units.pa_to_ft_head(h) / (
        stage_count * (f / constants.ESP_REFERENCE_FREQUENCY) ** 2
    )
    if len(np.unique(x)) < CURVE_COEFFICIENTS:
        raise PhysicsError("ESP: six distinct flow values are required", code="too_little_data")
    degree = CURVE_COEFFICIENTS - 1
    return value(np.polynomial.Polynomial.fit(x, y, degree).convert().coef.tolist(), "-")


def fit_head_correction(measured, theoretical, units=None):
    """Fit the affine correction ``theoretical = slope * measured + offset`` [-, Pa].

    Parameters
    ----------
    measured, theoretical : array_like
        Measured and theoretical heads [Pa], at least two finite pairs with distinct measurements.
    units : dict, optional
        A map from quantity to unit for the returned values.

    Returns
    -------
    dict
        ``{slope, offset}``: the least-squares slope [-] and offset [Pa], each a value.
    """
    output = OutputUnits(units)
    x, y = (np.asarray(item, dtype=float) for item in (measured, theoretical))
    if x.shape != y.shape or len(x) < 2 or not np.isfinite([x, y]).all() or np.var(x) == 0:
        raise PhysicsError(
            "ESP: two or more finite, distinct measurements required", code="too_little_data"
        )
    slope = np.sum((x - x.mean()) * (y - y.mean())) / np.sum((x - x.mean()) ** 2)
    offset = float(y.mean() - slope * x.mean())
    return {
        "slope": value(float(slope), "-"),
        "offset": output.value(offset, "Pa", "pressure_difference"),
    }


def estimate_reservoir_pressure(flows, bottomhole_pressures, units=None):
    """Fit the reservoir pressure [Pa] and the R-squared [-] from flow observations.

    Parameters
    ----------
    flows, bottomhole_pressures : array_like
        Volume flows [m3/s] and bottomhole pressures [Pa], at least two matching finite samples
        with nonzero flows.
    units : dict, optional
        A map from quantity to unit for the returned values.

    Returns
    -------
    dict
        ``{pressure, r_squared}``, each a value: the slope of the least-squares line ``p_bh / Q =
        p_res (1 / Q) + b``, which is the reservoir pressure of a linear inflow relation, and the
        R-squared of the line.
    """
    output = OutputUnits(units)
    q, p = (np.asarray(item, dtype=float) for item in (flows, bottomhole_pressures))
    if (
        q.shape != p.shape
        or q.ndim != 1
        or len(q) < 2
        or np.any(q == 0)
        or not np.isfinite([q, p]).all()
    ):
        raise PhysicsError(
            "Reservoir pressure estimation needs at least two matching finite, nonzero samples",
            code="too_little_data",
        )
    x, y = 1 / q, p / q
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        raise PhysicsError(
            "Reservoir pressure regression requires variation", code="too_little_data"
        )
    coefficients = np.polyfit(x, y, 1)
    residual = y - np.poly1d(coefficients)(x)
    r_squared = 1 - np.sum(residual**2) / np.sum((y - np.mean(y)) ** 2)
    return {
        "pressure": output.value(float(coefficients[0]), "Pa", "pressure"),
        "r_squared": value(float(r_squared), "-"),
    }


def estimate_conductance(
    hot_in_T,
    hot_out_T,
    cold_in_T,
    cold_out_T,
    m_dot_hot,
    m_dot_cold,
    *,
    cp_hot,
    cp_cold,
    arrangement,
    units=None,
):
    """Return the apparent UA of an exchanger as a value in W/K, from temperatures and mass flows.

    Temperatures are in K, mass flows in kg/s and heat capacities in J/kg/K. Raises
    ``PhysicsError`` when the measurements cannot determine UA: a stopped stream, hot and
    cold duties that disagree by more than 5 %, or no positive LMTD; see
    ``heat_transfer.apparent_conductance``. ``units`` is a map from quantity to unit.
    """
    output = OutputUnits(units)
    if arrangement not in {"counterflow", "parallel"}:
        raise ValidationError(
            f"HeatExchanger: unknown arrangement {arrangement!r}; expected counterflow or parallel",
            code="unknown_name",
        )
    apparent, code, hot_duty, cold_duty, delta = heat_transfer.apparent_conductance(
        arrangement,
        hot_in_T,
        hot_out_T,
        cold_in_T,
        cold_out_T,
        m_dot_hot,
        m_dot_cold,
        cp_hot,
        cp_cold,
    )
    if code == heat_transfer.NONPOSITIVE_INPUT:
        raise PhysicsError(
            "HeatExchanger: mass flows and heat capacities must be positive", code="too_little_data"
        )
    if code == heat_transfer.DISAGREEING_DUTIES:
        raise PhysicsError(
            f"HeatExchanger: hot/cold duties must agree within 5%; got {hot_duty} W and "
            f"{cold_duty} W",
            code="too_little_data",
        )
    if code == heat_transfer.NO_LMTD:
        raise PhysicsError(
            f"HeatExchanger: positive LMTD required; got {delta} K", code="too_little_data"
        )
    return output.value(apparent, "W/K", "thermal_conductance")


def _points(measured):
    """Return the measured head points in SI as a list of ``{flow, frequency, head}``."""
    return [
        {
            "flow": float(
                physics_units.value_in_si(point["flow"], "m3/s", "measured.flow", "volume_flow")
            ),
            "frequency": float(
                physics_units.value_in_si(
                    point["frequency"], "Hz", "measured.frequency", "frequency"
                )
            ),
            "head": float(
                physics_units.value_in_si(
                    point["head"], "Pa", "measured.head", "pressure_difference"
                )
            ),
        }
        for point in measured or ()
    ]


def _correction(points, units):
    """Return the affine correction of theoretical head on measured head, or why it has none."""
    if not points:
        return value(None, "-", "no measured points")
    try:
        return fit_head_correction(
            [point["head"] for point in points],
            [point["theoretical_head"] for point in points],
            units,
        )
    except PhysicsError as error:
        return value(None, "-", str(error))


def _measured_point(point, output):
    """Return one measured point with every number as a value."""
    return {
        "flow": output.value(point["flow"], "m3/s", "volume_flow"),
        "frequency": output.value(point["frequency"], "Hz", "frequency"),
        "head": output.value(point["head"], "Pa", "pressure_difference"),
        "theoretical_head": output.value(point["theoretical_head"], "Pa", "pressure_difference"),
    }


def _head_curve(module, frequency):
    """Return plotting points (flow [m3/s], head [Pa]) of an ESP at a frequency [Hz].

    The flows run from zero to twice the speed-scaled maximum flow; the head is evaluated at the
    flow referred to the reference speed.
    """
    if frequency <= 0:
        raise ValidationError(
            f"{module.path}: positive frequency required; got frequency = {frequency} Hz",
            code="invalid_design",
        )
    scale = frequency / constants.ESP_REFERENCE_FREQUENCY
    return [
        (float(flow), module.head_function(flow / scale, frequency))
        for flow in np.linspace(0, 2 * module.maximum_flow * scale, PUMP_CURVE_POINTS)
    ]


def pump_curve(plant, pump, measured=None, units=None):
    """Return an ESP's head curve at the reference frequency and the fit of measured points.

    The curve is the pump's polynomial head curve (``_head_curve``) at the reference
    frequency of 60 Hz, for flows from zero to twice the maximum flow. Head is a pressure
    difference in Pa; the head of a fluid column in metres is ``head / (density * g)`` with the
    density of the pumped fluid.

    Parameters
    ----------
    plant : Module
        A plant with parameter values.
    pump : str
        Dotted path of an ``ESP``, for example ``"doublet.esp"``.
    measured : list of dict, optional
        Points ``{flow, frequency, head}`` in m3/s, Hz and Pa (SI numbers or ``Quantity`` values).
    units : dict, optional
        A map from quantity to unit for the returned values.

    Returns
    -------
    dict
        Plain JSON ``{pump, frequency, curve, measured, correction}``, every number a value.
        ``curve`` is ``{flow, head}``. Each measured point gains ``theoretical_head`` [Pa], the
        pump's head at its flow and frequency. ``correction`` is ``{slope, offset}`` of the
        least-squares line ``theoretical_head = slope * head + offset`` (offset in Pa), or a value
        ``None`` with a ``reason`` when fewer than two distinct measured heads are given. This is
        the retained ``fit_head_correction``; a diagnosis: the ESP's
        ``correction_factors`` map the curve head to the pressure rise, the inverse direction.
    """
    output = OutputUnits(units)
    module = plant.get_submodule(pump)
    if not isinstance(module, ESP):
        raise ValidationError(
            f"pump_curve: pump = {pump!r}; expected the path of an ESP", path=pump
        )
    points = _points(measured)
    for point in points:
        point["theoretical_head"] = float(module.head_function(point["flow"], point["frequency"]))
    reference = constants.ESP_REFERENCE_FREQUENCY.value
    flows, heads = zip(*_head_curve(module, reference))
    return {
        "pump": pump,
        "frequency": output.value(reference, "Hz", "frequency"),
        "curve": {
            "flow": output.value(flows, "m3/s", "volume_flow"),
            "head": output.value(heads, "Pa", "pressure_difference"),
        },
        "measured": [_measured_point(point, output) for point in points],
        "correction": _correction(points, units),
    }
