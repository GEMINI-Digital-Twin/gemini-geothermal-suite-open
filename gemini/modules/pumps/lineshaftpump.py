"""Line-shaft downhole pump on the retained TNO ESP polynomial basis."""

from gemini import ops
from gemini.errors import PhysicsError
from gemini.modules._utils.flow import require_forward
from gemini.modules.declarations import Control, Inlet, Outlet, Output, Parameter
from gemini.modules.module import Module
from gemini.physics import constants, energy, pumps
from gemini.streams.flows import Stream
from gemini.units.quantities import (
    Count,
    Dimensionless,
    Efficiency,
    Frequency,
    Length,
    LinearPower,
    Power,
    PressureDifference,
)


class LineShaftPump(Module):
    """Downhole multistage pump driven by a surface motor through a line shaft.

    The pump stages use the same TNO R11363 polynomial basis as ``ESP``
    (``gemini.physics.pumps``): ``head_coefficients`` and ``power_coefficients`` give ft of head and
    bhp per stage at 60 Hz with the flow in bbl/day, scaled by ``stage_count`` and by the square
    (head) and cube (power) of ``frequency / 60 Hz``. The line shaft from the surface motor to
    the pump at ``setting_depth`` adds the mechanical friction loss
    ``P_friction = shaft_friction_loss * setting_depth * frequency / 60 Hz``: the friction loss
    per shaft length is given at the 60 Hz catalogue speed and grows in proportion to speed
    (constant bearing friction torque), the form of the vertical-turbine-pump manufacturer
    tables of line-shaft friction (horsepower per 100 ft of shaft at a given speed; see
    ANSI/HI 2.3, Rotodynamic Vertical Pumps for Design and Application). Electricity is
    ``(P_pump + P_friction) / motor_efficiency``.

    NOTE(refactor): like ``ESP`` the pump is isothermal: the empirical polynomials do not
    guarantee ``P_pump >= Q H`` (the retained ESP efficiency can exceed one), so no pump or
    shaft loss is allocated to the fluid and no motor loss is reported as ``loss_out``. The
    electricity is listed as unresolved pump power by ``energy_balance``. Thrust-bearing
    losses, shaft stretch and the column pipe friction (part of the well model) are not
    modelled. Reverse flow, a negative head or a negative pump power (running off the
    polynomial curve) raise ``PhysicsError``; at zero flow the pump runs at shutoff.
    """

    repr_fields = ("stage_count", "setting_depth", "motor_efficiency")

    def __init__(self):
        """Declare line-shaft pump design data, ports and computed performance."""
        super().__init__()

        # Parameters
        self.stage_count = Parameter(Count, description="Number of stages of the pump")
        self.head_coefficients = Parameter(
            list[float],
            shape=(pumps.POLYNOMIAL_COEFFICIENT_COUNT,),
            calibratable=True,
            description="Polynomial coefficients of the head curve of one stage",
        )
        self.power_coefficients = Parameter(
            list[float],
            shape=(pumps.POLYNOMIAL_COEFFICIENT_COUNT,),
            calibratable=True,
            description="Polynomial coefficients of the power curve of one stage",
        )
        self.setting_depth = Parameter(
            Length, description="Depth at which the pump is set, the length of the line shaft"
        )
        self.shaft_friction_loss = Parameter(
            LinearPower, ge=0, description="Friction power lost per unit of shaft length at 60 Hz"
        )
        self.motor_efficiency = Parameter(
            Efficiency,
            description="Efficiency of the electric motor: shaft power over electric power drawn",
        )

        # Inlets
        self.fluid_in = Inlet(Stream, kind="brine")
        self.power_in = Inlet(Power, kind="electricity")

        # Controls
        self.frequency = Control(Frequency, description="Operating frequency of the pump motor")

        # Outputs
        self.head = Output(
            PressureDifference,
            soft_sensor=True,
            description="Pressure rise given to the stream by the pump stages",
        )
        self.pump_power = Output(
            Power, description="Mechanical power given to the fluid by the pump stages"
        )
        self.shaft_friction_power = Output(
            Power, description="Power lost to friction in the line shaft"
        )
        self.shaft_power = Output(
            Power, soft_sensor=True, description="Mechanical power on the pump shaft"
        )
        self.efficiency = Output(
            Dimensionless, description="Pump efficiency: hydraulic power over shaft power"
        )

        # Outlets
        self.fluid_out = Outlet(Stream, kind="brine")

    def forward(self, inputs, inlets, state):
        """Raise the suction pressure by the pump-curve head."""
        frequency = inputs["frequency"]

        # Outlets
        suction = inlets.fluid_in
        flow = suction.volumetric_flow()
        head = self._head(flow, frequency)

        discharge = suction._with_si(p=suction.p + head)
        pump_power, friction = self._powers(flow, frequency)
        shaft_power = pump_power + friction
        power_in = energy.input_power(shaft_power, self.motor_efficiency)

        # Outputs
        rise = discharge.p - suction.p
        outputs = dict(
            head=rise,
            pump_power=pump_power,
            shaft_friction_power=friction,
            shaft_power=shaft_power,
            efficiency=pumps.pump_efficiency(flow, rise, pump_power),
        )

        outlets = dict(fluid_out=discharge, power_in=power_in)
        return outputs, outlets

    def _powers(self, flow, frequency):
        """Return the pump power and the shaft friction power [W] at a volume flow [m3/s]."""
        pump_power = pumps.power(flow, frequency, self.stage_count, self.power_coefficients)
        ops.check(
            pump_power >= 0,
            PhysicsError,
            "{path}: pump power = {pump_power} W at flow = {flow} m3/s; expected >= 0 "
            "(pump off its power curve)",
            path=self.path,
            pump_power=pump_power,
            flow=flow,
        )
        speed = pumps.speed_ratio(frequency, constants.ESP_REFERENCE_FREQUENCY)
        friction = pumps.line_shaft_friction_power(
            self.shaft_friction_loss, self.setting_depth, speed
        )
        return pump_power, friction

    def _head(self, flow, frequency):
        """Return the pump-curve pressure rise [Pa] at a suction volume flow [m3/s]."""
        require_forward(self.path, "suction volume flow", flow, "m3/s")
        head = pumps.head(flow, frequency, self.stage_count, self.head_coefficients)
        ops.check(
            head >= 0,
            PhysicsError,
            "{path}: head = {head} Pa at flow = {flow} m3/s; expected >= 0 (pump off "
            "its head curve)",
            path=self.path,
            head=head,
            flow=flow,
        )
        return head
