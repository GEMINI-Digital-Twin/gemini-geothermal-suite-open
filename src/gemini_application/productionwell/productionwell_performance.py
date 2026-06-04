"""Production well performance analysis with IPR, VLP, and ESP calculations."""

import numpy as np
from matplotlib import pyplot as plt

from gemini_application.application_abstract import ApplicationAbstract
from gemini_model.fluid.pvt_water_stp import PVTConstantSTP
from gemini_model.pump.esp import ESP
from gemini_model.reservoir.inflow_performance import IPR
from gemini_model.well.pressure_drop import DPDT


class ProductionWellPerformance(ApplicationAbstract):
    """Class for application production well IPR/VLP calculation."""

    def __init__(self):
        """Initialize production well performance."""
        super().__init__()

        self.IPR = IPR()
        self.VLP1 = DPDT()
        self.VLP2 = DPDT()
        self.ESP = ESP()

    def init_parameters(self, parameters):
        """Initialize model parameters."""
        well_unit = self.unit

        res_param = dict()

        res_param["reservoir_pressure"] = parameters["reservoir_pressure"]
        res_param["productivity_index"] = parameters["productivity_index"]
        res_param["type"] = "production_reservoir"

        self.IPR.update_parameters(res_param)

        esp_param = dict()
        esp_param["no_stages"] = parameters["esp_no_stage"]
        esp_param["pump_name"] = parameters["esp_type"]
        esp_param["head_coeff"] = np.asarray(
            parameters["esp_head_coeff"].split(";"), dtype=np.float32
        )
        esp_param["power_coeff"] = np.asarray(
            parameters["esp_power_coeff"].split(";"), dtype=np.float32
        )
        esp_param["min_flow"] = parameters["esp_min_flow"]
        esp_param["max_flow"] = parameters["esp_max_flow"]

        self.ESP.update_parameters(esp_param)

        well_param = dict()

        well_traj = well_unit.parameters["property"]["productionwell_trajectory_table"][-1]
        well_param["diameter"] = np.array([parameters["esp_tubing"]])  # well diameter in [m]
        well_param["length"] = np.array([parameters["esp_depth"]])  # well depth in [m]
        well_param["angle"] = np.array([90 * np.pi / 180])  # well angle in [degree]
        well_param["roughness"] = np.array([well_traj[1]["roughness"]])  # roughness of cells [m]
        well_param["friction_correlation"] = parameters["friction_correlation"]
        well_param["friction_correlation_2p"] = "BeggsBrill"
        well_param["correction_factors"] = [1, 0]

        self.VLP1.update_parameters(well_param)

        pvt_param = dict()
        pvt_param["RHOL"] = parameters["liquid_density"]
        pvt_param["VISL"] = parameters["liquid_viscosity"]

        self.VLP1.PVT = PVTConstantSTP()
        self.VLP1.PVT.update_parameters(pvt_param)

        well_param = dict()

        length = []
        diameter = []
        angle = []
        roughness = []
        for ii in range(1, len(well_traj)):
            if well_traj[ii - 1]["MD"] >= parameters["esp_depth"]:
                MD = well_traj[ii]["MD"] - well_traj[ii - 1]["MD"]
                TVD = well_traj[ii]["TVD"] - well_traj[ii - 1]["TVD"]

                length.append(MD)
                diameter.append(well_traj[ii]["ID"])
                angle.append(np.round(90 - np.arccos(TVD / MD) * 180 / np.pi, 2) * np.pi / 180)
                roughness.append(well_traj[ii]["roughness"])

        well_param["diameter"] = np.array(diameter)  # well diameter in [m]
        well_param["length"] = np.array(length)  # well depth in [m]
        well_param["angle"] = np.array(angle)  # well angle in [degree]
        well_param["roughness"] = roughness  # roughness of cells [m]
        well_param["friction_correlation"] = parameters["friction_correlation"]
        well_param["friction_correlation_2p"] = "BeggsBrill"
        well_param["correction_factors"] = [1, 0]

        self.VLP2.update_parameters(well_param)
        self.VLP2.PVT = PVTConstantSTP()
        self.VLP2.PVT.update_parameters(pvt_param)

    def calculate(self):
        """Calculate IPR, VLP, ESP."""
        flow_array = np.linspace(
            self.ESP.parameters["min_flow"] * 0.8, self.ESP.parameters["max_flow"] * 1.1, 100
        )
        self.inputs["flow"] = flow_array

        self.calculate_dp_top_esp()
        self.calculate_esp()
        self.calculate_dp_esp_bottom()
        self.calculate_pbh_res()

    def calculate_dp_top_esp(self):
        """Calculate pressure drop from wellhead to ESP."""
        try:
            u = dict()
            x = []

            discharge_pressure = []
            discharge_temperature = []
            for flow in self.inputs["flow"]:
                u["pressure"] = self.inputs["wellhead_pressure"] * 1e5  # bar to Pa
                u["temperature"] = self.inputs["wellhead_temperature"] + 273.15  # C to K
                u["flowrate"] = flow / 3600  # m3/hr to m3/s
                u["temperature_ambient"] = self.inputs["soil_temperature"] + 273.15  # C to K
                u["direction"] = "down"

                self.VLP1.calculate_output(u, x)

                # ASSERT
                y = self.VLP1.get_output()

                discharge_pressure.append(y["pressure_output"] / 1e5)  # Pa to bar
                discharge_temperature.append(y["temperature_output"] - 273.15)  # K to C
        except Exception as e:
            print("ERROR:" + repr(e))
            discharge_pressure = None
            discharge_temperature = None

        self.outputs["discharge_pressure"] = np.array(discharge_pressure)
        self.outputs["discharge_temperature"] = np.array(discharge_temperature)

    def calculate_dp_esp_bottom(self):
        """Calculate pressure drop from ESP to bottomhole."""
        try:
            self.outputs["intake_pressure"] = (
                self.outputs["discharge_pressure"] - self.outputs["pump_head"]
            )
            self.outputs["intake_temperature"] = self.outputs["discharge_temperature"]

            u = dict()
            x = []

            bottomhole_pressure = []
            bottomhole_temperature = []
            ii = 0
            for flow in self.inputs["flow"]:
                u["pressure"] = self.outputs["intake_pressure"][ii] * 1e5  # bar to Pa
                u["temperature"] = self.outputs["intake_temperature"][ii] + 273.15  # C to K
                u["flowrate"] = flow / 3600  # m3/hr to m3/s
                u["temperature_ambient"] = self.inputs["soil_temperature"] + 273.15  # C to K
                u["direction"] = "down"

                self.VLP2.calculate_output(u, x)

                # ASSERT
                y = self.VLP2.get_output()

                bottomhole_pressure.append(y["pressure_output"] / 1e5)  # Pa to bar
                bottomhole_temperature.append(y["temperature_output"] - 273.15)  # C to K

                ii = ii + 1

        except Exception as e:
            print("ERROR:" + repr(e))
            bottomhole_pressure = None
            bottomhole_temperature = None

        self.outputs["pbh_well"] = np.array(bottomhole_pressure)
        self.outputs["tbh_well"] = np.array(bottomhole_temperature)

    def calculate_esp(self):
        """Calculate ESP output."""
        try:
            u = dict()
            x = []

            pump_head = []
            pump_power = []
            pump_eff = []
            for flow in self.inputs["flow"]:
                u["pump_freq"] = self.inputs["esp_freq"]
                u["pump_flow"] = flow / 3600

                self.ESP.calculate_output(u, x)

                # ASSERT
                y = self.ESP.get_output()
                pump_head.append(y["pump_head"] / 1e5)
                pump_power.append(y["pump_power"])
                pump_eff.append(y["pump_eff"])

        except Exception as e:
            print("ERROR:" + repr(e))
            pump_head = None
            pump_power = None
            pump_eff = None

        self.outputs["pump_head"] = np.array(pump_head)
        self.outputs["pump_power"] = np.array(pump_power)
        self.outputs["pump_eff"] = np.array(pump_eff)

    def calculate_pbh_res(self):
        """Calculate bottomhole pressure from reservoir."""
        try:
            u = dict()
            x = []

            pbh_res = []
            p_res = []
            for flow in self.inputs["flow"]:
                u["flow"] = flow

                self.IPR.calculate_output(u, x)

                # ASSERT
                y = self.IPR.get_output()
                pbh_res.append(y["bottomhole_pressure"])
                p_res.append(self.IPR.parameters["reservoir_pressure"])

        except Exception as e:
            print("ERROR:" + repr(e))
            pbh_res = None
            p_res = None

        self.outputs["pbh_res"] = np.array(pbh_res)
        self.inputs["reservoir_pressure"] = np.array(p_res)

    def plot(self):
        """Calculate all pressure from reservoir to topside."""
        x = self.inputs["flow"]
        y0 = self.inputs["wellhead_pressure"] * np.ones(len(x))
        y1 = self.outputs["discharge_pressure"]
        y2 = self.outputs["intake_pressure"]
        y3 = self.outputs["pbh_well"]
        y4 = self.outputs["pbh_res"]
        y5 = self.inputs["reservoir_pressure"]

        plt.figure()
        plt.plot(x, y0, label="wellhead pressure")
        plt.plot(x, y1, label="discharge pressure")
        plt.plot(x, y2, label="intake pressure")
        plt.plot(x, y3, label="pbh well")
        plt.plot(x, y4, label="pbh res")
        plt.plot(x, y5, label="reservoir pressure")
        plt.legend()
        plt.show()

    def get_solution(self):
        """Get production well performance solution."""
        try:
            sol_pbh = np.sqrt(np.power(self.outputs["pbh_well"] - self.outputs["pbh_res"], 2))
            if np.amin(sol_pbh) > 3:
                raise Exception("Solution not found")

            index = np.where(sol_pbh == np.amin(sol_pbh))
            self.outputs["sol_flow"] = self.inputs["flow"][index]
            self.outputs["sol_pbh"] = self.outputs["pbh_well"][index]
            self.outputs["sol_esp_head"] = self.outputs["pump_head"][index]
            self.outputs["sol_esp_power"] = self.outputs["pump_power"][index]
            self.outputs["sol_esp_eff"] = self.outputs["pump_eff"][index]
            self.outputs["sol_intake_pressure"] = self.outputs["intake_pressure"][index]
            self.outputs["sol_discharge_pressure"] = self.outputs["discharge_pressure"][index]

        except Exception as e:
            print("ERROR:" + repr(e))

            self.outputs["sol_flow"] = None
            self.outputs["sol_flow"] = None
            self.outputs["sol_pbh"] = None
            self.outputs["sol_esp_head"] = None
            self.outputs["sol_esp_power"] = None
            self.outputs["sol_esp_eff"] = None
            self.outputs["sol_intake_pressure"] = None
            self.outputs["sol_discharge_pressure"] = None
