"""Energy conversion through an efficiency, shared by pumps, compressors, motors and burners."""

from gemini import ops


@ops.physics
def total_power(powers):
    """Return the sum [W] of the powers a ``many`` port holds, or of a plant port's ends."""
    return sum(powers, start=0.0)


@ops.physics
def input_power(useful_power: float, efficiency: float) -> float:
    """Return the power a converter draws for a useful power, ``P_in = P_out / eta``.

    Parameters
    ----------
    useful_power : float
        Power delivered [W]: hydraulic power of a pump, shaft power of a motor, heat of a boiler.
    efficiency : float
        Conversion efficiency in (0, 1] [-].

    Returns
    -------
    float
        Power drawn [W]: shaft power, electricity or fuel.

    Notes
    -----
    Definition of the efficiency of a steady converter, valid at the operating point the efficiency
    belongs to. Reference: Moran and Shapiro, Fundamentals of Engineering Thermodynamics, section 2.
    """
    return useful_power / efficiency


@ops.physics
def output_power(input_power_value: float, efficiency: float) -> float:
    """Return the useful power [W] of an input power, ``P = F eta``.

    Parameters
    ----------
    input_power_value : float
        Power drawn [W], nonnegative.
    efficiency : float
        Useful share of it [-], positive.

    Returns
    -------
    float
        Useful power [W].

    Notes
    -----
    Definition of an efficiency, the inverse of ``input_power``.

    Validity: Any real inputs. No division occurs.
    Source: Definition of an efficiency; no published source is needed.
    """
    return input_power_value * efficiency


@ops.physics
def temperature_after(start, end, share):
    """Return the temperature [K] of a water that went ``share`` of the way from start to end.

    Parameters
    ----------
    start, end : float
        Temperatures [K] at the two ends of a duty.
    share : float
        Part of the duty done [-], in [0, 1].

    Returns
    -------
    float
        ``start + share (end - start)``: at a constant flow and heat capacity the temperature
        moves in proportion to the duty.

    Notes
    -----
    Validity: Constant flow and specific heat over the duty.
    Source: The steady heat balance of a stream; no published source is needed.
    """
    return start + share * (end - start)


@ops.physics
def circuit_flow(heat, specific_heat, temperature_difference):
    """Return the mass flow [kg/s] of a water circuit that carries a heat rate.

    Parameters
    ----------
    heat : float
        Heat rate [W], nonnegative.
    specific_heat : float
        Specific heat [J/kg/K], positive.
    temperature_difference : float
        Supply and return difference [K], positive.

    Returns
    -------
    float
        ``m = Q / (cp dT)``.

    Notes
    -----
    Reference: the steady hydronic heat balance, ASHRAE Handbook, HVAC Systems and Equipment
    (2020), chapter 13.

    Validity: Liquid circuits at constant specific heat.
    Source: As in the reference.
    """
    return heat / (specific_heat * temperature_difference)
