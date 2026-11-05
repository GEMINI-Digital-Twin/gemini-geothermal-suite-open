"""Electrical submersible pump using the retained TNO polynomial basis."""

import numpy as np

from gemini import ops, runtime
from gemini.errors import PhysicsError
from gemini.modules._utils.flow import require_forward
from gemini.modules.declarations import Control, Output, Parameter, Port
from gemini.modules.module import Module
from gemini.modules.results import Health
from gemini.ops import kernels
from gemini.physics import constants, diagnostics, energy, hydraulics, pumps
from gemini.streams.energy import Energy
from gemini.streams.fluid import Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase
from gemini.units.quantities import (
    Count,
    Dimensionless,
    Efficiency,
    Fraction,
    Frequency,
    Length,
    Power,
    Pressure,
    PressureDifference,
    Ratio,
    VolumeFlow,
)

HEALTH_KEYS = ("power", "head", "discharge_pressure")
"""Measured quantities whose relative drift from the prediction is scored."""

NO_MEASUREMENTS_OUTSIDE = "No performance measurements; outside operating window"


CURVE_SHAPE = (pumps.POLYNOMIAL_COEFFICIENT_COUNT,)
"""Shape of the head and power coefficient lists."""


def _float32():
    """Return whether the runtime precision is float32."""
    return runtime.get_precision() == "float32"


CURVE_STEPS = 200
"""The flows from zero to ``maximum_flow`` the curves are read at to name where they are negative."""


def _below_zero(flows, values):
    """Return ``[(first, last), ...]``: the runs of ``flows`` where ``values`` are below zero."""
    ranges, start = [], None
    for index, (flow, value) in enumerate(zip(flows, values, strict=True)):
        if value < 0 and start is None:
            start = flow
        if start is not None and (value >= 0 or index == len(flows) - 1):
            ranges.append((float(start), float(flows[index - 1] if value >= 0 else flow)))
            start = None
    return ranges


class ESP(Module):
    """Electrical submersible pump installed inside a production well."""

    repr_fields = ("stage_count", "setting_depth", "motor_efficiency", "best_efficiency_flow")
    operating_limits = (
        ("intake_pressure", "min", "minimum_intake_pressure"),
        ("gas_volume_fraction", "max", "maximum_gas_fraction"),
    )

    def __init__(self):
        """Declare ESP design data, ports and computed performance."""
        super().__init__()

        # Parameters
        self.stage_count = Parameter(Count, description="Number of stages of the pump")
        self.head_coefficients = Parameter(
            list[float],
            shape=CURVE_SHAPE,
            calibratable=True,
            description="Polynomial coefficients of the head curve of one stage",
        )
        self.power_coefficients = Parameter(
            list[float],
            shape=CURVE_SHAPE,
            calibratable=True,
            description="Polynomial coefficients of the power curve of one stage",
        )
        self.pump_type = Parameter(str, description="Catalogue name or label of the pump model")
        self.setting_depth = Parameter(Length, description="Depth at which the pump is set")
        self.motor_efficiency = Parameter(
            Efficiency,
            description="Efficiency of the motor: shaft power over electric power drawn",
        )
        self.minimum_flow = Parameter(
            VolumeFlow,
            ge=0,
            description=(
                "Lowest flow of the recommended operating window at the reference frequency"
            ),
        )
        self.maximum_flow = Parameter(
            VolumeFlow,
            gt=0,
            description=(
                "Highest flow of the recommended operating window at the reference frequency"
            ),
        )
        self.best_efficiency_flow = Parameter(
            VolumeFlow,
            gt=0,
            description="Flow at which the pump reaches its best efficiency",
        )
        self.correction_factors = Parameter(
            tuple[Dimensionless, PressureDifference],
            description=(
                "Calibration factors of the pressure rise: a multiplier and an added pressure "
                "difference"
            ),
        )
        self.tubing = Parameter(
            Length | None,
            default=None,
            gt=0,
            description=(
                "Inner diameter of the tubing the pump discharges into; empty when not given"
            ),
        )
        self.minimum_intake_pressure = Parameter(
            Pressure | None,
            default=None,
            description="Lowest pressure at the pump intake the equipment allows; empty: no limit",
        )
        self.maximum_gas_fraction = Parameter(
            Fraction | None,
            default=None,
            description="Largest free-gas volume fraction at the intake; empty: no limit",
        )
        self.drift_threshold = Parameter(
            Fraction,
            gt=0,
            le=1,
            description="Relative drift from the prediction at which the health alarm is raised",
        )

        # Inlets
        self.fluid_in = Port(
            Direction.IN,
            phase=Phase.LIQUID,
            fluid=Fluid.BRINE,
            level=Level.GEOTHERMAL,
            flow=Flow.IMPOSED,
        )
        self.power_in = Port(Direction.IN, energy=Energy.ELECTRICITY, flow=Flow.DRAWN)

        # Controls
        self.frequency = Control(Frequency, description="Operating frequency of the pump motor")

        # Outputs
        self.head = Output(
            PressureDifference, soft_sensor=True, description="Pressure rise given to the stream"
        )
        self.power = Output(
            Power, soft_sensor=True, description="Mechanical power on the pump shaft"
        )
        self.efficiency = Output(
            Dimensionless,
            soft_sensor=True,
            description="Hydraulic efficiency: fluid power over shaft power",
        )
        self.discharge_pressure = Output(
            Pressure, soft_sensor=True, description="Pressure at the pump discharge"
        )
        self.is_in_operating_window = Output(
            bool, description="True when the flow is inside the recommended operating window"
        )
        self.intake_pressure = Output(
            Pressure, soft_sensor=True, description="Pressure at the pump intake"
        )
        self.gas_volume_fraction = Output(
            Fraction,
            description="Free-gas volume over total volume of the stream at the pump intake",
        )
        self.best_efficiency_ratio = Output(
            Ratio, description="Flow as a share of the best-efficiency flow at the current speed"
        )

        # Outlets
        self.fluid_out = Port(
            Direction.OUT,
            phase=Phase.LIQUID,
            fluid=Fluid.BRINE,
            level=Level.GEOTHERMAL,
            flow=Flow.IMPOSED,
        )

    def _scalar_mode(self):
        """Return ``PLAIN`` under float32 precision, else ``WRAP``.

        NOTE(refactor): the legacy float32 arithmetic needs Python floats next to float32
        coefficients, and an ``np.float64`` scalar would promote them. This is the one module that
        honours float32 precision, so ``pumps.esp_efficiency`` keeps ``ops.truediv``: a
        plain ``/`` by a zero power would raise there.
        """
        return kernels.PLAIN if _float32() else kernels.WRAP

    def forward(self, inputs, inlets, state):
        """Raise the suction-stream pressure by the pump-curve head."""
        frequency = inputs["frequency"]

        # Outlets
        suction = inlets.fluid_in
        flow = suction.volumetric_flow()
        require_forward(self.path, "suction volume flow", flow, "m3/s")
        head = self.head_function(flow, frequency)
        power = self.power_function(flow, frequency)
        scale = pumps.speed_ratio(frequency, constants.ESP_REFERENCE_FREQUENCY)
        gas = self._gas_volume_fraction(suction)
        self._check_inside_curve(flow, head, power, scale, suction.p, gas)

        slope, offset = self.correction_factors
        head = ops.where(frequency > 0, hydraulics.affine_correction(head, slope, offset), head)
        discharge = suction._with_si(p=suction.p + head)
        power_in = energy.input_power(power, self.motor_efficiency)

        # Outputs
        outputs = dict(
            head=head,
            power=power,
            efficiency=pumps.esp_efficiency(flow, head, power),
            discharge_pressure=discharge.p,
            is_in_operating_window=pumps.is_in_operating_window(
                flow, self.minimum_flow, self.maximum_flow, scale
            ),
            intake_pressure=suction.p,
            gas_volume_fraction=gas,
            best_efficiency_ratio=pumps.best_efficiency_ratio(
                flow, scale, self.best_efficiency_flow
            ),
        )

        outlets = dict(fluid_out=discharge, power_in=power_in)
        return outputs, outlets

    @staticmethod
    def _gas_volume_fraction(suction):
        """Return the free-gas volume fraction of the suction stream at its own pressure."""
        fluid = suction.fluid
        return pumps.intake_gas_volume_fraction(
            fluid.properties(suction.p, suction.T).rho_l,
            fluid.gas_density_at(suction.p, suction.T),
            fluid.gas_mass_fraction,
        )

    def _check_inside_curve(self, flow, head, power, scale, intake, gas):
        """Fail the row where the polynomial curves are used outside the range they are valid for.

        The polynomials are fitted on a finite flow range and extrapolate outside it, to a power
        of any size or to a negative head or power. The range is the pump's own: the flow at most
        ``maximum_flow`` scaled by the speed ratio (affinity law) with
        ``pumps.CURVE_FLOW_TOLERANCE`` on top, the head and the power at least zero. The row
        fails with ``out_of_range`` naming the path, the flow, the head, the power, the largest flow
        and the intake pressure and gas volume fraction that inflated the flow.
        ``minimum_flow`` is the recommended range, not this one: a flow below it only raises the
        health alarm.
        """
        largest = pumps.curve_flow_limit(self.maximum_flow, scale)
        ops.check(
            ops.logical_and(ops.logical_and(flow <= largest, head >= 0), power >= 0),
            PhysicsError,
            "{path}: flow = {flow} m3/s gives head = {head} Pa and power = {power} W; expected "
            "flow at most {largest} m3/s (maximum_flow at this speed) and head and power at "
            "least 0, the range the curves are valid for; intake pressure = {intake} Pa and gas "
            "volume fraction = {gas}{curves}. maximum_flow is the range of the pump curves, not "
            "the case's flow band: the suction flow is above the doublet's flow by the expansion "
            "of the brine and its free gas",
            code="out_of_range",
            path=self.path,
            curves=self._negative_curves(),
            flow=flow,
            head=head,
            power=power,
            largest=largest,
            intake=intake,
            gas=gas,
        )

    def _negative_curves(self):
        """Return where the head or power curve is below zero, from 0 to ``maximum_flow``, as text.

        Named in the ``out_of_range`` message, so the row says where the curves are valid, not one
        flow (geomind request 35). The sign of the polynomials does not depend on the speed, so
        they are read at the reference frequency on ``CURVE_STEPS`` flows, once per set of
        curves; a pump whose curves cannot be read (unset, or in a trace) gives no text.
        """
        try:
            key = (
                float(self.maximum_flow),
                int(self.stage_count),
                tuple(np.ravel(self.head_coefficients).tolist()),
                tuple(np.ravel(self.power_coefficients).tolist()),
            )
        except Exception:  # an unset or traced parameter: the message stays as it is
            return ""
        cached = self.__dict__.get("_negative_curves_cache")
        if cached is not None and cached[0] == key:
            return cached[1]
        largest = key[0]
        flows = np.linspace(0.0, largest, CURVE_STEPS + 1)
        frequency = float(constants.ESP_REFERENCE_FREQUENCY)
        parts = []
        for name, curve in (("head", self.head_function), ("power", self.power_function)):
            values = np.asarray(curve(flows, frequency), dtype=float)
            ranges = _below_zero(flows, values)
            if ranges:
                said = ", ".join(f"{low:.4g} to {high:.4g}" for low, high in ranges)
                parts.append(f"negative {name} at flows {said} m3/s")
        text = f"; the curves give {' and '.join(parts)} (0 to {largest:.4g} m3/s)" if parts else ""
        self.__dict__["_negative_curves_cache"] = (key, text)
        return text

    def head_function(self, flow: float, frequency: float) -> float:
        """Return pump head [Pa] for flow [m3/s] and frequency [Hz]."""
        return pumps.head(
            flow, frequency, self.stage_count, self._coefficients(self.head_coefficients)
        )

    def power_function(self, flow: float, frequency: float) -> float:
        """Return shaft power [W] for flow [m3/s] and frequency [Hz]."""
        return pumps.power(
            flow, frequency, self.stage_count, self._coefficients(self.power_coefficients)
        )

    def health(self, result, measured):
        """Score the worst available relative drift and the operating window.

        Runs on scalars and on arrays over a chunk: the worst drift key and the message are
        selected with ``ops.where`` over complete strings, the first key winning a tie.
        """
        predicted = result.outputs
        window = predicted.is_in_operating_window
        drifts = {
            key: diagnostics.relative_drift(measured[key], getattr(predicted, key))
            for key in HEALTH_KEYS
            if key in measured
        }
        worst, message = self._worst_drift(drifts, window)
        return Health(
            score=diagnostics.remaining_margin(worst),
            alarm=ops.logical_or(worst > self.drift_threshold, ops.logical_not(window)),
            message=message,
            metrics=drifts,
        )

    @staticmethod
    def _worst_drift(drifts, window):
        """Return the largest absolute drift and the message naming it and the window."""
        if not drifts:
            return 0, ops.where(window, "No performance measurements", NO_MEASUREMENTS_OUTSIDE)
        worst, message = None, None
        for key, drift in drifts.items():
            text = ops.where(
                window, f"Worst drift: {key}", f"Worst drift: {key}; outside operating window"
            )
            magnitude = ops.abs(drift)
            if worst is None:
                worst, message = magnitude, text
                continue
            larger = magnitude > worst
            worst, message = ops.where(larger, magnitude, worst), ops.where(larger, text, message)
        return worst, message

    @staticmethod
    def _coefficients(values):
        """Return curve coefficients in the selected runtime precision.

        NOTE(refactor): old monitoring uses NumPy float32 arithmetic when selected globally. The
        ``np.asarray`` is a precision cast of the stored coefficients, not maths.
        """
        if _float32():
            return np.asarray(values, dtype=np.float32)
        return values
