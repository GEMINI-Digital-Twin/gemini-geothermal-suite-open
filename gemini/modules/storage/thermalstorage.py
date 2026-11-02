"""Fully mixed hot or chilled water storage tank with a charge and a discharge circuit."""

from typing import Literal

from gemini import ops
from gemini.modules._utils.equipment import Equipment
from gemini.modules._utils.flow import require_forward
from gemini.modules.declarations import Inlet, Outlet, Output, Parameter, State
from gemini.modules.module import Module
from gemini.physics import heat_transfer
from gemini.streams.flows import Stream
from gemini.units.quantities import (
    Energy,
    Fraction,
    HeatAccumulation,
    Power,
    Temperature,
    ThermalConductance,
    Volume,
)


class ThermalStorage(Equipment, Module):
    """Fully mixed (lumped) hot or chilled water tank with charge and discharge circuits.

    The tank content is the fluid of the charging inlet (``module.fluid`` when stated) at one
    uniform temperature, the state ``temperature``.
    Each circuit exchanges heat with the tank through a constant effectiveness ``e``
    (``charge_effectiveness``, ``discharge_effectiveness``); ``e = 1`` is a direct
    connection, where the circuit leaves at the tank temperature. With ``C_i = m_dot_i * cp_i``
    the heat flows into the tank are ``Q_i = e_i * C_i * (T_i_in - T)`` and the circuit leaves
    at ``T_i_out = T_i_in - e_i * (T_i_in - T)``; the ambient exchange is
    ``Q_amb = UA * (T - T_ambient)``. The tank balance (Duffie and Beckman 2013, *Solar
    Engineering of Thermal Processes*, 4th ed., section 8.3, fully mixed storage) is

        rho * cp * V * dT/dt = Q_charge + Q_discharge - Q_amb.

    ``update`` integrates it with its exact exponential solution over ``dt`` for inlets
    held constant during the step: with ``b = e_c C_c + e_d C_d + UA`` and the equilibrium
    ``T_eq = (e_c C_c T_c + e_d C_d T_d + UA T_ambient) / b``,
    ``T(dt) = T_eq + (T(0) - T_eq) * exp(-b dt / (rho cp V))``; it is unconditionally stable.
    Outlets and outputs use the start-of-step temperature.

    ``service`` sets the sign of the reported energies: a ``"hot"`` tank stores heat, so
    ``stored_energy = rho cp V (T - T_ref)``, ``charge_duty = Q_charge`` and ``discharge_duty =
    -Q_discharge``; a ``"chilled"`` tank stores cold, so every sign flips and ``stored_energy =
    rho cp V (T_ref - T)``. A negative duty means the circuit works against the service (for
    example charge water colder than a hot tank). ``loss_out`` is ``Q_amb``, negative for a chilled
    tank in a warm room.

    ``heat_accumulation`` is the rate of increase of the tank's sensible heat
    ``rho cp V dT/dt`` at the start of the step; ``energy_balance`` counts it as the signed
    storage outflow, so the tank is first-law closed. Each circuit keeps its mass flow, pressure
    and fluid (constant tank volume, no pressure loss), so ``mass_balance`` closes.

    Assumptions and validity: single-phase liquid below boiling, no thermal stratification
    (a stratified tank delivers hotter discharge water than this model), constant fluid
    properties at the start-of-step temperature, constant effectiveness independent of flow,
    and inlet temperatures constant over a step (use steps short against the tank time
    constant ``rho cp V / b`` when the inlets vary).

    The tank temperature is a state, so the module is traced as the body of a scan.
    """

    equipment_kind = "thermal_storage"

    def __init__(self):
        """Declare tank design data, circuits, the tank temperature and its energies."""
        super().__init__()

        # Parameters
        self.service = Parameter(
            Literal["hot", "chilled"], description="Service of the tank: hot water or chilled water"
        )
        self.volume = Parameter(Volume, gt=0, description="Volume of the tank")
        self.heat_loss_conductance = Parameter(
            ThermalConductance,
            description="Conductance of the heat loss from the tank to the surroundings",
        )
        self.reference_temperature = Parameter(
            Temperature, description="Reference temperature of the stored energy and the heat loss"
        )
        self.charge_effectiveness = Parameter(
            Fraction,
            description=(
                "Effectiveness of the charging circuit heat exchange; one is a direct connection"
            ),
        )
        self.discharge_effectiveness = Parameter(
            Fraction,
            description=(
                "Effectiveness of the discharging circuit heat exchange; one is a direct connection"
            ),
        )

        # Inlets
        self.charge_in = Inlet(Stream, kind="hot_water")
        self.discharge_in = Inlet(Stream, kind="hot_water")
        self.air_in = Inlet(Stream, kind="air")

        # States
        self.temperature = State(Temperature, description="Uniform temperature of the tank content")

        # Outputs
        self.tank_temperature = Output(
            Temperature, description="Uniform temperature of the tank content"
        )
        self.stored_energy = Output(
            Energy, description="Heat held in the tank relative to its reference temperature"
        )
        self.charge_duty = Output(
            Power, description="Heat the charging circuit gives to the service of the tank"
        )
        self.discharge_duty = Output(
            Power, description="Heat the discharging circuit takes from the service of the tank"
        )
        self.heat_accumulation = Output(
            HeatAccumulation,
            description="Rate at which the store gains heat (negative when it loses)",
        )

        # Outlets
        self.charge_out = Outlet(Stream, kind="hot_water")
        self.discharge_out = Outlet(Stream, kind="hot_water")
        self.loss_out = Outlet(Power, kind="heat")

    def forward(self, inputs, inlets, state):
        """Return both circuits after exchanging heat with the start-of-step tank."""
        temperature = state["temperature"]

        # Outlets
        charge_in, discharge_in = inlets.charge_in, inlets.discharge_in
        charge_g = self._conductance(charge_in, self.charge_effectiveness)
        discharge_g = self._conductance(discharge_in, self.discharge_effectiveness)
        charge_T = self._outlet_temperature(
            charge_in, charge_g, self.charge_effectiveness, temperature
        )
        fluid_out_T = self._outlet_temperature(
            discharge_in, discharge_g, self.discharge_effectiveness, temperature
        )
        charge_out = charge_in._with_si(T=charge_T)
        discharge_out = discharge_in._with_si(T=fluid_out_T)

        loss_out = heat_transfer.heat_rate(
            self.heat_loss_conductance, temperature - inlets.air_in.T
        )

        # Outputs
        charge = heat_transfer.heat_rate(charge_g, charge_in.T - temperature)
        discharge = heat_transfer.heat_rate(discharge_g, discharge_in.T - temperature)
        stored_energy, charge_duty, discharge_duty = heat_transfer.tank_service_report(
            self.service == "hot",
            self._capacity(charge_in, temperature),
            temperature,
            self.reference_temperature,
            charge,
            discharge,
        )
        outputs = dict(
            tank_temperature=temperature,
            stored_energy=stored_energy,
            charge_duty=charge_duty,
            discharge_duty=discharge_duty,
            heat_accumulation=charge + discharge - loss_out,
        )

        outlets = dict(charge_out=charge_out, discharge_out=discharge_out, loss_out=loss_out)
        return outputs, outlets

    def cost_size(self):
        """Return the size that the cost of the tank scales with: volume."""
        return self.volume

    def update(self, inputs, inlets, outlets, state, dt):
        """Return the tank temperature after exchanging heat over ``dt``."""
        charge_in, discharge_in = inlets.charge_in, inlets.discharge_in
        temperature = state["temperature"]
        relaxed = heat_transfer.tank_relaxation(
            temperature,
            self._capacity(charge_in, temperature),
            dt,
            self._conductance(charge_in, self.charge_effectiveness),
            charge_in.T,
            self._conductance(discharge_in, self.discharge_effectiveness),
            discharge_in.T,
            self.heat_loss_conductance,
            inlets.air_in.T,
        )
        return {"temperature": relaxed}

    def _capacity(self, charge_in, temperature):
        """Return the tank heat capacity rho * cp * V [J/K] of the tank fluid."""
        properties = self._fluid_of(charge_in).properties(charge_in.p, temperature)
        return heat_transfer.tank_capacity(properties.liquid_volumetric_heat_capacity, self.volume)

    def _conductance(self, stream, effectiveness):
        """Return the circuit conductance e * m_dot * cp [W/K]; reject reverse flow."""
        require_forward(self.path, "circuit m_dot", stream.m_dot)
        return heat_transfer.circuit_conductance(effectiveness, stream.heat_capacity_rate())

    def _outlet_temperature(self, stream, conductance, effectiveness, temperature):
        """Return a circuit's outlet temperature [K]; a stopped circuit keeps its inlet value."""
        return ops.where(
            conductance == 0,
            stream.T,
            heat_transfer.effectiveness_outlet_temperature(stream.T, effectiveness, temperature),
        )
