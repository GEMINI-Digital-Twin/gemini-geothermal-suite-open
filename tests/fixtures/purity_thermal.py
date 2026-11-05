"""Purity cases of the grids, heating, treatment and cooling classes (see ``purity.py``)."""

from gemini.modules import GasGrid
from gemini.modules.cooling import AbsorptionUnit, AdsorptionChiller
from gemini.modules.grids import (
    ChemicalGrid,
    CoolingGrid,
    ElectricityGrid,
    HeatingGrid,
    WasteGrid,
)
from gemini.modules.heating import CHP, Boiler, ElectricBoiler, HeatPump
from gemini.modules.treatment import (
    Blowdown,
    Degasser,
    Desander,
    Filter,
    Flare,
    InhibitorDosing,
)
from gemini.streams.flows import Stream
from gemini.streams.fluid import BRINE, Fluid
from gemini.streams.ports import Ports
from tests.fixtures import si
from tests.fixtures.designs import with_values


def water(flow, temperature, pressure=3e5, fluid=BRINE):
    """Return a stream of ``flow`` [kg/s], ``temperature`` [K] and ``pressure`` [Pa]."""
    return Stream._si(m_dot=flow, T=temperature, p=pressure, fluid=fluid)


def case(cls, params, inlets=None, inputs=None):
    """Return a configured ``cls`` and a run that calls it and its ``forward`` directly."""
    inlets, inputs = inlets or {}, inputs or {}
    module = si.set_params(with_values(cls()), "", params)

    def run(module):
        module(**inlets, **inputs)
        module.forward(dict(inputs), Ports(inlets), {})

    return module, run


def grid_gas():
    """Return the grid gas offered by a gas grid."""
    return with_values(GasGrid())._offered()["gas_out"]


def chemical_product():
    """Return the product offered by a chemical grid."""
    grid = ChemicalGrid()
    grid.fluid = BRINE
    return grid._offered()["chemical_out"]


def boiler_case():
    """Return a gas boiler."""
    params = {"capacity": 1e5, "efficiency": 0.8}
    return case(
        Boiler,
        params,
        dict(fluid_in=water(10, 300, 1e6), fuel_in=grid_gas()),
        dict(temperature_setpoint=360.0),
    )


def electric_boiler_case():
    """Return an electric boiler."""
    params = {"capacity": 1e5, "efficiency": 0.8}
    return case(
        ElectricBoiler,
        params,
        dict(fluid_in=water(10, 300, 1e6)),
        dict(temperature_setpoint=360.0),
    )


def chp_case():
    """Return an engine."""
    params = dict(
        electric_capacity=1e6,
        electric_efficiency=0.4,
        thermal_efficiency=0.45,
        maximum_outlet_temperature=363.15,
    )
    inlets = dict(fluid_in=water(20, 333.15), fuel_in=grid_gas())
    return case(CHP, params, inlets, dict(load_fraction=1.0))


def heat_pump_case():
    """Return a heat pump."""
    params = {"mode": "heating", "capacity": 2e6}
    inlets = dict(source_in=water(20, 300), sink_in=water(10, 320))
    return case(HeatPump, params, inlets, dict(temperature_setpoint=340.0))


def electricity_grid_case():
    """Return a connection with limits."""
    inlets = dict(power_out=[3e6], power_in=[1e6])
    return case(ElectricityGrid, {"import_limit": 1e6, "export_limit": 5e5}, inlets)


def heating_grid_case():
    """Return a consumer on an open circuit."""
    inlets = dict(supply_in=water(2, 343.15))
    return case(HeatingGrid, {"minimum_return_temperature": 313.15}, inlets, dict(heat_demand=1e5))


def cooling_grid_case():
    """Return a consumer on an open circuit."""
    params = {"maximum_return_temperature": 289.15, "dew_point_margin": 3.0}
    inputs = dict(
        sensible_cooling_demand=5e4,
        latent_cooling_demand=1e4,
        indoor_temperature=297.15,
        indoor_relative_humidity=0.5,
    )
    return case(CoolingGrid, params, dict(supply_in=water(2, 280.15)), inputs)


def sorption_inlets(generator, chilled, cooling):
    """Return the three circuits of a sorption machine."""
    return dict(
        generator_in=water(*generator), chilled_in=water(*chilled), cooling_in=water(*cooling)
    )


def absorption_case():
    """Return an absorption chiller."""
    params = dict(
        mode="chiller",
        capacity=1e6,
        characteristic_slope=20000,
        minimum_driving_difference=10,
        rejection_coefficient=2.2,
        evaporator_coefficient=1.2,
        auxiliary_power_ratio=0.01,
    )
    inlets = sorption_inlets((10, 361.15), (10, 285.15), (25, 303.15))
    return case(AbsorptionUnit, params, inlets, dict(temperature_setpoint=280.15))


def adsorption_case():
    """Return an adsorption chiller."""
    params = dict(
        capacity=1e5,
        characteristic_slope=2000,
        minimum_driving_difference=5,
        rejection_coefficient=2.0,
        evaporator_coefficient=1.0,
        auxiliary_power_ratio=0.02,
    )
    inlets = sorption_inlets((5, 343.15), (5, 291.15), (10, 300.15))
    return case(AdsorptionChiller, params, inlets, dict(temperature_setpoint=285.15))


def degasser_case():
    """Return a degasser that separates half of the free gas."""
    params = {"separation_efficiency": 0.5}
    inlets = dict(fluid_in=water(40, 350, 1e6, Fluid(gas_mass_fraction=0.02)))
    return case(Degasser, params, inlets)


def desander_case():
    """Return a desander."""
    params = {"separation_efficiency": 0.9, "nominal_pressure_drop": 1e5, "nominal_mass_flow": 40.0}
    return case(Desander, params, dict(fluid_in=water(20, 350, 1e6)), dict(sand_concentration=0.05))


def inhibitor_case():
    """Return an inhibitor dosing."""
    inlets = dict(fluid_in=water(50, 340, 8e5), chemical_in=chemical_product())
    return case(InhibitorDosing, {"product_concentration": 0.4}, inlets, dict(dose=2e-5))


def flare_case():
    """Return a flare."""
    fluid = Fluid(kind="gas", gas_composition={"CH4": 0.8, "CO2": 0.2})
    return case(Flare, {}, dict(gas_in=water(0.1, 330, 2e5, fluid)))


CASES = {
    "AbsorptionUnit": absorption_case,
    "AdsorptionChiller": adsorption_case,
    "Blowdown": lambda: case(
        Blowdown, {}, dict(fluid_in=water(8, 330)), dict(blowdown_fraction=0.25)
    ),
    "Boiler": boiler_case,
    "CHP": chp_case,
    "ChemicalGrid": lambda: case(ChemicalGrid, {}),
    "CoolingGrid": cooling_grid_case,
    "Degasser": degasser_case,
    "Desander": desander_case,
    "ElectricBoiler": electric_boiler_case,
    "ElectricityGrid": electricity_grid_case,
    "Filter": lambda: case(Filter, {}, dict(fluid_in=water(20, 300, 1e6))),
    "Flare": flare_case,
    "GasGrid": lambda: case(GasGrid, {}),
    "HeatPump": heat_pump_case,
    "HeatingGrid": heating_grid_case,
    "InhibitorDosing": inhibitor_case,
    "WasteGrid": lambda: case(WasteGrid, {}, dict(waste_in=[water(1, 300)])),
}
"""``{class name: function giving (module, run)}`` of the classes of the thermal folders."""
