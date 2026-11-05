"""Adiabatic junction mixing two streams of the same fluid."""

from gemini import ops
from gemini.errors import ValidationError
from gemini.modules._utils.flow import require_forward
from gemini.modules.declarations import Output, Port
from gemini.modules.module import Module
from gemini.physics import heat_transfer
from gemini.streams.fluid import Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase
from gemini.units.quantities import PressureDifference


class Mixer(Module):
    """Adiabatic tee mixing two streams of one fluid into a single outlet.

    Steady first law without heat or work: ``T_mix = (m_1 cp_1 T_1 + m_2 cp_2 T_2) / (m_1 cp_1 +
    m_2 cp_2)`` and ``m_mix = m_1 + m_2``, so mass and sensible energy close to rounding. A
    stopped junction (both flows zero) carries no energy and takes the mean inlet temperature.

    The outlet pressure is the lower inlet pressure. A junction has one pressure, so in the
    real network the higher-pressure branch is throttled down to it by its own resistance (a
    valve, the tee loss); a sequential model that does not solve the network cannot raise the
    lower stream, and taking the lower pressure never creates pressure energy. The discarded
    difference is reported as ``pressure_imbalance``: a large value means the upstream branches
    are not hydraulically balanced and the model under-predicts a throttling loss upstream.

    Streams of different fluids raise ``ValidationError`` (a mixture property model would be
    needed); reverse flow in either inlet raises ``PhysicsError``.
    """

    def __init__(self):
        """Declare both inlets, the mixed outlet and the mixing diagnostics."""
        super().__init__()

        # Inlets
        self.branch1_in = Port(
            Direction.IN,
            fluid=Fluid.ANY,
            phase=Phase.LIQUID,
            level=Level.ANY,
            generic="T",
            flow=Flow.IMPOSED,
        )
        self.branch2_in = Port(
            Direction.IN,
            fluid=Fluid.ANY,
            phase=Phase.LIQUID,
            level=Level.ANY,
            generic="T",
            flow=Flow.IMPOSED,
        )

        # Outputs
        self.pressure_imbalance = Output(
            PressureDifference, description="Difference between the two inlet pressures"
        )

        # Outlets
        self.fluid_out = Port(
            Direction.OUT,
            fluid=Fluid.ANY,
            phase=Phase.LIQUID,
            level=Level.ANY,
            generic="T",
            flow=Flow.IMPOSED,
        )

    def forward(self, inputs, inlets, state):
        """Combine both inlet streams at the lower inlet pressure."""

        # Outlets
        branch1_in = inlets.branch1_in
        branch2_in = inlets.branch2_in
        self._check(branch1_in, branch2_in)
        fluid_out = branch1_in._with_si(
            m_dot=branch1_in.m_dot + branch2_in.m_dot,
            T=heat_transfer.mixed_temperature(
                branch1_in.heat_capacity_rate(),
                branch1_in.T,
                branch2_in.heat_capacity_rate(),
                branch2_in.T,
            ),
            p=ops.minimum(branch1_in.p, branch2_in.p),
        )

        # Outputs
        outputs = dict(pressure_imbalance=ops.abs(branch1_in.p - branch2_in.p))

        outlets = dict(fluid_out=fluid_out)
        return outputs, outlets

    def _loop_start(self, inputs, port, entering):
        """Start a loop at the water that joins from outside: the blend before the loop adds any."""
        return entering[0].T if entering else None

    def _check(self, branch1_in, branch2_in):
        """Reject reverse flow and streams of different fluids."""
        require_forward(self.path, "branch1_in.m_dot", branch1_in.m_dot)
        require_forward(self.path, "branch2_in.m_dot", branch2_in.m_dot)
        if branch1_in.fluid != branch2_in.fluid:
            raise ValidationError(
                f"{self.path}: branch1_in.fluid = {branch1_in.fluid!r}, branch2_in.fluid = "
                f"{branch2_in.fluid!r}; expected the same fluid",
                code="invalid_design",
            )
