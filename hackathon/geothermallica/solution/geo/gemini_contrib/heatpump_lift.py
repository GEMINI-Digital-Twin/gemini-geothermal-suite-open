"""GEMINI's HeatpumpBasic in Lorenz mode, with a lowest brine outlet temperature (floor) set per call and inputs in plant units.

COP (coefficient of performance, heat out per electricity in) = eta T_h / (T_h - T_s) on log-mean temperatures,
Ommen et al. 2015, DOI 10.1016/j.ijrefrig.2015.02.012. When the floor binds the outlet is solved by bracketing (brentq).
calculate_output() fills the GEMINI outputs plus Q_th_MW, P_el_MW, Q_brine_MW, T_brine_out_C, T_water_out_C and floor_binds.
"""

import numpy as np
from scipy.optimize import brentq

from gemini_model.heatpump.heatpump_basic import HeatpumpBasic


def _tlm(a_k, b_k):
    """Log-mean of two absolute temperatures (K)."""
    return (a_k - b_k) / np.log(a_k / b_k)


class HeatPumpLift(HeatpumpBasic):
    """Heat pump taking T_brine_in_C, brine_flow_m3h, T_brine_floor_C, T_water_in_C, water_flow_m3h; adds MW and C outputs."""

    def __init__(self):
        """Lorenz mode, efficiency 0.5, heat capacity 4 000 J/kg/K both sides, water 1 000 and brine 1 030 kg/m3, target 100 C."""
        super().__init__()
        self.parameters.update(
            {
                "mode": "lorenz",
                "eta_lorenz": 0.5,   # Lorenz efficiency; International Energy Agency heat-pump Annex 58 gives 0.35-0.59
                "Cp_h": 4000.0,
                "Cp_s": 4000.0,
                "rho_h": 1000.0,
                "rho_s": 1030.0,   # brine density from the challenge brief
                "Th_out_target": 100.0,   # district-heating supply, C, from the challenge brief
            }
        )

    def _calculate(self, Th_out, Th_in, Ts_in, mh, ms):
        """HeatpumpBasic's (COP, T out, T brine out, heat, power); in the floor branch, where its Nelder-Mead finds a COP ~1 root, brentq."""
        Ts_floor = self.parameters["Ts_in_minimum"] + 273.15
        # brine at or below the floor: nothing to take, so no heat, no power, water passes through
        if Ts_in <= Ts_floor:
            return float("nan"), Th_in, Ts_in, 0.0, 0.0
        result = super()._calculate(Th_out, Th_in, Ts_in, mh, ms)
        if abs(result[2] - Ts_floor) >= 1e-9:
            return result
        p = self.parameters
        q_s = p["Cp_s"] * ms * (Ts_in - Ts_floor)
        t_s = _tlm(Ts_in, Ts_floor)

        def cop(th):
            t_h = _tlm(th, Th_in)
            return p["eta_lorenz"] * t_h / (t_h - t_s)

        def gap(th):
            # sink duty minus what the source and the compressor can give at that outlet temperature
            return p["Cp_h"] * mh * (th - Th_in) - q_s * cop(th) / (cop(th) - 1)

        th = brentq(gap, Th_in + 1e-6, Th_out)
        q_h = p["Cp_h"] * mh * (th - Th_in)
        return cop(th), th, Ts_floor, q_h, q_h / cop(th)

    def calculate_output(self, u, x=None):
        """Run HeatpumpBasic on plant-unit inputs u and add the MW, C and floor_binds outputs."""
        self.parameters["mode"] = "lorenz"
        self.parameters["Ts_in_minimum"] = u["T_brine_floor_C"]
        super().calculate_output(
            {
                "Th_in": u["T_water_in_C"],
                "Ts_in": u["T_brine_in_C"],
                "hot_flow_rate": u["water_flow_m3h"] / 3600.0,
                "source_flow_rate": u["brine_flow_m3h"] / 3600.0,
            },
            x,
        )
        y = self.output
        m_s = u["brine_flow_m3h"] / 3600.0 * self.parameters["rho_s"]
        y["Q_th_MW"] = y["Thermal_production"] / 1e6
        y["P_el_MW"] = y["electrical_consumption"] / 1e6
        y["Q_brine_MW"] = m_s * self.parameters["Cp_s"] * (u["T_brine_in_C"] - y["Ts_out"]) / 1e6
        y["T_brine_out_C"] = y["Ts_out"]
        y["T_water_out_C"] = y["Th_out"]
        y["floor_binds"] = y["Ts_out"] <= u["T_brine_floor_C"] + 1e-9


def register():
    """Add the heat pumps to GEMINI's component registry so create_component("heatpump_lift") works."""
    from gemini_simulator.registry import COMPONENT_REGISTRY

    COMPONENT_REGISTRY["heatpump"] = HeatpumpBasic
    COMPONENT_REGISTRY["heatpump_lift"] = HeatPumpLift
