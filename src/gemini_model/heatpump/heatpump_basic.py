"""HeatpumpBasic model.

Heatpump model based on Carnot-efficiency model or a Lorenz-efficiency model.

References
----------
Carnot COP equation:
    COP_carnot = eta_carnot * (Th / (Th - Ts))
    where Th and Ts are the (constant) condenser and evaporator temperatures [K].
    See: Carnot, S. (1824). "Reflexions sur la puissance motrice du feu."
    Also: Cengel, Y. A., & Boles, M. A. (2015). "Thermodynamics: An Engineering
    Approach" (8th ed.), McGraw-Hill, Chapter 11 (Refrigeration Cycles).

Lorenz COP equation:
    COP_lorenz = eta_lorenz * (Th / (Th - Ts))
    where Th and Ts are the logarithmic mean temperatures of the heat sink
    (condenser) and heat source (evaporator) glide, respectively:
    Th = (Th_in - Th_out) / ln(Th_in / Th_out) and
    Ts = (Ts_in - Ts_out) / ln(Ts_in / Ts_out).
    The Lorenz cycle extends the Carnot cycle to non-isothermal heat exchange
    (glide), which is relevant for heat pumps with secondary fluids.
    See: Lorenz, H. (1894). "Die Ermittlung der Grenzwerte der thermodynamischen
    Energieumwandlung." Zeitschrift fur die gesamte Kalte-Industrie.
    Also: Kuo, C. S. et al. (2005). "Analysis of a Lorenz refrigeration cycle
    for heat pumps," and ASHRAE Handbook - Fundamentals, Chapter on
    Thermodynamics and Refrigeration Cycles.
"""

import numpy as np
from scipy.optimize import minimize

from gemini_model.model_abstract import StaticModel


class HeatpumpBasic(StaticModel):
    """HeatpumpBasic model."""

    def __init__(self):
        """Model initialization.

        Sets up default parameters for the heat pump model, including the
        operating mode ("carnot" or "lorenz"), efficiency factors relative to
        the ideal Carnot/Lorenz COP, a nominal COP used as the optimizer's
        initial guess, fluid properties (specific heat and density for the
        hot/sink and source loops), the target hot side outlet temperature,
        and the minimum allowed source side outlet temperature.
        """
        self.parameters = {
            "mode": "carnot",
            "eta_carnot": 0.5,
            "eta_lorenz": 0.5,
            "COP_0": 3.0,
            "Cp_h": 4181,  # J/kg.K
            "Cp_s": 4181,  # J/kg.K
            "rho_h": 1000,  # kg/m3
            "rho_s": 1000,  # kg/m3
            "Th_out_target": 80,  # °C
            "Ts_in_minimum": 10,  # °C
        }
        self.output = {}

    def update_parameters(self, parameters):
        """Update model parameters.

        Parameters
        ----------
        parameters: dict
            Parameters dict as defined by the model.
        """
        for key, value in parameters.items():
            self.parameters[key] = value

    def initialize_state(self, x):
        """Generate an initial state based on user parameters.

        Not applicable: HeatpumpBasic is a static model with no internal
        state, so this method is a no-op.
        """
        pass

    def update_state(self, u, x):
        """Update the state based on input u and state x.

        Not applicable: HeatpumpBasic is a static model with no internal
        state, so this method is a no-op.
        """
        pass

    def calculate_output(self, u, x):
        """Calculate output based on input u and state x.

        Converts inputs (temperatures in °C, volumetric flows in m3/h) to SI
        units (K, kg/s), solves for the operating point via `_calculate`, and
        stores the results (COP, outlet temperatures, thermal production and
        electrical consumption) in `self.output`.

        Parameters
        ----------
        u: dict
            Model inputs: "Th_in" (°C), "Ts_in" (°C), "qh" (m3/h), "qs" (m3/h).
        x: state
            Model state (unused, model is static).
        """
        # get input
        Th_out = self.parameters["Th_out_target"] + 273.15  # Convert to Kelvin
        Th_in = u["Th_in"] + 273.15  # Convert to Kelvin
        Ts_in = u["Ts_in"] + 273.15  # Convert to Kelvin
        mh = u["qh"] * self.parameters["rho_h"] / 3600  # Convert m3/h to kg/s
        ms = u["qs"] * self.parameters["rho_s"] / 3600  # Convert m3/h to kg/s

        result = self._calculate(Th_out, Th_in, Ts_in, mh, ms)

        self.output["COP"] = result[0]
        self.output["Th_out"] = result[1] - 273.15  # Convert back to Celsius
        self.output["Ts_out"] = result[2] - 273.15  # Convert back to Celsius
        self.output["Thermal_production"] = result[3]
        self.output["electrical_consumption"] = result[4]

    def _calculate(self, Th_out, Th_in, Ts_in, mh, ms):
        """Solve for the heat pump operating point (COP, outlet temperatures,
        thermal production and electrical consumption).

        Uses `scipy.optimize.minimize` (Nelder-Mead) to jointly solve the
        thermodynamic efficiency equation (Carnot or Lorenz, selected via
        `self.parameters['mode']`) together with the energy balance equation
        (Qh = Qs + electrical work, expressed as COP = Qh/(Qh-Qs)).

        If the resulting source outlet temperature `Ts_out` drops below
        `Ts_in_minimum`, the problem is re-solved with `Ts_out` fixed at that
        minimum and `Th_out` (the target hot outlet temperature) allowed to
        drop instead, via `carnot_model2`/`lorenz_model2`.

        Parameters
        ----------
        Th_out: float
            Target hot side (sink) outlet temperature [K].
        Th_in: float
            Hot side (sink) inlet temperature [K].
        Ts_in: float
            Source side inlet temperature [K].
        mh: float
            Hot side (sink) mass flow rate [kg/s].
        ms: float
            Source side mass flow rate [kg/s].

        Returns
        -------
        tuple
            (COP, Th_out, Ts_out, thermal_production, electrical_consumption)
        """

        def lorenz_model(x, Th_out, Th_in, Ts_in, mh, ms):
            """Residual function for the Lorenz-efficiency model, solving for
            (COP, Ts_out) given a fixed target Th_out.

            Combines two residuals: J1 enforces the Lorenz COP equation
            COP = eta_lorenz * (Th / (Th - Ts)), where Th and Ts are the
            logarithmic mean temperatures of the sink and source glide
            (see module reference for the Lorenz cycle); J2 enforces the
            energy balance COP = Qh / (Qh - Qs).
            """
            COP = x[0]
            Ts_out = x[1]

            Qh = self.parameters["Cp_h"] * (Th_out - Th_in) * mh
            Qs = self.parameters["Cp_s"] * (Ts_in - Ts_out) * ms

            Th = (Th_in - Th_out) / np.log(Th_in / Th_out)
            Ts = (Ts_in - Ts_out) / np.log(Ts_in / Ts_out)

            J1 = np.abs(COP - (self.parameters["eta_lorenz"] * (Th / (Th - Ts))))
            J2 = np.abs(COP - Qh / (Qh - Qs))
            J = J1 + J2
            return J

        def lorenz_model2(x, Ts_out, Th_in, Ts_in, mh, ms):
            """Residual function for the Lorenz-efficiency model, solving for
            (COP, Th_out) given a fixed minimum source outlet temperature
            Ts_out (used when the unconstrained solution violates
            Ts_in_minimum). See `lorenz_model` for the underlying equations.
            """
            COP = x[0]
            Th_out = x[1]

            Qh = self.parameters["Cp_h"] * (Th_out - Th_in) * mh
            Qs = self.parameters["Cp_s"] * (Ts_in - Ts_out) * ms

            Th = (Th_in - Th_out) / np.log(Th_in / Th_out)
            Ts = (Ts_in - Ts_out) / np.log(Ts_in / Ts_out)

            J1 = np.abs(COP - (self.parameters["eta_lorenz"] * (Th / (Th - Ts))))
            J2 = np.abs(COP - Qh / (Qh - Qs))
            J = J1 + J2
            return J

        def carnot_model(x, Th_out, Th_in, Ts_in, mh, ms):
            """Residual function for the Carnot-efficiency model, solving for
            (COP, Ts_out) given a fixed target Th_out.

            Combines two residuals: J1 enforces the Carnot COP equation
            COP = eta_carnot * (Th / (Th - Ts)), where Th = Th_out and
            Ts = Ts_in are treated as constant condenser/evaporator
            temperatures (see module reference for the Carnot cycle);
            J2 enforces the energy balance COP = Qh / (Qh - Qs).
            """
            COP = x[0]
            Ts_out = x[1]

            Qh = self.parameters["Cp_h"] * (Th_out - Th_in) * mh
            Qs = self.parameters["Cp_s"] * (Ts_in - Ts_out) * ms

            Th = Th_out
            Ts = Ts_in

            J1 = np.abs(COP - (self.parameters["eta_carnot"] * (Th / (Th - Ts))))
            J2 = np.abs(COP - Qh / (Qh - Qs))

            J = J1 + J2

            return J

        def carnot_model2(x, Ts_out, Th_in, Ts_in, mh, ms):
            """Residual function for the Carnot-efficiency model, solving for
            (COP, Th_out) given a fixed minimum source outlet temperature
            Ts_out (used when the unconstrained solution violates
            Ts_in_minimum). See `carnot_model` for the underlying equations.
            """
            COP = x[0]
            Th_out = x[1]

            Qh = self.parameters["Cp_h"] * (Th_out - Th_in) * mh
            Qs = self.parameters["Cp_s"] * (Ts_in - Ts_out) * ms

            Th = Th_out
            Ts = Ts_in

            J1 = np.abs(COP - (self.parameters["eta_carnot"] * (Th / (Th - Ts))))
            J2 = np.abs(COP - Qh / (Qh - Qs))

            J = J1 + J2

            return J

        x0 = [self.parameters["COP_0"], Ts_in - 10]
        if self.parameters["mode"] == "carnot":
            result = minimize(
                carnot_model, x0, args=(Th_out, Th_in, Ts_in, mh, ms), method="Nelder-Mead"
            )
        else:
            result = minimize(
                lorenz_model, x0, args=(Th_out, Th_in, Ts_in, mh, ms), method="Nelder-Mead"
            )

        COP = result.x[0]
        Ts_out = result.x[1]

        print(Ts_out)

        if Ts_out < self.parameters["Ts_in_minimum"] + 273.15:
            x0 = [self.parameters["COP_0"], Th_out]
            if self.parameters["mode"] == "carnot":
                result = minimize(
                    carnot_model2,
                    x0,
                    args=(self.parameters["Ts_in_minimum"] + 273.15, Th_in, Ts_in, mh, ms),
                    method="Nelder-Mead",
                )
            else:
                result = minimize(
                    lorenz_model2,
                    x0,
                    args=(self.parameters["Ts_in_minimum"] + 273.15, Th_in, Ts_in, mh, ms),
                    method="Nelder-Mead",
                )

            COP = result.x[0]
            Th_out = result.x[1]
            Ts_out = self.parameters["Ts_in_minimum"] + 273.15

        thermal_production = self.parameters["Cp_h"] * (Th_out - Th_in) * mh
        electrical_consumption = thermal_production / COP

        return COP, Th_out, Ts_out, thermal_production, electrical_consumption

    def get_output(self):
        """Get output of the model.

        Returns
        -------
        dict
            Output dict with keys "COP", "Th_out" (°C), "Ts_out" (°C),
            "Thermal_production" (W) and "electrical_consumption" (W),
            as populated by `calculate_output`.
        """
        return self.output


if __name__ == "__main__":
    # Example usage
    heatpump = HeatpumpBasic()
    heatpump.update_parameters(
        {
            "mode": "carnot",
            "eta_carnot": 0.5,
            "eta_lorenz": 0.5,
            "COP_0": 4.0,
            "Cp_h": 4181,  # J/kg.K
            "Cp_s": 4181,  # J/kg.K
            "rho_h": 1000,  # kg/m3
            "rho_s": 1000,  # kg/m3
            "Th_out_target": 80,  # °C
            "Ts_in_minimum": 5,  # °C
        }
    )

    u = {"Th_in": 30, "Ts_in": 40, "qh": 10.0, "qs": 20.0}  # °C  # °C  # m3/h  # m3/h

    heatpump.calculate_output(u, None)
    output = heatpump.get_output()
    print(output)
