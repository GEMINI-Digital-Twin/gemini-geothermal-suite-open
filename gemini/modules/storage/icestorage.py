"""Lumped ice-on-coil or encapsulated ice store on one glycol circuit."""

from gemini import ops
from gemini.errors import ValidationError
from gemini.modules._utils.equipment import Equipment
from gemini.modules._utils.flow import require_forward
from gemini.modules.declarations import Output, Parameter, Port, State
from gemini.modules.module import Module
from gemini.physics import heat_transfer
from gemini.streams.fluid import Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase
from gemini.units.quantities import (
    Energy,
    Fraction,
    HeatAccumulation,
    Mass,
    SpecificEnthalpy,
    SpecificHeat,
    Temperature,
    ThermalConductance,
    Volume,
)


class IceStorage(Equipment, Module):
    """Lumped ice store for cooling: a glycol coil freezes or melts a fixed mass of water.

    The store holds ``water_mass`` M of water at one uniform temperature T, of which the
    state ``ice_fraction`` x is frozen. The state ``temperature`` is the store temperature: the
    freezing temperature T_f while partly frozen (0 < x < 1), above it only as all liquid
    (x = 0, sensible heat with ``water_specific_heat``) and below it only as all ice (x = 1,
    sensible heat with ``ice_specific_heat``). Other combinations raise ``ValidationError``.

    The coil is a heat exchanger against a store at uniform temperature (capacity ratio zero),
    so with ``C = m_dot * cp`` of the glycol its effectiveness is ``e = 1 - exp(-UA / C)``
    (Incropera et al., *Fundamentals of Heat and Mass Transfer*, effectiveness-NTU method). The
    heat flow from the glycol into the store is ``duty = e * C * (T_in - T)`` and the glycol
    leaves at ``fluid_out_T = T_in - e * (T_in - T)``. A glycol inlet below T_f charges the store
    (negative duty: water freezes, then the ice subcools), one above T_f discharges it (positive
    duty: the store cools the glycol, the ice melts, then the water warms).

    ``update`` integrates the enthalpy balance exactly and piecewise over ``dt`` for an
    inlet held constant during the step: in the latent segment T = T_f and the duty is constant,
    so x changes linearly by ``-duty * t / (M * L)``; in a sensible segment T relaxes towards
    ``T_in`` with the time constant ``M * c / (e * C)``. A step moves to the next segment when
    the store becomes full (x = 1) or empty (x = 0), or reaches T_f, so it can cross at most
    three segments. Outlets and outputs use the start-of-step state.

    ``stored_cold = M * L * x`` is the latent cold available. The store is perfectly insulated
    and the coil carries the glycol in a closed circuit, so ``mass_balance`` closes.
    ``heat_accumulation`` equals ``duty``, the rate of increase of the store's internal energy
    at the start of the step (negative while charging with cold); ``energy_balance`` counts it as
    the signed storage outflow, so the store is first-law closed.

    Reference values: ``latent_heat`` 333.55 kJ/kg is the conventional latent heat of fusion of
    ice at 0 degC and 101.325 kPa; IAPWS R10-06 (Feistel and Wagner 2006, *A new equation of
    state for H2O ice Ih*) gives 333.44 kJ/kg at the triple point, 0.03 % lower.
    ``freezing_temperature`` 273.15 K is the normal melting point. ``water_specific_heat``
    4219.9 J/kg/K is saturated liquid water at 0.01 degC (IAPWS-95, Wagner and Pruss 2002) and
    ``ice_specific_heat`` 2096.8 J/kg/K is ice Ih at the triple point (IAPWS R10-06).

    Simplifications and validity: one lumped store temperature, constant coil UA (in a real
    ice-on-coil store UA falls as the ice layer thickens and depends on the glycol flow regime;
    ASHRAE Handbook, HVAC Applications, chapter Thermal Storage), constant properties, no
    supercooling or nucleation delay, no ambient heat gain and no pressure loss. Suitable for
    hourly or 15-minute dispatch studies of the store's state of charge, not for coil design.

    The ice fraction and the temperature are states, so the module is traced as the body of a
    scan. The segment loop of ``heat_transfer.ice_advance`` runs its fixed ``MAX_SEGMENTS`` passes,
    a finished pass keeping its state. The coil follows ``heat_transfer.ambient_effectiveness`` and
    ``circuit_conductance``; the segments are ``heat_transfer.ice_step``.

    The store is equipment of kind ``ice_storage``, priced only when the economics of a case
    gives ``capex.ice_storage`` (``PRICED_WHEN_GIVEN``): per m3 of ``volume`` or per energy of
    ``energy_capacity``, the unit of the factor tells which. Without that factor it adds no cost.
    """

    equipment_kind = "ice_storage"

    def __init__(self):
        """Declare store design data, the glycol circuit, the phase state and its energies."""
        super().__init__()

        # Parameters
        self.water_mass = Parameter(Mass, gt=0, description="Mass of water in the store")
        self.thermal_conductance = Parameter(
            ThermalConductance, gt=0, description="Conductance of the glycol coil against the store"
        )
        self.latent_heat = Parameter(
            SpecificEnthalpy,
            default=heat_transfer.DEFAULT_ICE_LATENT_HEAT,
            gt=0,
            description="Latent heat of the phase change",
        )
        self.freezing_temperature = Parameter(
            Temperature,
            default=heat_transfer.DEFAULT_FREEZING_TEMPERATURE,
            description="Temperature at which the water freezes",
        )
        self.water_specific_heat = Parameter(
            SpecificHeat,
            default=heat_transfer.DEFAULT_WATER_HEAT_CAPACITY,
            description="Specific heat capacity of liquid water",
        )
        self.ice_specific_heat = Parameter(
            SpecificHeat,
            default=heat_transfer.DEFAULT_ICE_HEAT_CAPACITY,
            description="Specific heat capacity of ice",
        )

        self.volume = Parameter(
            Volume | None,
            default=None,
            gt=0,
            description="Volume of the store; the size of a cost given per m3",
        )
        self.energy_capacity = Parameter(
            Energy | None,
            default=None,
            gt=0,
            description=(
                "Cold the store holds between its design states; the size of a cost given per "
                "energy, and empty when the cost is per m3"
            ),
        )

        # Inlets
        self.fluid_in = Port(
            Direction.IN,
            phase=Phase.LIQUID,
            fluid=Fluid.WATER,
            level=Level.CHILLED,
            flow=Flow.IMPOSED,
        )

        # States
        self.ice_fraction = State(Fraction, description="Frozen share of the water of the store")
        self.temperature = State(Temperature, description="Uniform temperature of the store")

        # Outputs
        self.stored_cold = Output(
            Energy,
            description=(
                "Cold held in the store, as the heat needed to melt and warm it to its reference"
            ),
        )
        self.heat_accumulation = Output(
            HeatAccumulation,
            description="Rate at which the store gains heat (negative when it loses)",
        )
        self.is_full = Output(bool, description="True when the store is completely frozen")
        self.is_empty = Output(bool, description="True when the store is completely melted")

        # Outlets
        self.fluid_out = Port(
            Direction.OUT,
            phase=Phase.LIQUID,
            fluid=Fluid.WATER,
            level=Level.CHILLED,
            flow=Flow.IMPOSED,
        )

    def forward(self, inputs, inlets, state):
        """Return the glycol after exchanging heat with the start-of-step store."""
        fraction, temperature = state["ice_fraction"], state["temperature"]

        # Outlets
        inlet = inlets.fluid_in
        effectiveness = self._effectiveness(inlet, fraction, temperature)
        outlet = inlet._with_si(
            T=heat_transfer.effectiveness_outlet_temperature(inlet.T, effectiveness, temperature)
        )

        # Outputs
        outputs = dict(
            stored_cold=heat_transfer.ice_stored_cold(self.water_mass, self.latent_heat, fraction),
            heat_accumulation=heat_transfer.heat_rate(
                inlet.heat_capacity_rate(), inlet.T - outlet.T
            ),
            is_full=fraction >= 1,
            is_empty=fraction <= 0,
        )

        outlets = dict(fluid_out=outlet)
        return outputs, outlets

    def cost_size(self):
        """Return the size that the cost of the store scales with: ``volume`` [m3]."""
        if self.volume is None:
            raise self.missing_size("volume")
        return self.volume

    def cost_size_of(self, quantity):
        """Return the ``energy_capacity`` [J] for a cost per energy, ``None`` for another one."""
        if quantity != "energy":
            return None
        if self.energy_capacity is None:
            raise self.missing_size("energy_capacity")
        return self.energy_capacity

    def update(self, inputs, inlets, outlets, state, dt):
        """Return the ice fraction and the temperature after the step."""
        inlet = inlets.fluid_in
        fraction, temperature = state["ice_fraction"], state["temperature"]
        fraction, temperature = heat_transfer.ice_advance(
            fraction,
            temperature,
            dt,
            inlet.T,
            self._conductance(inlet, fraction, temperature),
            self.water_mass,
            self.latent_heat,
            self.freezing_temperature,
            self.water_specific_heat,
            self.ice_specific_heat,
        )
        return {"ice_fraction": fraction, "temperature": temperature}

    def _rate(self, inlet):
        """Return the glycol capacity rate m_dot * cp [W/K]; reject reverse flow."""
        require_forward(self.path, "fluid_in.m_dot", inlet.m_dot)
        return inlet.heat_capacity_rate()

    def _effectiveness(self, inlet, fraction, temperature):
        """Return the coil effectiveness 1 - exp(-UA / C) [-] after checking the store state."""
        self._check_state(fraction, temperature)
        rate = self._rate(inlet)
        return heat_transfer.ambient_effectiveness(self.thermal_conductance, rate)

    def _conductance(self, inlet, fraction, temperature):
        """Return the coil conductance e * m_dot * cp [W/K]."""
        return heat_transfer.circuit_conductance(
            self._effectiveness(inlet, fraction, temperature), self._rate(inlet)
        )

    def _check_state(self, fraction, temperature):
        """Require the store temperature to match its phase (see the class docstring)."""
        freezing = self.freezing_temperature
        consistent = ops.logical_or(
            ops.logical_or(
                temperature == freezing,
                ops.logical_and(fraction == 0, temperature > freezing),
            ),
            ops.logical_and(fraction == 1, temperature < freezing),
        )
        ops.check(
            consistent,
            ValidationError,
            "{path}: temperature = {temperature} K with ice_fraction = {fraction}; "
            "expected {freezing} K while partly frozen, above it only with no ice and "
            "below it only when fully frozen",
            path=self.path,
            temperature=temperature,
            fraction=fraction,
            freezing=freezing,
            code="invalid_design",
        )
