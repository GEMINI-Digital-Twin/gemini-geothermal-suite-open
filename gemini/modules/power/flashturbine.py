"""Single-flash condensing steam turbine with Baumann wet-expansion losses."""

from gemini import ops
from gemini.errors import PhysicsError
from gemini.modules._utils.flow import require_forward
from gemini.modules.declarations import Output, Parameter, Port
from gemini.modules.module import Module
from gemini.physics import steam
from gemini.streams.energy import Energy
from gemini.streams.fluid import WATER, Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase
from gemini.units.quantities import Efficiency, Fraction, Power, Pressure, Ratio


class FlashTurbine(Module):
    """Condensing steam turbine and generator fed with dry saturated steam from a separator.

    The inlet is dry saturated steam (``Fluid`` kind ``steam``, as ``Separator.gas_out`` emits) at
    the inlet pressure; the inlet temperature is not used because the pressure fixes the
    saturated state. The steam expands to ``condenser_pressure`` with the Baumann rule:
    eta = eta_dry (1 - a (1 - x_out) / 2) for the mean exhaust moisture (see
    ``steam.baumann_expansion``). The generator converts ``gross_power`` (shaft power)
    with ``generator_efficiency``. The condenser condenses the exhaust to saturated liquid at
    the condenser pressure, which leaves through ``outlet`` as water.

    ``loss_out`` is the condenser duty plus the generator loss, so the module is closed in
    IF97 enthalpies: m h_g(p_in) = electricity_generated + heat_loss + m h_f(p_cond).

    NOTE(refactor): ``energy_balance`` audits sensible enthalpy ``m_dot * cp_l * T`` and
    cannot represent the latent heat of the steam, so its residual is not valid for this phase
    change; the unit tests check closure with the steam enthalpies instead.

    Design values: ``isentropic_efficiency`` and ``baumann_factor`` are set by the plant. DiPippo
    (R. (2016), Geothermal Power Plants, 4th ed., section 5.5) assumes a dry efficiency of 0.85
    for geothermal steam turbines and the classical Baumann rule, a factor of 1.
    Assumptions: no non-condensable gases, steam ejector or gland losses; condenser at a fixed
    pressure. Valid for inlet pressures up to 16.529 MPa above a condenser pressure of at
    least 611.213 Pa, with a wet exhaust.
    """

    def __init__(self):
        """Declare turbine and generator design data, ports and computed performance."""
        super().__init__()

        # Parameters
        self.isentropic_efficiency = Parameter(
            Efficiency,
            description="Dry-steam isentropic efficiency of the turbine",
        )
        self.baumann_factor = Parameter(
            Ratio,
            description="Baumann coefficient: efficiency loss per unit of exhaust moisture",
        )
        self.condenser_pressure = Parameter(Pressure, gt=0, description="Pressure in the condenser")
        self.generator_efficiency = Parameter(
            Efficiency, description="Efficiency of the generator: electric power over shaft power"
        )

        # Inlets
        self.fluid_in = Port(
            Direction.IN,
            phase=Phase.GAS,
            fluid=Fluid.STEAM,
            level=Level.GEOTHERMAL,
            flow=Flow.IMPOSED,
        )

        # Outputs
        self.gross_power = Output(
            Power, description="Electric power generated before parasitic loads"
        )
        self.condenser_duty = Output(Power, description="Heat rejected in the condenser")
        self.exhaust_quality = Output(
            Fraction, description="Steam quality (vapour share) at the turbine exhaust"
        )

        # Outlets
        self.fluid_out = Port(
            Direction.OUT,
            phase=Phase.TWO_PHASE,
            fluid=Fluid.STEAM,
            level=Level.GEOTHERMAL,
            flow=Flow.IMPOSED,
        )
        self.power_out = Port(Direction.OUT, energy=Energy.ELECTRICITY, flow=Flow.IMPOSED)
        self.loss_out = Port(Direction.OUT, energy=Energy.HEAT, flow=Flow.IMPOSED)

    def forward(self, inputs, inlets, state):
        """Expand the steam and return the condensate at the condenser saturation state."""

        # Outlets
        inlet = inlets.fluid_in
        condenser = steam.saturation_properties(self.condenser_pressure)

        outlet = inlet._with_si(T=condenser.temperature, p=self.condenser_pressure, fluid=WATER)
        expansion = self._expansion(inlet)
        balance = self._balance(inlet, expansion)

        # Outputs
        outputs = dict(
            gross_power=balance.gross_power,
            condenser_duty=balance.condenser_duty,
            exhaust_quality=expansion.outlet_quality,
        )

        outlets = dict(
            fluid_out=outlet, power_out=balance.electricity_generated, loss_out=balance.heat_loss
        )
        return outputs, outlets

    def _balance(self, inlet, expansion):
        """Return the enthalpy balance of the turbine, generator and condenser."""
        return steam.turbine_balance(
            inlet.m_dot,
            expansion.inlet_enthalpy,
            expansion.outlet_enthalpy,
            steam.saturation_properties(self.condenser_pressure).liquid_enthalpy,
            self.generator_efficiency,
        )

    def _expansion(self, inlet):
        """Return the Baumann expansion of the inlet steam to the condenser pressure.

        Raises ``PhysicsError`` outside the model domain; ``forward`` calls it to reject
        such an inlet before it emits the condensate.
        """
        require_forward(self.path, "fluid_in.m_dot", inlet.m_dot)
        if inlet.fluid.kind != "steam":
            raise PhysicsError(
                f"{self.path}: inlet.fluid.kind = {inlet.fluid.kind!r}; expected 'steam'"
            )
        ops.check(
            inlet.p > self.condenser_pressure,
            PhysicsError,
            "{path}: fluid_in.p = {p} Pa; expected above the condenser pressure "
            "{condenser_pressure} Pa",
            path=self.path,
            p=inlet.p,
            condenser_pressure=self.condenser_pressure,
        )
        return steam.baumann_expansion(
            inlet.p, self.condenser_pressure, self.isentropic_efficiency, self.baumann_factor
        )
