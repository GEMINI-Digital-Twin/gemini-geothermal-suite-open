"""Single-effect lithium-bromide absorption chiller driven by hot brine.

The chiller cools the brine from its inlet temperature down to a floor and turns that heat into
cold at a fixed thermal COP. COP source: US DOE CHP Technology Fact Sheet, Absorption Chillers,
DOE/EE-1608 (2017),
https://www.energy.gov/sites/prod/files/2017/06/f35/CHP-Absorption%20Chiller-compliant.pdf
"""

from gemini_model.model_abstract import StaticModel

_MIN_CAPACITY_RATE = 1e-9  # W/K, guards against division by zero


class AbsorptionChiller(StaticModel):
    """Absorption chiller: brine heat above a temperature floor in, cold out at a fixed COP."""

    def __init__(self):
        """Set the defaults for a single-effect lithium-bromide chiller on brine."""
        super().__init__()
        self.parameters = {
            "cop_thermal": 0.75,  # cold out per drive heat in; US DOE DOE/EE-1608 (2017)
            "min_driving_temperature": 78.0,  # C, coldest usable brine; assumed (about 80 C wanted)
            "fluid_density": 1030.0,  # kg/m3, brine
            "specific_heat": 4000.0,  # J/kg/K, brine
            "flow_resistance": 0.0,  # bar per m3/s on the brine side, as in the filter
            "auxiliary_power_fraction": 0.03,  # W of fan and pump electricity per W cold; assumed
        }

    def calculate_output(self, u, x=None):
        """Cold, drive heat and brine outlet from u: pressure (bar), temperature (C), flow (m3/s).

        Optional ``u["temperature_floor"]`` (C) raises the lowest brine outlet allowed, for
        example what a downstream heat exchanger still needs; optional ``u["cooling_demand"]``
        (W) caps the cold produced.
        """
        p = self.parameters
        pressure = u["pressure"]
        temperature = u["temperature"]
        flow_rate = u["flow_rate"]
        demand = u.get("cooling_demand")

        floor = p["min_driving_temperature"]
        if u.get("temperature_floor") is not None:
            floor = max(floor, u["temperature_floor"])

        capacity_rate = p["fluid_density"] * flow_rate * p["specific_heat"]  # W/K
        drive_heat = 0.0
        temperature_out = temperature
        if capacity_rate >= _MIN_CAPACITY_RATE and temperature > floor:
            drive_heat = capacity_rate * (temperature - floor)
            if demand is not None:
                drive_heat = min(drive_heat, demand / p["cop_thermal"])
            temperature_out = temperature - drive_heat / capacity_rate
        cooling_power = p["cop_thermal"] * drive_heat

        self.output = {
            "pressure_in": pressure,
            "pressure_out": pressure - flow_rate * p["flow_resistance"],
            "temperature_in": temperature,
            "temperature_out": temperature_out,
            "flow_rate": flow_rate,
            "flow_rate_m3h": flow_rate * 3600.0,
            "drive_temperature_floor": floor,
            "drive_heat": drive_heat,
            "cooling_power": cooling_power,
            "cooling_unmet": demand - cooling_power if demand is not None else 0.0,
            "power_el": p["auxiliary_power_fraction"] * cooling_power,
            "power_th": 0.0,
            "emission": 0.0,
        }
