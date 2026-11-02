"""Discrete PID controller with output limits and clamping anti-windup."""

from typing import Literal

from gemini import ops
from gemini.errors import ValidationError
from gemini.modules.control import _physics
from gemini.modules.declarations import Boundary, Control, Output, Parameter, State
from gemini.modules.module import Module
from gemini.units.quantities import Dimensionless, Duration


class PIDController(Module):
    """Discrete PID controller with output limits and clamping anti-windup; no fluid ports.

    The error is ``e = setpoint - measurement`` for ``direction="reverse"`` (the command rises
    when the measurement falls, as for a heating valve) and ``e = measurement - setpoint`` for
    ``direction="direct"`` (as for a cooling valve). With the gain ``K``, the integral time
    ``Ti`` and the derivative time ``Td`` the command of step k is the ideal (ISA) form,
    discretised as in Astrom and Hagglund 2006, *Advanced PID Control*, chapter 3:

        u_k = clamp(K * e_k + I_k + D_k, minimum_output, maximum_output)
        D_k = K * Td * (e_k - e_(k-1)) / h_(k-1)
        I_(k+1) = I_k + K * h_k / Ti * e_k

    The states are ``integral`` I (in command units), ``previous_error`` e_(k-1) and
    ``previous_step`` h_(k-1) [s]. The step length h_k is known only when the states advance,
    so the command uses start-of-step states only: the integral is the explicit (forward
    rectangular) sum of the errors before this step, a one-step lag of the integral action, and
    the derivative is the backward difference of the last two errors over the previous step
    length, exact for a uniform clock. Before the first step (``previous_step`` is zero, no step
    yet) the derivative is zero. The derivative acts on the error, so a setpoint change kicks it
    once; it is not filtered, so noisy measurements need an empty ``derivative_time`` (the
    default) or a filtered measurement.

    Anti-windup is clamping (conditional integration): the integral does not change over a step
    whose unclamped command already exceeds a limit while the error drives it further out.
    ``integral_time=None`` gives P or PD control. The three states have no default: the case
    states them in ``initial_state`` (a controller that starts fresh has all three at zero).

    A parent composite calls the controller in ``forward`` with ``measurement=`` (and
    optionally ``setpoint=``) and uses ``result.outputs.command``; the controller is stateful, so
    call it once per step.
    """

    def __init__(self):
        """Declare the tuning, the limits, the controller memory and the command."""
        super().__init__()

        # Parameters
        self.proportional_gain = Parameter(
            Dimensionless, gt=0, description="Proportional gain K of the controller"
        )
        self.integral_time = Parameter(
            Duration | None,
            default=None,
            gt=0,
            description="Integral time Ti of the controller; empty disables the integral action",
        )
        self.derivative_time = Parameter(
            Duration | None,
            default=None,
            description="Derivative time Td of the controller; empty disables the derivative part",
        )
        self.minimum_output = Parameter(Dimensionless, description="Lower limit of the command")
        self.maximum_output = Parameter(Dimensionless, description="Upper limit of the command")
        self.direction = Parameter(
            Literal["direct", "reverse"],
            description=(
                "Sense of the control action: reverse raises the command when the measurement "
                "falls, direct when it rises"
            ),
        )

        # Controls
        self.setpoint = Control(Dimensionless, description="Target value of the measurement")

        # Boundaries
        self.measurement = Boundary(
            Dimensionless, description="Measured value the controller regulates"
        )

        # States
        self.integral = State(
            Dimensionless, description="Integral term I of the command at the start of the step"
        )
        self.previous_error = State(
            Dimensionless, description="Control error of the previous step; unused while no step"
        )
        self.previous_step = State(
            Duration, ge=0, description="Length of the previous step; zero when there is none yet"
        )

        # Outputs
        self.error = Output(
            Dimensionless,
            description=(
                "Control error: the distance of the measurement from the setpoint in the acting "
                "direction"
            ),
        )
        self.command = Output(
            Dimensionless, description="Command the controller outputs, within its limits"
        )
        self.is_saturated = Output(bool, description="True when the command is held at a limit")

    def forward(self, inputs, inlets, state):
        """Move no fluid; the command is an output."""
        unclamped = self._unclamped_command(inputs, state)
        command = ops.minimum(self.maximum_output, ops.maximum(self.minimum_output, unclamped))

        # Outputs
        outputs = dict(
            error=self._error(inputs),
            command=command,
            is_saturated=command != unclamped,
        )

        outlets = dict()
        return outputs, outlets

    def update(self, inputs, inlets, outlets, state, dt):
        """Return the integral, the error and the length of this step for the next one."""
        error = self._error(inputs)
        unclamped = self._unclamped_command(inputs, state)
        increment = 0.0
        if self.integral_time is not None:
            increment = _physics.pid_integral_increment(
                self.proportional_gain, dt, self.integral_time, error
            )
        increment = _physics.anti_windup_increment(
            increment, unclamped, self.minimum_output, self.maximum_output
        )
        return {
            "integral": state["integral"] + increment,
            "previous_error": error,
            "previous_step": dt,
        }

    def _error(self, inputs):
        """Return the control error in the sense of ``direction``."""
        return _physics.pid_error(
            inputs["setpoint"], inputs["measurement"], self.direction == "reverse"
        )

    def _unclamped_command(self, inputs, state):
        """Return K * e + I + D from the start-of-step states, before the output limits."""
        ops.check(
            self.minimum_output < self.maximum_output,
            ValidationError,
            "{path}: minimum_output = {minimum_output}, maximum_output = {maximum_output}; "
            "expected minimum_output < maximum_output",
            path=self.path,
            minimum_output=self.minimum_output,
            maximum_output=self.maximum_output,
            code="invalid_design",
        )
        error = self._error(inputs)
        derivative = 0.0
        if self.derivative_time is not None:
            previous_step = state["previous_step"]
            started = previous_step > 0
            derivative = ops.where(
                started,
                _physics.pid_derivative(
                    self.proportional_gain,
                    self.derivative_time,
                    error - state["previous_error"],
                    ops.where(started, previous_step, 1.0),
                ),
                0.0,
            )
        return _physics.pid_command(self.proportional_gain, error, state["integral"], derivative)
