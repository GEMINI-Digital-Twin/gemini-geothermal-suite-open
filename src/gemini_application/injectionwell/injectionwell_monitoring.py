"""Injection well monitoring with Hall integral analysis and skin factor evaluation."""

import traceback
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytz
from matplotlib import pyplot as plt

from gemini_application.application_abstract import ApplicationAbstract
from gemini_model.fluid.pvt_water_stp import PVTConstantSTP
from gemini_model.reservoir.reservoir_pressuredrop import bottomhole_skin_dp
from gemini_model.well.pressure_drop import DPDT

tzobject = pytz.timezone("Europe/Amsterdam")


class InjectionWellMonitoring(ApplicationAbstract):
    """Class for application injection well II (Injectivity Index) & BHP calculations.

    This class also prepares the plot for skic factor effect analysis.
    """

    def __init__(self):
        """Initialize injection well monitoring."""
        super().__init__()

        self.bottomhole_skin_dp = bottomhole_skin_dp()
        self.DPF = DPDT()
        self.DPF.PVT = PVTConstantSTP()

    def init_parameters(self, parameters):
        """Initialize model parameters."""
        well_unit = self.unit

        res_param = dict()
        res_param["reservoir_pressure"] = parameters["reservoir_pressure"] * 1e5  # bar to Pa
        res_param["reservoir_radius"] = parameters["reservoir_radius"]  # m
        res_param["reservoir_top"] = parameters["reservoir_top"]  # m
        res_param["reservoir_permeability"] = (
            parameters["reservoir_permeability"] * 9.869233e-16
        )  # mD to m2
        res_param["reservoir_thickness"] = parameters["reservoir_thickness"]

        self.bottomhole_skin_dp.update_parameters(res_param)

        pvt_param = dict()
        pvt_param["RHOL"] = parameters["liquid_density"]
        pvt_param["VISL"] = parameters["liquid_viscosity"]

        self.DPF.PVT.update_parameters(pvt_param)

        well_param = dict()
        well_traj = well_unit.parameters["property"]["injectionwell_trajectory_table"][-1]
        length = []
        diameter = []
        angle = []
        roughness = []
        for ii in range(1, len(well_traj)):
            MD = well_traj[ii]["MD"] - well_traj[ii - 1]["MD"]
            TVD = well_traj[ii]["TVD"] - well_traj[ii - 1]["TVD"]

            roughness.append(well_traj[ii]["roughness"])
            length.append(MD)
            diameter.append(well_traj[ii]["ID"])
            angle.append((np.round(90 - np.arccos(TVD / MD) * 180 / np.pi, 2)) * np.pi / 180)

        well_param["diameter"] = np.array(diameter)  # well diameter in [m]
        well_param["length"] = np.array(length)  # well length in [m]
        well_param["angle"] = np.array(angle)  # well angle in [rad]
        well_param["roughness"] = roughness  # roughness of cells [m]
        well_param["friction_correlation"] = well_unit.parameters["property"][
            "injectionwell_friction_correlation"
        ][-1]
        well_param["friction_correlation_2p"] = well_unit.parameters["property"][
            "injectionwell_friction_correlation_2p"
        ][-1]
        well_param["correction_factors"] = well_unit.parameters["property"][
            "injectionwell_friction_correction_factors"
        ][-1]
        well_param["injectionwell_soil_temperature"] = well_unit.parameters["property"][
            "injectionwell_soil_temperature"
        ][
            -1
        ]  # soil temperature in [C]

        self.DPF.update_parameters(well_param)

    def calculate(self):
        """Calculate hall integral."""
        self.get_data()
        self.calculate_hall_integral()
        self.calculate_skin_lines()

    def get_data(self):
        """Get injection well monitoring data."""
        start_time = datetime.strptime(self.inputs["start_time"], "%Y-%m-%d %H:%M:%S")
        start_time = tzobject.localize(start_time)
        start_time = start_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        end_time = datetime.strptime(self.inputs["end_time"], "%Y-%m-%d %H:%M:%S")
        end_time = tzobject.localize(end_time)
        end_time = end_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        timestep = 3600  # hardcoded 1 hour since flowrate is in m3/h

        result, time = self.plant.database.read_internal_database(
            self.unit.plant.name,
            self.unit.name,
            "injectionwell_flow.measured",
            start_time,
            end_time,
            timestep,
        )
        self.inputs["flow"] = np.array(result)  # m3/hr
        self.inputs["time"] = np.array(time)

        result, time = self.plant.database.read_internal_database(
            self.unit.plant.name,
            self.unit.name,
            "injectionwell_wellhead_pressure.measured",
            start_time,
            end_time,
            timestep,
        )
        self.inputs["wellhead_pressure"] = np.array(result)  # bar

        result, time = self.plant.database.read_internal_database(
            self.unit.plant.name,
            self.unit.name,
            "injectionwell_bottomhole_pressure.calculated",
            start_time,
            end_time,
            timestep,
        )
        self.inputs["BHP"] = np.array(result)  # bar

    def calculate_hall_integral(self):
        """Calculate hall integral and its derivative."""
        try:
            cumulative_production = self.inputs["flow"].cumsum()  # m3
            hall_integral = (
                self.inputs["BHP"] - self.inputs["reservoir_pressure"]
            ).cumsum()  # bar.hr
            cumulative_production = np.where(
                cumulative_production <= 0, np.nan, cumulative_production
            )
            hall_derivative_numerical = np.gradient(
                hall_integral, np.log(cumulative_production)
            )  # bar.hr/m3
        except Exception:
            print("ERROR in " + self.__class__.__name__ + " : " + traceback.format_exc())
            cumulative_production = None
            hall_integral = None
            hall_derivative_numerical = None

        self.outputs["cumulative_flow"] = cumulative_production  # m3
        self.outputs["hall_integral"] = hall_integral  # bar.hr
        self.outputs["hall_derivative_numerical"] = hall_derivative_numerical  # bar.hr/m3

    def calculate_skin_lines(self):
        """Calculate skin factor lines."""
        try:
            # flow in m3/hr to m3/s
            flow_array = np.linspace(
                self.inputs["min_flow_plot"] / 3600,
                self.inputs["max_flow_plot"] / 3600,
                self.inputs["no_interval_flow_plot"],
            )

            skin_array = np.linspace(
                self.inputs["min_skin_plot"],
                self.inputs["max_skin_plot"],
                self.inputs["no_interval_skin_plot"],
            )

            u_well = dict()
            u_res = dict()
            x = []
            P_inj = []

            u_well["pressure"] = 0.1 * 1e5  # Pa, currently hardcoded due to using fix PVT
            u_well["temperature"] = 65 + 273.15  # C to K, currently hardcoded due to using fix PVT
            u_well["direction"] = "down"
            u_well["temperature_ambient"] = (
                self.unit.parameters["property"]["injectionwell_soil_temperature"][-1] + 273.15
            )  # C to K

            _, density, _, _, viscosity, _, _, _, _, _ = self.DPF.PVT.get_pvt(
                u_well["pressure"], u_well["temperature"]
            )
            for skin in skin_array:
                P_inj_skin = []
                for flow in flow_array:
                    u_well["flowrate"] = flow  # m3/s

                    self.DPF.calculate_output(u_well, x)

                    y = self.DPF.get_output()

                    deltaP_fric = y["pressuredrop_fric_output"] / 1e5  # Pa to bar

                    u_res["flow"] = flow  # m3/s
                    u_res["viscosity"] = viscosity  # Pa.s
                    u_res["density"] = density  # kg/m3
                    u_res["well_radius"] = self.inputs["wellbore_radius"]  # m
                    u_res["skin_factor"] = skin

                    self.bottomhole_skin_dp.calculate_output(u_res, x)

                    y = self.bottomhole_skin_dp.get_output()

                    BHP = y["reservoir_dp"] / 1e5  # Pa to bar

                    deltaP_HH = y["Hydrostatic_dp"] / 1e5  # Pa to bar

                    result = BHP - deltaP_HH + deltaP_fric  # bar

                    if result < 0:
                        result = 0

                    P_inj_skin.append(result)
                P_inj.append(P_inj_skin)

            self.outputs["injection_pressure"] = P_inj  # bar
            self.outputs["max_cal_P_inj"] = np.max(P_inj)
            self.inputs["flow_array"] = flow_array * 3600
            self.inputs["skin_array"] = skin_array
        except Exception:
            print("ERROR in " + self.__class__.__name__ + " : " + traceback.format_exc())

    def plot(self):
        """Calculate all pressure from reservoir to topside."""
        x = self.outputs["cumulative_flow"]
        y0 = self.outputs["hall_integral"]
        y1 = self.outputs["hall_derivative_numerical"]

        plt.figure()
        plt.plot(x, y0, label="hall_integral")
        plt.plot(x, y1, label="hall_derivative_numerical")
        plt.legend()
        plt.show()

        plt.figure()
        plt.plot(x, y0, label="hall_integral")
        plt.plot(x, y1, label="hall_derivative_numerical")
        plt.xscale("log")
        plt.yscale("log")
        plt.legend()
        plt.show()

    def plot_skin(self):
        """Calculate all skin factor effect."""

        def format_func(value, tick_number):
            date = pd.to_datetime(value)
            return date.strftime("%d %B %Y")

        realTime_time = self.inputs["time"]
        realTime_time = pd.to_datetime(realTime_time)
        realTime_flow = self.inputs["flow"]
        realTime_wellhead_pressure = self.inputs["wellhead_pressure"]
        max_flow_rate = self.inputs["max_flow_rate"]
        max_pressure = self.inputs["max_pressure"]
        flow_array = np.linspace(
            self.inputs["min_flow_plot"],
            self.inputs["max_flow_plot"],
            self.inputs["no_interval_flow_plot"],
        )
        skin_array = np.linspace(
            self.inputs["min_skin_plot"],
            self.inputs["max_skin_plot"],
            self.inputs["no_interval_skin_plot"],
        )

        plt.figure()

        scatter = plt.scatter(
            realTime_flow, realTime_wellhead_pressure, c=realTime_time.astype("int64"), cmap="jet"
        )
        colorbar = plt.colorbar(scatter)
        colorbar.ax.yaxis.set_major_formatter(plt.FuncFormatter(format_func))

        for idx, skin in enumerate(skin_array):
            plt.plot(
                flow_array,
                self.outputs["injection_pressure"][idx],
                label=f"Skin = {skin}",
                color="dimgray",
                linestyle="--",
            )
            plt.text(
                flow_array[-1],
                self.outputs["injection_pressure"][idx][-1],
                f"skin = {skin:.0f}",
                color="black",
                fontsize=8,
                verticalalignment="bottom",
                horizontalalignment="left",
            )

        plt.axvline(x=max_flow_rate, color="r", linestyle="--")
        plt.axhline(y=max_pressure, color="r", linestyle="-.")

        plt.text(
            max_flow_rate - 10,
            self.outputs["max_cal_P_inj"] - 22,
            f"Max Q = {max_flow_rate:.0f} m3/h",
            color="red",
            fontsize=8,
            verticalalignment="bottom",
            horizontalalignment="left",
            rotation="vertical",
        )
        plt.text(
            self.inputs["min_flow_plot"] + 2,
            max_pressure + 2,
            f"Max P = {max_pressure:.0f} bar",
            color="red",
            fontsize=8,
            verticalalignment="bottom",
            horizontalalignment="left",
        )

        plt.xlim((self.inputs["min_flow_plot"], self.inputs["max_flow_plot"] + 50))
        plt.ylim((0, self.outputs["max_cal_P_inj"] + 5))
        plt.title("Q-P plot incl. skin lines")
        plt.xlabel("Flow Rate [m3/h]")
        plt.ylabel("Injection pressure [bar]")
        plt.grid()
        plt.tight_layout()
        plt.show()
