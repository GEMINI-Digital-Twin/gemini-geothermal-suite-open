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
from scipy.optimize import brentq

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

    def calculate_output(self, u, x=None):
        """Calculate output based on input u and state x.

        Converts inputs (temperatures in degC, volumetric flows in m3/s) to
        SI units (K, kg/s), solves for the operating point via `_calculate`,
        and stores the results (COP, outlet temperatures, thermal production
        and electrical consumption) in `self.output`.

        Parameters
        ----------
        u: dict
            Model inputs: "Th_in" (degC), "Ts_in" (degC), "hot_flow_rate"
            (m3/s, hot/sink side), "source_flow_rate" (m3/s, source side).
            Optional "hot_pressure_in"/"source_pressure_in" (bar) are echoed
            back unchanged as "hot_pressure_out"/"source_pressure_out" (this
            model does not compute a pressure drop), so a downstream
            pressure chain is not broken when connecting through a heat pump.
        x: state
            Model state (unused, model is static).
        """
        # get input
        Th_out = self.parameters["Th_out_target"] + 273.15  # Convert to Kelvin
        Th_in = u["Th_in"] + 273.15  # Convert to Kelvin
        Ts_in = u["Ts_in"] + 273.15  # Convert to Kelvin
        hot_flow_rate = u["hot_flow_rate"]  # m3/s
        source_flow_rate = u["source_flow_rate"]  # m3/s
        mh = hot_flow_rate * self.parameters["rho_h"]  # kg/s
        ms = source_flow_rate * self.parameters["rho_s"]  # kg/s

        result = self._calculate(Th_out, Th_in, Ts_in, mh, ms)

        self.output["COP"] = result[0]
        self.output["Th_out"] = result[1] - 273.15  # Convert back to Celsius
        self.output["Ts_out"] = result[2] - 273.15  # Convert back to Celsius
        self.output["Thermal_production"] = result[3]
        self.output["electrical_consumption"] = result[4]
        self.output["hot_flow_rate"] = hot_flow_rate
        self.output["hot_flow_rate_m3h"] = hot_flow_rate * 3600.0
        self.output["source_flow_rate"] = source_flow_rate
        self.output["source_flow_rate_m3h"] = source_flow_rate * 3600.0
        self.output["power_th"] = result[3]
        self.output["power_el"] = result[4]
        self.output["emission"] = 0.0

        if "hot_pressure_in" in u:
            self.output["hot_pressure_in"] = u["hot_pressure_in"]
            self.output["hot_pressure_out"] = u["hot_pressure_in"]
        if "source_pressure_in" in u:
            self.output["source_pressure_in"] = u["source_pressure_in"]
            self.output["source_pressure_out"] = u["source_pressure_in"]

    def _calculate(self, Th_out, Th_in, Ts_in, mh, ms):
        """Solve for the heat pump operating point.

        (COP, outlet temperatures, thermal production and electrical
        consumption).

        Jointly satisfies the thermodynamic efficiency equation (Carnot or
        Lorenz, selected via `self.parameters['mode']`) and the energy
        balance (Qh = Qs + electrical work, i.e. COP = Qh/(Qh-Qs)).

        With the sink outlet fixed at its target, Qh is known and the only
        unknown is the source outlet temperature: a 1-D root of
        COP_balance(Ts_out) - COP_model(Ts_out), bracketed between Ts_in
        (Qs -> 0, COP_balance -> 1) and the temperature at which Qs -> Qh
        (COP_balance -> +inf), solved with `scipy.optimize.brentq`.

        If the resulting source outlet temperature `Ts_out` drops below
        `Ts_in_minimum`, `Ts_out` is pinned at that minimum and the sink
        outlet temperature is solved instead (see `_solve_source_limited`).

        GeoHackathon 2026 change: the previous unbracketed Nelder-Mead on
        |residual| sums could converge to non-physical points (e.g. Ts_out
        below the minimum for a 55 C source, then Th_out = 140 C and
        COP ~ 1e8). The bracketed formulation has a unique physical root and
        is ~20x faster.

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
        cp_h, cp_s = self.parameters["Cp_h"], self.parameters["Cp_s"]
        Qh = cp_h * mh * (Th_out - Th_in)
        if Qh <= 0 or ms <= 0:
            return self.parameters["COP_0"], Th_in, Ts_in, 0.0, 0.0

        def g(ts_out):
            qs = cp_s * ms * (Ts_in - ts_out)
            return Qh / (Qh - qs) - self._cop_model(Th_in, Th_out, Ts_in, ts_out)

        ts_lo = Ts_in - Qh / (cp_s * ms) * (1 - 1e-9)  # Qs -> Qh
        ts_hi = Ts_in - 1e-9  # Qs -> 0
        if g(ts_hi) >= 0:  # thermodynamic COP <= 1: no useful operating point
            return 1.0, Th_in, Ts_in, 0.0, 0.0
        Ts_out = brentq(g, max(ts_lo, 1.0), ts_hi, xtol=1e-7)
        COP = Qh / (Qh - cp_s * ms * (Ts_in - Ts_out))

        if Ts_out < self.parameters["Ts_in_minimum"] + 273.15:
            Ts_out = self.parameters["Ts_in_minimum"] + 273.15
            COP, Th_out = self._solve_source_limited(Th_out, Th_in, Ts_in, Ts_out, mh, ms)

        thermal_production = cp_h * (Th_out - Th_in) * mh
        electrical_consumption = thermal_production / COP

        return COP, Th_out, Ts_out, thermal_production, electrical_consumption

    @staticmethod
    def _log_mean(t1, t2):
        """Logarithmic mean temperature, continuous at t1 == t2."""
        if abs(t1 - t2) < 1e-9:
            return 0.5 * (t1 + t2)
        return (t1 - t2) / np.log(t1 / t2)

    def _cop_model(self, Th_in, Th_out, Ts_in, Ts_out):
        """Thermodynamic COP (Carnot or Lorenz) for the given terminal temperatures [K]."""
        if self.parameters["mode"] == "carnot":
            Th, Ts = Th_out, Ts_in
            return self.parameters["eta_carnot"] * Th / (Th - Ts)
        Th = self._log_mean(Th_in, Th_out)
        Ts = self._log_mean(Ts_in, Ts_out)
        return self.parameters["eta_lorenz"] * Th / (Th - Ts)

    def _solve_source_limited(self, Th_out_target, Th_in, Ts_in, Ts_out, mh, ms):
        """Operating point when the source outlet is pinned at its minimum.

        The source heat Qs is then fixed, and the sink outlet temperature is
        the root of COP_balance(Th_out) = COP_model(Th_out) with
        COP_balance = Qh / (Qh - Qs), Qh = cp_h * mh * (Th_out - Th_in).
        Solved with a bracketed root finder on Th_out in
        (Th_in + Qs / (cp_h * mh), Th_out_target]; COP_balance -> +inf at the
        lower end, so the root is unique and physical. (GeoHackathon 2026 fix:
        the previous unbracketed Nelder-Mead on (COP, Th_out) could converge to
        a spurious COP -> 1, Th_out -> very large solution, e.g. 837 C.)
        Returns (COP, Th_out); if even the target is reachable, Th_out = target.
        """
        cp_h = self.parameters["Cp_h"]
        Qs = self.parameters["Cp_s"] * (Ts_in - Ts_out) * ms
        if Qs <= 0 or mh <= 0:
            return self.parameters["COP_0"], Th_in
        th_lo = Th_in + Qs / (cp_h * mh) + 1e-6

        def g(th_out):
            qh = cp_h * mh * (th_out - Th_in)
            return qh / (qh - Qs) - self._cop_model(Th_in, th_out, Ts_in, Ts_out)

        if th_lo >= Th_out_target or g(Th_out_target) >= 0:
            # source not limiting at the target: deliver the target temperature
            th = Th_out_target
            qh = cp_h * mh * (th - Th_in)
            return qh / max(qh - Qs, 1e-9), th
        th = brentq(g, th_lo, Th_out_target, xtol=1e-6)
        qh = cp_h * mh * (th - Th_in)
        return qh / (qh - Qs), th

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
