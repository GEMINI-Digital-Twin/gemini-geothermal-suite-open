"""Building or process cooling demand on a chilled-water circuit, with latent load."""

from gemini import ops
from gemini.errors import ValidationError
from gemini.modules._utils.flow import require_forward
from gemini.modules.declarations import Boundary, Control, Output, Parameter, Port
from gemini.modules.module import Module
from gemini.physics import heat_transfer, psychrometrics
from gemini.streams.flows import Stream
from gemini.streams.fluid import WATER, Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase
from gemini.units.quantities import (
    Fraction,
    MassFlow,
    Power,
    Pressure,
    Temperature,
    TemperatureDifference,
)


class CoolingGrid(Module):
    """Cooling consumer that warms the chilled-water supply by the sensible and latent loads.

    The circuit's mass flow is imposed by the supply stream, so the return temperature follows
    from the heat taken from the building:

    T_limit = min(maximum_return_temperature, indoor_temperature)
    Q_available = m_dot cp max(0, T_limit - T_supply)
    Q_sensible = min(sensible_cooling_demand, Q_available)
    Q_latent = min(latent_cooling_demand, Q_available - Q_sensible)  if T_supply <= T_dew - margin
    Q_latent = 0                                                     otherwise
    T_return = T_supply + (Q_sensible + Q_latent) / (m_dot cp)

    The dew point ``T_dew`` of the indoor air comes from ``psychrometrics.dew_point`` (Hyland and
    Wexler 1983 saturation pressure, ASHRAE Handbook - Fundamentals 2017, chapter 1). Moisture
    condenses on a coil only when its surface is below the dew point; the coil surface is warmer
    than the water, so dehumidification needs a supply at least ``dew_point_margin`` below the
    dew point (the coil apparatus dew point approach, ASHRAE Handbook - HVAC Systems and
    Equipment 2020, chapter 23, "Air-cooling and dehumidifying coils"). Otherwise the latent
    load is unmet, as with chilled beams or radiant ceilings run above the dew point. The water
    cannot return warmer than the indoor air that heats it, hence the indoor temperature in
    ``T_limit``.

    When the available capacity is short, the sensible load is served first: room thermostats
    control the dry-bulb temperature and humidity drifts. The latent heat (condensation of the
    removed vapour) enters the water like the sensible heat, so the heat on its ports is their sum;
    the condensate drains on the air side and the water mass flow is unchanged.

    The return pressure, the return-temperature limit, the dew-point margin and the indoor state
    are conditions of the consumer: the case gives them (``demand.cooling``), a plant does not.

    On a closed loop ``return_temperature``, ``return_pressure`` and the control ``flow`` set the
    return water: ``return_out`` is offered before the other modules run, and the loads met are
    those the rise of the water up to the return temperature takes. Bind the demand to
    a ``gm.case.from_csv`` column. Without them the return follows from the loads, as in a
    substation. Unmet loads are reported, never an error.

    Simplifications: steady state, constant fluid properties (the inlet ``cp``), no pressure
    drop, no coil characteristic beyond the return limit and the dew-point test, and loads
    given as boundaries instead of computed from the air side. The model conserves mass and is
    first-law closed: the sensible enthalpy rise of the stream equals the heat on its ports. Valid
    for chilled water or glycol with nonnegative flow and indoor air from 173.15 K to 473.15 K
    with a relative humidity in (0, 1].
    """

    bypass = {}
    """Removable: a demand the plant may decline to serve, with its branch."""

    plant_role = "cooling_supply"

    def __init__(self):
        """Declare the consumer's limits, indoor conditions, loads and absorbed heat."""
        super().__init__()
        self.fluid = WATER

        # Parameters
        self.maximum_return_temperature = Parameter(
            Temperature | None,
            default=None,
            case="demand.cooling.maximum_return_temperature",
            description=(
                "Highest return temperature the consumer can warm the chilled water to; empty "
                "takes it from the case"
            ),
        )
        self.dew_point_margin = Parameter(
            TemperatureDifference | None,
            default=None,
            ge=0,
            case="demand.cooling.dew_point_margin",
            description=(
                "Margin above the dew point below which no latent load is taken; empty takes it "
                "from the case"
            ),
        )
        self.return_temperature = Parameter(
            Temperature | None,
            default=None,
            structural=True,
            case="demand.cooling.return_temperature",
            description=(
                "Return temperature of the chilled-water circuit; empty takes it from the case"
            ),
        )
        self.maximum_supply_temperature = Parameter(
            Temperature | None,
            default=None,
            case="demand.cooling.supply_temperature",
            description=(
                "Highest supply temperature at which the cooling demand is served; empty takes it "
                "from the case"
            ),
        )
        self.return_pressure = Parameter(
            Pressure | None,
            default=None,
            case="demand.cooling.return_pressure",
            description=(
                "Pressure of the stream leaving the consumer; empty takes it from the case"
            ),
        )

        # Inlets
        self.supply_in = Port(
            Direction.IN,
            phase=Phase.LIQUID,
            fluid=Fluid.WATER,
            level=Level.CHILLED,
            flow=Flow.IMPOSED,
        )

        # Controls
        self.flow = Control(
            MassFlow | None,
            default=None,
            ge=0,
            description=(
                "Mass flow of the chilled-water circuit; empty lets the supply stream impose it"
            ),
        )

        # Boundaries
        self.sensible_cooling_demand = Boundary(
            Power, ge=0, description="Sensible cooling load of the building"
        )
        self.latent_cooling_demand = Boundary(
            Power, ge=0, description="Latent cooling load of the building"
        )
        self.indoor_temperature = Boundary(
            Temperature,
            case="demand.cooling.indoor_temperature",
            description="Indoor air temperature of the building",
        )
        self.indoor_relative_humidity = Boundary(
            Fraction,
            gt=0,
            case="demand.cooling.indoor_relative_humidity",
            description="Relative humidity of the indoor air",
        )

        # Outputs
        self.unmet_sensible = Output(Power, description="Sensible cooling load not served")
        self.unmet_latent = Output(Power, description="Latent cooling load not served")
        self.surplus = Output(
            Power, description="Heat offered to the consumer beyond what it could take"
        )
        self.dew_point = Output(Temperature, description="Dew point of the indoor air")
        self.is_unmet = Output(bool, description="True when the demand was not fully served")

        # Outlets
        self.return_out = Port(
            Direction.OUT,
            phase=Phase.LIQUID,
            fluid=Fluid.WATER,
            level=Level.CHILLED,
            flow=Flow.IMPOSED,
            offered=True,
        )

    def forward(self, inputs, inlets, state):
        """Return the supply stream warmed by the absorbed building heat."""

        # Outlets
        supply_in = inlets.supply_in
        if self.return_temperature is None:
            sensible, latent = self._met_loads(inputs, supply_in)
            return_out = supply_in._with_si(
                T=self._warmed_temperature(inputs, supply_in, sensible + latent)
            )
            surplus = 0.0
        else:
            return_out = self._offer(inputs, inlets, state)["return_out"]
            sensible, latent = self._met_loads(inputs, supply_in, return_out)
            surplus = self._available(inputs, supply_in, return_out) - sensible - latent

        # Outputs
        unmet_sensible = inputs["sensible_cooling_demand"] - sensible
        unmet_latent = inputs["latent_cooling_demand"] - latent
        outputs = dict(
            unmet_sensible=unmet_sensible,
            unmet_latent=unmet_latent,
            surplus=surplus,
            dew_point=psychrometrics.dew_point(
                inputs["indoor_temperature"], inputs["indoor_relative_humidity"]
            ),
            is_unmet=ops.logical_or(unmet_sensible > 0, unmet_latent > 0),
        )

        outlets = dict(return_out=return_out)
        return outputs, outlets

    def _loop_start(self, inputs, port, entering):
        """Start a building loop at the warmest return temperature."""
        return ops.minimum(self.maximum_return_temperature, inputs["indoor_temperature"])

    def _offers(self):
        """Offer only on a closed loop; otherwise the outlet follows from the inlet."""
        return self.return_temperature is not None

    def _offer(self, inputs, inlets, state):
        """Offer the return water of a closed loop, at the fixed temperature and the given flow."""
        if (
            self.return_temperature is None
            or self.return_pressure is None
            or inputs["flow"] is None
        ):
            raise ValidationError(
                f"{self.path}: return_temperature, return_pressure and flow are needed to offer "
                "return_out; expected all three on a closed loop",
                code="invalid_design",
            )
        offered = Stream._si(
            m_dot=inputs["flow"],
            T=self.return_temperature,
            p=self.return_pressure,
            fluid=self.fluid,
        )
        return {"return_out": offered}

    def _warmed_temperature(self, inputs, supply_in, absorbed):
        """Return the return temperature [K] after the building gave ``absorbed`` [W] to it."""
        warmed = ops.minimum(
            self._return_limit(inputs),
            supply_in.T
            + heat_transfer.temperature_change(absorbed, supply_in.heat_capacity_rate()),
        )
        return ops.where(absorbed == 0, supply_in.T, warmed)

    def _available(self, inputs, supply_in, return_out=None):
        """Return the cold [W] the water takes up to its return limit."""
        return heat_transfer.setpoint_duty(
            supply_in.heat_capacity_rate(), self._return_limit(inputs, return_out) - supply_in.T
        )

    def _met_loads(self, inputs, supply_in, return_out=None):
        """Return the met sensible and latent loads [W]; the rise of the water on a closed loop."""
        require_forward(self.path, "supply_in.m_dot", supply_in.m_dot)
        if self.dew_point_margin is None:
            raise ValidationError(
                f"{self.path}: dew_point_margin = None; expected demand.cooling.dew_point_margin "
                "in the case",
                path="demand.cooling.dew_point_margin",
                code="missing_value",
            )
        available = self._available(inputs, supply_in, return_out)
        dew_point = psychrometrics.dew_point(
            inputs["indoor_temperature"], inputs["indoor_relative_humidity"]
        )
        dry = supply_in.T > dew_point - self.dew_point_margin
        return heat_transfer.sensible_latent_loads(
            available, inputs["sensible_cooling_demand"], inputs["latent_cooling_demand"], dry
        )

    def _return_limit(self, inputs, return_out=None):
        """Return the warmest return temperature [K]: the fixed one, the parameter or indoor air."""
        if self.return_temperature is not None and return_out is not None:
            return return_out.T
        return ops.minimum(self.maximum_return_temperature, inputs["indoor_temperature"])
