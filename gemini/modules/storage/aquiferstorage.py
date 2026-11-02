"""Aquifer thermal energy storage (ATES) well pair with a warm and a cold store."""

from typing import Literal

from gemini import ops
from gemini.errors import PhysicsError, ValidationError
from gemini.modules._utils.flow import require_forward
from gemini.modules.declarations import Control, Inlet, Outlet, Output, Parameter, State
from gemini.modules.module import Module
from gemini.physics import energy, fluid, ground, heat_transfer
from gemini.streams.flows import Stream
from gemini.units.quantities import (
    Dimensionless,
    Duration,
    Energy,
    Fraction,
    HeatAccumulation,
    Length,
    MassFlow,
    Power,
    Pressure,
    Temperature,
    TemperatureDifference,
    ThermalConductivity,
    Volume,
    VolumetricHeatCapacity,
)

STORES = ("warm", "cold")
"""The two stores of the well pair, in state order."""

MODES = ("charge", "discharge", "idle")
"""The options of ``mode``, in declared order."""

CHARGE, DISCHARGE, IDLE = (MODES.index(mode) for mode in MODES)
"""The positions of ``"charge"``, ``"discharge"`` and ``"idle"`` in ``MODES``."""


class AquiferStorage(Module):
    """Balanced ATES well pair storing heat in a warm and cold in a cold aquifer store.

    ``mode`` ``"charge"`` produces from the cold well and injects ``injection_in`` into the
    warm well (summer: heat from cooling is stored); ``"discharge"`` produces from the warm
    well and injects into the cold well (winter: stored heat is recovered); ``"idle"`` moves no
    water and requires zero flow. The doublet is balanced: ``production_out`` carries the
    injected mass flow, pressure and fluid at the temperature of the store it is produced from
    (the aquifer temperature in idle mode); well hydraulics belong to well modules.

    Each store is fully mixed and described by its injected water volume V [m3] and its
    temperature change theta = T - T_aq [K] relative to ``aquifer_temperature``; an empty
    store produces native groundwater at the aquifer temperature. Its excess heat is
    E = (rho c)_w V theta, with (rho c)_w from the circuit fluid, and it occupies the thermal
    volume V (rho c)_w / (rho c)_a with (rho c)_a = phi (rho c)_w + (1 - phi) (rho c)_r, a
    cylinder of height ``aquifer_thickness`` H and thermal radius R. Losses to the
    surroundings are transient conduction through the whole envelope A = 2 pi R (R + H),
    averaged over the ``storage_period`` t_p: UA = 2 k A / sqrt(pi alpha t_p) with
    alpha = k / (rho c)_a (``ground.cylinder_store_conductance``, Carslaw and Jaeger 1959), so
    each store relaxes towards the aquifer temperature with the time constant
    (rho c)_w V / UA and the losses scale with the area-to-volume ratio, as observed for ATES
    (Bloemendal and Hartog 2018, Geothermics 71, 306-319). A store above the aquifer
    temperature reports its loss as ``loss_out``, one below it its gain as
    ``loss_out`` (negative). The ``storage_period`` is the charge or discharge season of seasonal
    ATES, about half a year, and the plant states it.

    Each step first applies the injected volume Q dt (mixing) and the withdrawn volume
    (temperature unchanged; the store volume stops at zero, after which native water is
    produced), then the exact exponential conduction decay over ``dt`` at the end-of-step
    volume. The decay is exact for an idle store; with flow the operator splitting is first
    order in ``dt``. When a store empties within one step, the step's production temperature
    is still the start-of-step store temperature.

    ``stored_energy`` is the net excess heat of both stores (the cold store counts negative).
    ``recovery_efficiency`` is the warm store's thermal recovery, heat produced over heat
    injected, both relative to the aquifer temperature (the definition of Bloemendal and
    Hartog 2018); it is NaN (shown as ``None`` in results) until positive heat has been charged.

    Assumptions: no regional groundwater flow, dispersion or buoyancy; no thermal
    interaction between the wells; a sharp, fully mixed store instead of a thermal fringe
    (late-season production temperatures are therefore too high and early ones too low); a
    fully penetrating screen over H; and a conduction boundary layer sqrt(alpha t_p) thin
    against R and H. Dispersion and fringe losses are not resolved, so
    ``ground_conductivity`` is calibratable as an effective value. Valid for low-temperature
    ATES (stores below about 30 degC, so buoyancy flow is weak).
    ``heat_accumulation`` is the rate of change of the stored heat at the start of the step: the
    sensible enthalpy flow of ``injection_in`` minus that of ``production_out`` (``m_dot cp T``
    per stream, the basis of ``energy_balance``) minus the net conduction loss. It is the signed
    storage outflow of ``energy_balance``, so the well pair is first-law closed per call.

    The production temperature does not depend on the injected stream, so a plant that closes
    the groundwater loop through this module (production, pump, heat exchanger, injection) needs
    no iteration: with ``groundwater_flow`` and ``groundwater_pressure`` set, ``production_out`` is
    offered before the other modules run, and the module is called once with the returned
    groundwater, which it produces again at ``groundwater_pressure``.

    Inside, ``mode`` is its position among the options (``CHARGE``, ``DISCHARGE``, ``IDLE``), so
    the modes are selected with ``ops.where`` and the module is traced: a call with the text
    converts it (``_mode``), and the compiler feeds the position of a text column.
    """

    def __init__(self):
        """Declare aquifer data, the operating mode and the two store states."""
        super().__init__()

        # Parameters
        self.aquifer_temperature = Parameter(
            Temperature, description="Undisturbed temperature of the aquifer"
        )
        self.aquifer_thickness = Parameter(
            Length, gt=0, description="Thickness of the storage aquifer"
        )
        self.porosity = Parameter(
            Fraction, gt=0, lt=1, description="Pore volume as a fraction of the aquifer rock volume"
        )
        self.rock_volumetric_heat_capacity = Parameter(
            VolumetricHeatCapacity, description="Volumetric heat capacity of the saturated rock"
        )
        self.ground_conductivity = Parameter(
            ThermalConductivity, calibratable=True, description="Thermal conductivity of the ground"
        )
        self.storage_period = Parameter(
            Duration,
            gt=0,
            description="Duration of one charge or discharge period of the store",
        )
        self.groundwater_pressure = Parameter(
            Pressure | None,
            default=None,
            gt=0,
            description="Pressure of the groundwater; empty when not given",
        )

        # Inlets
        self.injection_in = Inlet(Stream, kind="brine")

        # Controls
        self.mode = Control(
            Literal["charge", "discharge", "idle"],
            description="Operating mode: charge, discharge or idle",
        )
        self.groundwater_flow = Control(
            MassFlow | None,
            default=None,
            ge=0,
            description="Natural groundwater flow through the store; empty means none",
        )

        # States
        self.warm_volume = State(Volume, description="Water volume injected into the warm store")
        self.warm_temperature_change = State(
            TemperatureDifference,
            description="Temperature of the warm store relative to the aquifer temperature",
        )
        self.cold_volume = State(Volume, description="Water volume injected into the cold store")
        self.cold_temperature_change = State(
            TemperatureDifference,
            description="Temperature of the cold store relative to the aquifer temperature",
        )
        self.charged_heat = State(Energy, description="Excess heat injected since the start")
        self.recovered_heat = State(Energy, description="Excess heat produced since the start")

        # Outputs
        self.stored_energy = Output(
            Energy, description="Heat held in the store relative to its reference"
        )
        self.recovery_efficiency = Output(
            Dimensionless | None, description="Share of the stored heat recovered"
        )
        self.warm_temperature = Output(Temperature, description="Temperature of the warm store")
        self.cold_temperature = Output(Temperature, description="Temperature of the cold store")
        self.heat_accumulation = Output(
            HeatAccumulation,
            description="Rate at which the store gains heat (negative when it loses)",
        )

        # Outlets
        self.production_out = Outlet(Stream, kind="brine", offered=True)
        self.loss_out = Outlet(Power, kind="heat")

    def forward(self, inputs, inlets, state):
        """Produce the injected mass flow from the source store of the current mode."""
        mode = self._mode(inputs["mode"])

        # Outlets
        injection_in = inlets.injection_in
        self._volume_flow(injection_in, mode)
        production_out = injection_in._with_si(T=self._production_temperature(mode, state))
        if self.groundwater_pressure is not None:
            production_out = production_out._with_si(p=self.groundwater_pressure)

        losses = self._store_losses(injection_in, state)
        loss_out = energy.total_power(losses)

        # Outputs
        water = self._fluid_heat_capacity(injection_in)
        outputs = dict(
            stored_energy=ground.aquifer_stored_energy(
                water,
                state["warm_volume"],
                state["warm_temperature_change"],
                state["cold_volume"],
                state["cold_temperature_change"],
            ),
            recovery_efficiency=ground.thermal_recovery(
                state["recovered_heat"], state["charged_heat"]
            ),
            warm_temperature=self.aquifer_temperature + state["warm_temperature_change"],
            cold_temperature=self.aquifer_temperature + state["cold_temperature_change"],
            heat_accumulation=(
                heat_transfer.heat_rate(injection_in.heat_capacity_rate(), injection_in.T)
                - heat_transfer.heat_rate(production_out.heat_capacity_rate(), production_out.T)
                - sum(losses)
            ),
        )

        outlets = dict(production_out=production_out, loss_out=loss_out)
        return outputs, outlets

    def _offer(self, inputs, inlets, state):
        """Offer the produced groundwater of a loop through the well pair."""
        flow = inputs["groundwater_flow"]
        if self.groundwater_pressure is None or flow is None:
            raise ValidationError(
                f"{self.path}: groundwater_pressure and groundwater_flow are needed to offer "
                "production_out; expected both on a loop through the well pair",
                code="invalid_design",
            )
        offered = Stream._si(
            m_dot=flow,
            T=self._production_temperature(self._mode(inputs["mode"]), state),
            p=self.groundwater_pressure,
            fluid=self.fluid,
        )
        return {"production_out": offered}

    def _store_losses(self, injection, state):
        """Return the conduction loss [W] of each store to the aquifer around it."""
        water = self._fluid_heat_capacity(injection)
        return [
            heat_transfer.heat_rate(
                ground.store_conductance(
                    volume,
                    self.ground_conductivity,
                    self.porosity,
                    water,
                    self.rock_volumetric_heat_capacity,
                    self.aquifer_thickness,
                    self.storage_period,
                ),
                change,
            )
            for volume, change in (self._store(store, state) for store in STORES)
        ]

    def update(self, inputs, inlets, outlets, state, dt):
        """Return the store volumes, temperature changes and heat totals after the step."""
        mode = self._mode(inputs["mode"])
        injection = inlets.injection_in
        volume = ground.injected_volume(self._volume_flow(injection, mode), dt)
        injected_change = injection.T - self.aquifer_temperature
        water = self._fluid_heat_capacity(injection)
        states = {}
        for store in STORES:
            store_volume, change = self._moved_store(store, mode, state, volume, injected_change)
            conductance = ground.store_conductance(
                store_volume,
                self.ground_conductivity,
                self.porosity,
                water,
                self.rock_volumetric_heat_capacity,
                self.aquifer_thickness,
                self.storage_period,
            )
            states[f"{store}_volume"] = store_volume
            states[f"{store}_temperature_change"] = ground.store_relaxation(
                change, store_volume, conductance, dt, water
            )
        charged = state["charged_heat"]
        states["charged_heat"] = ops.where(
            mode == CHARGE, charged + ground.stored_heat(water, volume, injected_change), charged
        )
        recovered = state["recovered_heat"]
        states["recovered_heat"] = ops.where(
            mode == DISCHARGE,
            recovered + ground.stored_heat(water, volume, state["warm_temperature_change"]),
            recovered,
        )
        return states

    @staticmethod
    def _mode(value):
        """Return the position of the operating mode among the options: a text converts."""
        return MODES.index(value) if isinstance(value, str) else value

    def _production_temperature(self, mode, state):
        """Return the temperature [K] that ``production_out`` has in the running step."""
        change = ops.where(
            mode == CHARGE,
            state["cold_temperature_change"],
            ops.where(mode == DISCHARGE, state["warm_temperature_change"], 0.0),
        )
        return self.aquifer_temperature + change

    def _moved_store(self, store, mode, state, volume, injected_change):
        """Return a store's volume [m3] and temperature change [K] after this step's flow."""
        store_volume, change = self._store(store, state)
        source, target = (
            (mode == DISCHARGE, mode == CHARGE)
            if store == "warm"
            else (mode == CHARGE, mode == DISCHARGE)
        )
        mixed_volume, mixed_change = ground.mix_store(store_volume, change, volume, injected_change)
        drawn = ops.maximum(store_volume - volume, 0.0)
        return (
            ops.where(target, mixed_volume, ops.where(source, drawn, store_volume)),
            ops.where(target, mixed_change, change),
        )

    @staticmethod
    def _store(store, state):
        """Return a store's volume [m3] and temperature change [K] at the start of the step."""
        return state[f"{store}_volume"], state[f"{store}_temperature_change"]

    @staticmethod
    def _fluid_heat_capacity(stream):
        """Return the volumetric heat capacity (rho c)_w [J/m3/K] of the circuit liquid."""
        properties = stream.fluid.properties(stream.p, stream.T)
        return properties.liquid_volumetric_heat_capacity

    def _volume_flow(self, injection, mode):
        """Return the injected liquid volume flow [m3/s] after checking it against the mode."""
        require_forward(self.path, "injection_in.m_dot", injection.m_dot)
        ops.check(
            ops.logical_or(mode != IDLE, injection.m_dot == 0),
            PhysicsError,
            "{path}: injection_in.m_dot = {m_dot} kg/s in idle mode; expected 0",
            path=self.path,
            m_dot=injection.m_dot,
        )
        density = injection.fluid.properties(injection.p, injection.T).rho_l
        return fluid.volume_flow(injection.m_dot, density)
