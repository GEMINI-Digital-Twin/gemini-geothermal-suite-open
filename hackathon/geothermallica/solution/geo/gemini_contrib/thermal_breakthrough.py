"""Thermal breakthrough time of a doublet and pressure interference between doublets in a row.

Breakthrough: first arrival of the cold front at the producer, Gringarten-Sauty for a doublet in a
confined aquifer, as written in Wallmeier et al. (2025) SGP-TR-229, eq. 9,
https://pangea.stanford.edu/ERE/db/GeoConf/papers/SGW/2025/Wallmeier.pdf:

    t_bt = pi H L^2 (rho c)_a / (3 Q rho_w c_w)
    (rho c)_a = phi rho_w c_w + (1 - phi) rho_r c_r

Interference: steady line sources as in DoubletCalc 1.4, eq. 7 (TNO 2014, report R11396, manual
linked below). The n doublets stand side by side, injectors on one line D apart and each producer
L from its injector. The extra pressure at injector i from doublet j != i is

    dp_ij = Q mu / (2 pi k H) ln(sqrt(L^2 + (|i - j| D)^2) / (|i - j| D))

Default rock density and heat capacity and well spacing are TNO ThermoGIS defaults,
https://pythermogis-15909e.ci.tno.nl/theory/utcprops/contents/.
"""

# DoubletCalc 1.4.3 manual: https://acc.nlog.nl/sites/default/files/6ab98fc3-1ca1-4bbe-b0a2-c5a9658a3597_doubletcalc%20v143%20manual.pdf  # noqa: E501

import math

from gemini_model.model_abstract import StaticModel

YEAR = 365.25 * 24 * 3600  # seconds per year (s)


class DoubletThermalBreakthrough(StaticModel):
    """Thermal breakthrough time of a doublet and injector pressure from neighbouring doublets.

    Analytic, homogeneous and isotropic aquifer, no heat exchange with cap and base rock, steady
    pressure field; the doublets are identical and run at the same flowrate.

    Parameters: reservoir_thickness (m), porosity (-), rock_density (kg/m3), rock_heat_capacity
    (J/kg/K), water_density (kg/m3), water_heat_capacity (J/kg/K), well_spacing (m),
    reservoir_permeability (m2), viscosity (Pa s), number_of_doublets (-), doublet_spacing (m,
    None: equal to well_spacing).
    Inputs (u): flowrate (m3/s) per doublet.
    Outputs: breakthrough_time (s), interference_pressure (Pa, list with one value per injector)
    and interference_pressure_max (Pa).
    """

    def __init__(self):
        """Initialize with ThermoGIS rock defaults, brine 1030 kg/m3, 4000 J/kg/K, one doublet."""
        super().__init__()
        self.parameters = {
            "rock_density": 2700.0,  # kg/m3
            "rock_heat_capacity": 1000.0,  # J/kg/K
            "water_density": 1030.0,  # kg/m3
            "water_heat_capacity": 4000.0,  # J/kg/K
            "well_spacing": 1500.0,  # producer to injector at reservoir level (m)
            "number_of_doublets": 1,  # doublets in a row (-)
            "doublet_spacing": None,  # injector to injector (m), None: well_spacing
        }

    def heat_capacity_aquifer(self):
        """Heat capacity per volume of the water-filled rock (J/m3/K)."""
        p = self.parameters
        rho_c_water = p["water_density"] * p["water_heat_capacity"]
        rho_c_rock = p["rock_density"] * p["rock_heat_capacity"]
        return p["porosity"] * rho_c_water + (1 - p["porosity"]) * rho_c_rock

    def breakthrough_time(self, flowrate, well_spacing=None):
        """Breakthrough time (s) at flowrate (m3/s) and well_spacing (m, default the parameter)."""
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
        """Well spacing (m) that gives a breakthrough time of years (a) at flowrate (m3/s)."""
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
        """Calculate breakthrough time and interference pressure at the flowrate in u."""
        flowrate = u["flowrate"]  # m3/s
        dp = self.interference_pressure(flowrate)
        self.output["breakthrough_time"] = self.breakthrough_time(flowrate)
        self.output["interference_pressure"] = dp
        self.output["interference_pressure_max"] = max(dp)
