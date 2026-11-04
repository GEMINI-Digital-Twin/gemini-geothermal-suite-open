"""Thermal breakthrough time of a doublet and pressure interference between doublets in a row.

Breakthrough: Gringarten-Sauty as in Wallmeier et al. (2025) SGP-TR-229 eq. 9,
https://pangea.stanford.edu/ERE/db/GeoConf/papers/SGW/2025/Wallmeier.pdf. Interference: steady
line sources, DoubletCalc 1.4 manual eq. 7 (TNO 2014, link below). Parameter sources are in the
inline comments. Output: breakthrough time (s) and the extra pressure at each injector (Pa).
"""

# DoubletCalc 1.4.3 manual: https://acc.nlog.nl/sites/default/files/6ab98fc3-1ca1-4bbe-b0a2-c5a9658a3597_doubletcalc%20v143%20manual.pdf  # noqa: E501

import math

from gemini_model.model_abstract import StaticModel

YEAR = 365.25 * 24 * 3600  # seconds per year


class DoubletThermalBreakthrough(StaticModel):
    """Compute breakthrough and interference for a homogeneous confined aquifer, steady flow."""

    def __init__(self):
        """Set the defaults: ThermoGIS rock, brine 1030 kg/m3 and 4000 J/kg/K, one doublet."""
        super().__init__()
        self.parameters = {
            "rock_density": 2700.0,  # kg/m3; source: TNO ThermoGIS defaults
            "rock_heat_capacity": 1000.0,  # J/kg/K; source: TNO ThermoGIS defaults
            "water_density": 1030.0,  # kg/m3; assumed brine
            "water_heat_capacity": 4000.0,  # J/kg/K; assumed brine
            "well_spacing": 1500.0,  # producer to injector in the reservoir, m; ThermoGIS default
            "number_of_doublets": 1,  # doublets side by side
            "doublet_spacing": None,  # injector to injector, m; None means well_spacing
        }

    def heat_capacity_aquifer(self):
        """Volumetric heat capacity of the water-filled rock, J/m3/K."""
        p = self.parameters
        rho_c_water = p["water_density"] * p["water_heat_capacity"]
        rho_c_rock = p["rock_density"] * p["rock_heat_capacity"]
        return p["porosity"] * rho_c_water + (1 - p["porosity"]) * rho_c_rock

    def breakthrough_time(self, flowrate, well_spacing=None):
        """Breakthrough time (s) at flowrate (m3/s); well_spacing (m) defaults to the parameter."""
        p = self.parameters
        spacing = p["well_spacing"] if well_spacing is None else well_spacing
        rho_c_water = p["water_density"] * p["water_heat_capacity"]
        return (
            math.pi
            * p["reservoir_thickness"]
            * spacing**2
            * self.heat_capacity_aquifer()
            / (3 * flowrate * rho_c_water)
        )

    def spacing_for_years(self, years, flowrate):
        """Well spacing (m) for a breakthrough time of years at flowrate (m3/s)."""
        return self.parameters["well_spacing"] * math.sqrt(
            years * YEAR / self.breakthrough_time(flowrate)
        )

    def interference_pressure(self, flowrate):
        """Extra pressure (Pa) at each injector from the other doublets, one value per injector."""
        p = self.parameters
        n = int(p["number_of_doublets"])
        if n < 1:
            raise ValueError(f"number_of_doublets must be >= 1, got {n}.")
        spacing = p["well_spacing"]
        d = spacing if p["doublet_spacing"] is None else p["doublet_spacing"]
        unit = (
            flowrate
            * p["viscosity"]
            / (2 * math.pi * p["reservoir_permeability"] * p["reservoir_thickness"])
        )
        return [
            sum(
                unit * math.log(math.hypot(spacing, (i - j) * d) / (abs(i - j) * d))
                for j in range(n)
                if j != i
            )
            + 0.0
            for i in range(n)
        ]

    def calculate_output(self, u, x=None):
        """Breakthrough time and interference pressures at u["flowrate"] (m3/s)."""
        flowrate = u["flowrate"]
        dp = self.interference_pressure(flowrate)
        self.output["breakthrough_time"] = self.breakthrough_time(flowrate)
        self.output["interference_pressure"] = dp
        self.output["interference_pressure_max"] = max(dp)
