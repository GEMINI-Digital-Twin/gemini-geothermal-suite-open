"""Production temperature decline of a geothermal doublet after thermal breakthrough."""

from gemini.modules._utils.flow import require_forward
from gemini.modules.declarations import Boundary, Inlet, Outlet, Output, Parameter, State
from gemini.modules.module import Module
from gemini.physics import fluid, ground
from gemini.streams.flows import Stream
from gemini.units.quantities import (
    Duration,
    Fraction,
    Length,
    Temperature,
    TemperatureDifference,
    Volume,
    VolumetricHeatCapacity,
)


class ThermalDecline(Module):
    """Cold-front breakthrough and production temperature decline of a balanced doublet.

    Placed between a ``ProductionReservoir`` sandface and the production well, it lowers the
    produced temperature once the cooled region around the injector reaches the producer.
    The state is the cumulative injected volume V [m3]; in a balanced doublet it equals the
    produced volume, so each step adds the inlet liquid volume flow times ``dt`` (exact for a
    flow that is constant over the step).

    Breakthrough follows Gringarten and Sauty (1975, J. Geophys. Res. 80(35), 4956-4962): the
    thermal front reaches the producer after the injected volume
    V_B = pi L**2 H (rho c)_a / (3 (rho c)_w), with L the ``well_spacing``, H the
    ``aquifer_thickness``, (rho c)_a = phi (rho c)_w + (1 - phi) (rho c)_r and (rho c)_w the
    liquid density times heat capacity of the inlet fluid. ``breakthrough_time`` is V_B / Q at
    the current liquid volume flow Q, counted from the start of injection (NaN at zero flow,
    shown as ``None`` in results). After breakthrough the doublet's streamlines arrive one after
    another: the share f = theta / pi of the flow on streamlines whose thermal travel time
    3 (sin theta - theta cos theta) / sin(theta)**3 * t_B has passed arrives at the injection
    temperature (``ground.doublet_cold_fraction``), so
    fluid_out_T = T_in - f(V / V_B) (T_in - injection_temperature), where T_in is the reservoir
    temperature carried by the inlet.

    Assumptions: homogeneous, isotropic, confined aquifer of constant thickness; fully
    penetrating wells; no regional flow; piston-like displacement with local thermal
    equilibrium between water and rock; no heat recharge from the confining beds (which makes
    the decline an upper bound, adequate when the aquifer is thick compared with the
    conduction length sqrt(alpha t) of the cap and base rock over the operating time); constant
    properties; and the current injection temperature applies to all injected water. Mass and
    pressure pass unchanged. The module is deliberately not first-law closed: the temperature
    drop is a correction of the open aquifer boundary, so the stream audit shows the residual
    m_dot cp (T_in - fluid_out_T), which is not heat lost to the environment.

    NOTE(refactor): written with ops, but a graph break while the graph has no ``scan``: the
    injected volume is a state.
    """

    def __init__(self):
        """Declare doublet geometry, rock data, the injection boundary and the volume state."""
        super().__init__()

        # Parameters
        self.well_spacing = Parameter(
            Length, gt=0, description="Distance between the production and injection wells"
        )
        self.aquifer_thickness = Parameter(
            Length, gt=0, description="Thickness of the aquifer between the wells"
        )
        self.porosity = Parameter(
            Fraction, gt=0, lt=1, description="Pore volume as a fraction of the aquifer rock volume"
        )
        self.rock_volumetric_heat_capacity = Parameter(
            VolumetricHeatCapacity, description="Volumetric heat capacity of the saturated rock"
        )

        # Inlets
        self.fluid_in = Inlet(Stream, kind="brine")

        # Boundaries
        self.injection_temperature = Boundary(
            Temperature, description="Temperature of the injected water"
        )

        # States
        self.injected_volume = State(
            Volume, description="Cumulative injected volume since the start of injection"
        )

        # Outputs
        self.breakthrough_time = Output(
            Duration | None,
            description="Time at which the cold front reaches the producer; empty at zero flow",
        )
        self.temperature_drop = Output(
            TemperatureDifference,
            description="Fall of the produced temperature below the initial one",
        )

        # Outlets
        self.fluid_out = Outlet(Stream, kind="brine")

    def forward(self, inputs, inlets, state):
        """Lower the reservoir temperature by the cold-water share of the produced flow."""

        # Outlets
        inlet = inlets.fluid_in
        flow = self._liquid_flow(inlet)
        volume = self._breakthrough_volume(inlet)
        drop = ground.doublet_temperature_drop(
            state["injected_volume"], volume, inlet.T, inputs["injection_temperature"]
        )
        outlet = inlet._with_si(T=inlet.T - drop)

        # Outputs
        outputs = dict(
            breakthrough_time=ground.doublet_breakthrough_time(volume, flow),
            temperature_drop=drop,
        )

        outlets = dict(fluid_out=outlet)
        return outputs, outlets

    def update(self, inputs, inlets, outlets, state, dt):
        """Return the injected volume after the step."""
        flow = self._liquid_flow(inlets.fluid_in)
        return {"injected_volume": state["injected_volume"] + ground.injected_volume(flow, dt)}

    def _breakthrough_volume(self, inlet):
        """Return the Gringarten-Sauty breakthrough volume V_B [m3] for the inlet fluid."""
        properties = inlet.fluid.properties(inlet.p, inlet.T)
        water = properties.liquid_volumetric_heat_capacity
        aquifer = ground.aquifer_volumetric_heat_capacity(
            self.porosity, water, self.rock_volumetric_heat_capacity
        )
        return ground.doublet_breakthrough_volume(
            self.well_spacing, self.aquifer_thickness, aquifer, water
        )

    def _liquid_flow(self, inlet):
        """Return the produced liquid volume flow [m3/s]; reverse flow is outside the model."""
        require_forward(self.path, "fluid_in.m_dot", inlet.m_dot)
        return fluid.volume_flow(inlet.m_dot, inlet.fluid.properties(inlet.p, inlet.T).rho_l)
