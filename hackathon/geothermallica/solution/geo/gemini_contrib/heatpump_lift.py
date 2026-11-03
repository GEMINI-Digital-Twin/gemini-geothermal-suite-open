"""Heat pump lifting district water to a target on brine from the exchanger (HeatpumpBasic, Lorenz).

Why: a brief may cap brine cooling (40 K here), so the evaporator can only take brine down to the
wellhead temperature minus the cap. HeatpumpBasic already has a source floor (Ts_in_minimum): when
the network duty would cool the brine below it, it fixes the brine at the floor and lets the
delivered temperature drop. HeatPumpLift sets that floor from the input each call, works in plant
units (C, m3/h, MW) and reports when the floor binds. In that floor branch the Nelder-Mead search of
HeatpumpBasic lands on a second, unphysical root (COP about 1, water out about 800 C, measured
2 Nov 2026), so HeatPumpLift re-solves it as a one-variable root between water-in and the target
(brentq), where the root is bracketed. COP = eta_lorenz T_h / (T_h - T_s) with log-mean temperatures
of the sink and source glides (Ommen et al. 2015, Int. J. Refrig. 55, 168-182,
DOI 10.1016/j.ijrefrig.2015.02.012; Arpagaus et al. 2018, Energy 152, 985-1010,
DOI 10.1016/j.energy.2018.03.166).

Defaults: eta_lorenz 0.5, brine rho 1030 kg/m3 and cp 4000 J/kg/K, network water rho 1000 kg/m3 and
cp 4000 J/kg/K, target 100 C; all assumptions a plant model may overwrite through update_parameters.
"""

import numpy as np
from scipy.optimize import brentq

from gemini_model.heatpump.heatpump_basic import HeatpumpBasic


def _tlm(a_k, b_k):
    """Log-mean of two absolute temperatures (K)."""
    return (a_k - b_k) / np.log(a_k / b_k)


class HeatPumpLift(HeatpumpBasic):
    """HeatpumpBasic in Lorenz mode with a brine floor set per call and a bracketed floor branch.

    Inputs (u): T_brine_in_C, brine_flow_m3h, T_brine_floor_C, T_water_in_C, water_flow_m3h.
    Outputs added to HeatpumpBasic's: Q_th_MW, P_el_MW, Q_brine_MW, T_brine_out_C, T_water_out_C,
    floor_binds.
    """

    def __init__(self):
        """Initialize with Lorenz mode, eta 0.5, cp 4000 J/kg/K on both sides, target 100 C."""
        super().__init__()
        self.parameters.update(
            {
                "mode": "lorenz",
                "eta_lorenz": 0.5,
                "Cp_h": 4000.0,
                "Cp_s": 4000.0,
                "rho_h": 1000.0,
                "rho_s": 1030.0,
                "Th_out_target": 100.0,
            }
        )

    def _calculate(self, Th_out, Th_in, Ts_in, mh, ms):
        """Return the HeatpumpBasic solution, except in the floor branch, re-solved by brentq."""
        result = super()._calculate(Th_out, Th_in, Ts_in, mh, ms)
        Ts_floor = self.parameters["Ts_in_minimum"] + 273.15
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
        y["floor_binds"] = abs(y["Ts_out"] - u["T_brine_floor_C"]) < 1e-9


def register():
    """Add the heat pumps to GEMINI's component registry so create_component("heatpump_lift") works."""
    from gemini_simulator.registry import COMPONENT_REGISTRY

    COMPONENT_REGISTRY["heatpump"] = HeatpumpBasic
    COMPONENT_REGISTRY["heatpump_lift"] = HeatPumpLift
