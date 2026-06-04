"""CO2 corrosion analysis application with caliper log processing and model optimization."""

import glob
import os
import re
from datetime import datetime, timezone

import lasio as ls
import numpy as np
import pandas as pd
import pytz
import ruptures as rpt

from gemini_application.application_abstract import ApplicationAbstract
from gemini_application.wims.model_optimization import OptCO2Corrosion
from gemini_model.corrosion.co2_corrosion_opt import CO2CorrosionOpt
from gemini_model.corrosion.correlation.co2_partial_pressure_model import CO2PartialPressureModel
from gemini_model.fluid.pvt_water_stp import PVTConstantSTP
from gemini_model.well.pressure_drop import DPDT

tzobject = pytz.timezone("Europe/Amsterdam")


class CO2CorrosionApplication(ApplicationAbstract):
    """Class for CO2 Corrosion application."""

    def __init__(self):
        """Initialize CO2 corrosion application."""
        super().__init__()
        self.VLP = DPDT()

        self.corrosion_models = []
        self.co2_models = []

    def _get_well_type(self):
        """Return 'productionwell' or 'injectionwell' from unit type or name."""
        try:
            ut = self.unit.parameters.get("type")
            if ut == "production_well":
                return "productionwell"
            if ut == "injection_well":
                return "injectionwell"
        except (KeyError, TypeError):
            pass
        if "production" in self.unit.name.lower():
            return "productionwell"
        if "injection" in self.unit.name.lower():
            return "injectionwell"
        return "productionwell"

    def _get_tally_from_well_parameters(self):
        """Get well tally from unit parameters (well parameter). Returns list of dicts or None."""
        well_type = self._get_well_type()
        key = f"{well_type}_tally_table"
        prop = self.unit.parameters.get("property") or {}
        table = prop.get(key)
        if table is not None and len(table) > 0:
            # table can be list per timestamp [[row,...], ...] or single list [row,...]
            first = table[0]
            if isinstance(first, list):
                if first:
                    return list(first)
            else:
                return list(table)
        if key in self.unit.parameters and self.unit.parameters[key]:
            tbl = self.unit.parameters[key]
            if isinstance(tbl, list) and tbl:
                first = tbl[0]
                if isinstance(first, list) and first:
                    return list(first)
                return list(tbl)
        return None

    def init_parameters(self, corrosion_model_name="DLD"):
        """Initialize models parameters. Tally from well parameter first, then tally folder."""
        well_unit = self.unit
        well_tally = self._get_tally_from_well_parameters()
        if not well_tally:
            project_data_folder = os.path.join(
                well_unit.plant.project_path, well_unit.plant.name + "/wims_data"
            )
            well_data_folder = os.path.join(project_data_folder, well_unit.name, "tally")
            well_tally_files = glob.glob(os.path.join(well_data_folder, "*.csv"))
            if well_tally_files:
                well_tally = pd.read_csv(well_tally_files[0]).to_dict("records")
            else:
                raise ValueError(
                    "No well tally found: set tally in Well Parameters (app builder) or upload a "
                    "tally file to wims_data/<well>/tally/"
                )
        self.inputs["well_tally"] = well_tally

        length = []
        diameter = []
        angle = []
        roughness = []

        for entry in well_tally:
            # Get values directly from the dictionary
            top_md = entry["TopMD"]
            bot_md = entry["BottomMD"]
            top_tvd = entry["TopTVD"]
            bot_tvd = entry["BottomTVD"]

            # Calculate MD and TVD
            MD = bot_md - top_md
            TVD = bot_tvd - top_tvd

            # Convert nominal inner diameter from inches to meters
            nominal_id_m = entry["ID"] * 0.0254

            # Append computed MD and diameter
            length.append(MD)
            diameter.append(nominal_id_m)

            # Calculate the inclination in radians if MD is positive
            if MD > 0:
                # Calculate the inclination in degrees first, round it, then convert to radians.
                incl_deg = np.round(90 - np.arccos(TVD / MD) * 180 / np.pi, 2)
                incl_rad = incl_deg * np.pi / 180
            else:
                incl_rad = 0.0
            angle.append(incl_rad)

            # Append roughness value
            roughness.append(entry["Roughness"])

        # Init PVT model;
        self.VLP.PVT = PVTConstantSTP()
        # Build well_param and update the VLP
        well_param = {
            "friction_correlation": "darcy_weisbach",
            "friction_correlation_2p": "darcy_weisbach",
            "diameter": np.array(diameter),
            "length": np.array(length),
            "angle": np.array(angle),
            "roughness": roughness,
        }
        self.VLP.update_parameters(well_param)

        # Create CO2PartialPressureModel for each "section"
        for _ in well_tally:
            self.co2_models.append(CO2PartialPressureModel())

        #  Initialize corrosion models for each joint
        # TODO: Add all parameters, so all models can be used! For now only, DLD is used.
        for joint in well_tally:
            joint_param = {
                "roughness": joint["Roughness"],
                "corrosion_model": corrosion_model_name,
                "diameter": self.inches_to_meters(joint["ID"]),
            }
            # Create a new corrosion model instance for this joint
            corrosion_model = CO2CorrosionOpt()

            # Hard-coded optimization parameters initial guess
            opt_param = {"A": 4.93, "B": 1119, "C": 0.58, "D": 2.45}

            # Update the corrosion model with both joint and optimization parameters
            corrosion_model.update_parameters(joint_param)
            corrosion_model.update_parameters(opt_param)

            # Add the updated model to the list of corrosion models
            self.corrosion_models.append(corrosion_model)

    def get_caliper_logs(self):
        """Get caliper logs data."""
        # Will hold caliper logs if any exist
        logs = {"logName": [], "logDate": [], "logData": []}

        if len(self.inputs["selectedLogs"]) == 0:
            print("No caliper logs provided. Skipping caliper read.")

        project_folder = os.path.join(self.plant.project_path, self.plant.name + "/wims_data")
        unit_data_folder = os.path.join(project_folder, self.unit.name)
        selected_well_data_folder = os.path.join(unit_data_folder, "calipers")

        for log in self.inputs["selectedLogs"]:
            logs["logName"].append(log)
            log_path = os.path.join(selected_well_data_folder, log)
            data = ls.read(log_path, ignore_data=False)
            logs["logData"].append(data.df().sort_index())
            # Check if log date is present
            for headeritem in data.well:
                if headeritem["mnemonic"] == "PID" or headeritem["mnemonic"] == "DATE":
                    logs["logDate"].append(headeritem["value"])

            print(f"Caliper {log} loaded successfully!")

        self.inputs["uploadedLogs"] = logs

    def get_water_analysis_data(self):
        """Get water analysis data."""
        # TODO: load water chemistry from UI
        project_folder = os.path.join(self.plant.project_path, self.plant.name)

        # Get water chemistry analysis data
        water_chemistry_file_name = "data/water_chemistry.csv"
        try:
            water_chemistry = pd.read_csv(os.path.join(project_folder, water_chemistry_file_name))
            self.inputs["water_chemistry"] = water_chemistry
            # print("Water analysis data loaded successfully!")
        except (FileNotFoundError, pd.errors.EmptyDataError):
            pass

    def get_production_data(self):
        """Get production data."""
        # Extract production data based on the well type
        if self.unit.parameters["type"] == "production_well":
            # TODO: For production well, chenge to ESP
            well_type = "productionwell"
        elif self.unit.parameters["type"] == "injection_well":
            well_type = "injectionwell"

        start_time = datetime.strptime(self.inputs["start_time"], "%Y-%m-%d %H:%M:%S")
        start_time = tzobject.localize(start_time)
        start_time = start_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        end_time = datetime.strptime(self.inputs["end_time"], "%Y-%m-%d %H:%M:%S")
        end_time = tzobject.localize(end_time)
        end_time = end_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        timestep = 3600  # hardcoded 1 hour since flowrate is in m3/h

        database = self.plant.databases[0]

        try:
            result, time = database.read_internal_database(
                self.unit.plant.name,
                self.unit.name,
                f"{well_type}_flow.measured",
                start_time,
                end_time,
                str(timestep) + "s",
            )
            self.inputs["flow"] = np.array(result)  # m3/hr
            self.inputs["time"] = np.array(time)

            result, time = database.read_internal_database(
                self.unit.plant.name,
                self.unit.name,
                f"{well_type}_wellhead_pressure.measured",
                start_time,
                end_time,
                str(timestep) + "s",
            )
            self.inputs["pressure"] = np.array(result)

            result, time = database.read_internal_database(
                self.unit.plant.name,
                self.unit.name,
                f"{well_type}_wellhead_temperature.measured",
                start_time,
                end_time,
                str(timestep) + "s",
            )
            self.inputs["temperature"] = np.array(result)
            # print("Production data loaded successfully!")
        except Exception:
            pass

    def get_prod_data_validation(self):
        """Read monthly production data from Excel file for validation purposes."""
        try:
            # Get the project folder path with correct structure
            project_folder = os.path.join(self.plant.project_path, self.plant.name + "/data")
            unit_data_folder = os.path.join(project_folder, self.unit.parameters["type"])
            selected_well_data_folder = os.path.join(unit_data_folder, self.unit.parameters["name"])

            # Construct path to the Excel file in the selected_well_data_folder
            excel_file_path = os.path.join(
                selected_well_data_folder, "monthly_production_data.xlsx"
            )

            # Read the Excel file
            monthly_data = pd.read_excel(excel_file_path)

            # Convert date column to datetime if it's not already
            if "Date" in monthly_data.columns:
                monthly_data["Date"] = pd.to_datetime(monthly_data["Date"])

            # Store the data in inputs dictionary
            self.inputs["monthly_flow"] = (
                monthly_data["Flow [m3/h]"].values
                if "Flow [m3/h]" in monthly_data.columns
                else None
            )
            self.inputs["monthly_pressure"] = (
                monthly_data["Pressure [bar]"].values
                if "Pressure [bar]" in monthly_data.columns
                else None
            )
            self.inputs["monthly_temperature"] = (
                monthly_data["Temperature [C]"].values
                if "Temperature [C]" in monthly_data.columns
                else None
            )
            self.inputs["monthly_dates"] = (
                monthly_data["Date"].values if "Date" in monthly_data.columns else None
            )

            print("Monthly production validation data loaded successfully!")
        except Exception as e:
            print(f"Error loading monthly production validation data: {str(e)}")
            # Initialize empty arrays if loading fails
            self.inputs["monthly_flow"] = None
            self.inputs["monthly_pressure"] = None
            self.inputs["monthly_temperature"] = None
            self.inputs["monthly_dates"] = None

    def get_gas_analysis_data(self):
        """Get gas analysis data."""
        pass

    def get_data(self):
        """Load data if available."""
        self.get_caliper_logs()
        # TODO: to be updated
        # self.get_water_analysis_data()
        # self.get_production_data()

    def calculate(self):
        """Execute main calculation pipeline."""
        # print('Corrosion rate from logs started')
        self.get_corrosion_rate_from_logs()
        # print('Corrosion rate from models started')
        self.get_corrosion_rate_from_models_segmented()
        # print('Corrosion rate prediction started')
        self.predict_corrosion_rate()

    def add_corrosion_columns(self, df):
        """Add corrosion columns to dataframe."""
        df["Max. Pen. [%]"] = None
        df["Max. Loss [%]"] = None
        df["Max. Pen. Depth [m]"] = None
        df["Min. Pen. Depth [m]"] = None
        df["Max. ID [inch]"] = None
        df["Min. ID [inch]"] = None
        df["Mean. ID [inch]"] = None
        df["Remaining wall thickness [inch]"] = None
        return df

    def predict_corrosion_rate(self):
        """Predict corrosion rate."""
        self.outputs["predictedCorrosionRate"] = pd.DataFrame(
            range(1, len(self.corrosion_models) + 1),
            index=range(len(self.corrosion_models)),
            columns=["Joint No."],
        )
        self.outputs["predictedThickness"] = pd.DataFrame(
            range(1, len(self.corrosion_models) + 1),
            index=range(len(self.corrosion_models)),
            columns=["Joint No."],
        )
        if len(self.outputs["processedLogs"]) > 0:
            # Sort logs by date
            unsorted_logs = list(
                zip(
                    self.inputs["uploadedLogs"]["logName"],
                    self.inputs["uploadedLogs"]["logDate"],
                    self.inputs["uploadedLogs"]["logData"],
                    self.outputs["processedLogs"],
                )
            )
            sorted_logs = sorted(
                unsorted_logs, key=lambda x: datetime.strptime(x[1], "%H-%M-%S %d-%m-%Y")
            )

            # Get baseline ID (87.5 % of original thickness or based on the latest log mean ID)
            latest_log_dates = datetime.strptime(sorted_logs[-1][1], "%H-%M-%S %d-%m-%Y")

            # Get Corrosion rate for the period between basaline and the End date
            fmt = "%Y-%m-%d %H:%M:%S"
            end_date = datetime.strptime(self.inputs["end_time"], fmt)
            col_label = f"Corroded [mm] between ({latest_log_dates} -> {end_date})"
            self._compute_corrosion_for_interval(
                latest_log_dates, end_date, col_label, output_switch="partial"
            )
            OD_nominal = [i.get("OD") for i in self.inputs["well_tally"]]
            col_label2 = f"Remaining wall thickenss [inch] ({end_date})"
            max_id_values = sorted_logs[-1][3]["Max. ID [inch]"].values.astype(float)
            predicted_values = self.outputs["predictedCorrosionRate"][col_label].values / 25.4
            self.outputs["predictedThickness"][col_label2] = np.round(
                OD_nominal - (max_id_values + predicted_values), 3
            )
        else:
            fmt = "%Y-%m-%d %H:%M:%S"
            start_date = datetime.strptime(self.inputs["start_time"], fmt)
            end_date = datetime.strptime(self.inputs["end_time"], fmt)
            col_label = (
                f"Corroded [mm] between "
                f"({start_date.strftime('%Y-%m-%d')} -> {end_date.strftime('%Y-%m-%d')})"
            )
            self._compute_corrosion_for_interval(
                start_date, end_date, col_label, output_switch="partial"
            )
            OD_nominal = [i.get("OD") for i in self.inputs["well_tally"]]
            ID_nominal = [i.get("ID") for i in self.inputs["well_tally"]]
            col_label2 = f"Predicted ID [inch] ({end_date})"
            predicted_corrosion_values = self.outputs["predictedCorrosionRate"][col_label].values
            self.outputs["predictedThickness"][col_label2] = np.round(
                OD_nominal - (ID_nominal + predicted_corrosion_values / 25.4), 3
            )

    def get_corrosion_rate_from_logs(self):
        """Compute measured corrosion based on log scenarios.

        Scenarios:
         - No logs => 'calculation not possible'
         - 1 log => compare that log to well tally ID at baseline date
         - 2+ logs => compare each log to the *previous* one (chronologically)
        """
        # Use well_tally length so DataFrame size matches when switching wells
        n_tally = len(self.inputs["well_tally"])
        n_logs = len(self.outputs["processedLogs"])

        # Create a DataFrame with Joint No. (n_tally rows to match column value lengths)
        corrosion_rate = pd.DataFrame(
            range(1, n_tally + 1),
            index=range(n_tally),
            columns=["Joint No."],
        )

        # If zero logs: no measurement
        if n_logs == 0:
            print("No logs present. Corrosion rate cannot be calculated.")
            corrosion_rate["Measured Corrosion [mm/year]"] = np.nan
            self.outputs["measuredCorrosionRate"] = corrosion_rate
            return

        # If we have at least one "processed_logs" entry
        # Note: processedLogs is available through self.outputs['processedLogs']

        # Sort logs by date
        unsorted_logs = list(
            zip(
                self.inputs["uploadedLogs"]["logName"],
                self.inputs["uploadedLogs"]["logDate"],
                self.inputs["uploadedLogs"]["logData"],
                self.outputs["processedLogs"],
            )
        )
        sorted_logs = sorted(
            unsorted_logs, key=lambda x: datetime.strptime(x[1], "%H-%M-%S %d-%m-%Y")
        )

        # ------------------------------------------------------------------
        # Baseline date -> first log (log can have fewer joints than tally)
        # ------------------------------------------------------------------
        fmt_log = "%H-%M-%S %d-%m-%Y"
        first_date = datetime.strptime(sorted_logs[0][1], fmt_log)
        first_data = sorted_logs[0][3]
        fmt = "%Y-%m-%d %H:%M:%S"  # The format of your date string
        baseline_date = datetime.strptime(self.inputs["start_time"], fmt)

        n_first = min(n_tally, len(first_data))

        # ID at baseline (from well tally nominal ID at baseline date)
        baseline_id_mm = np.array([row["ID"] * 25.4 for row in self.inputs["well_tally"]])
        first_id_mm = np.array(first_data["Min. ID [inch]"].iloc[:n_first].astype(float) * 25.4)

        delta_time = first_date - baseline_date
        rate_baseline_to_first = (
            abs(baseline_id_mm[:n_first] - first_id_mm)
            * 365
            / abs(delta_time.total_seconds() / 86400)
        ).round(5)
        col_baseline = (
            f"Corrosion rate [mm/year] "
            f"({baseline_date.strftime('%Y-%m-%d')} -> {first_date.strftime('%Y-%m-%d')})"
        )
        col_values = np.full(n_tally, np.nan, dtype=float)
        col_values[:n_first] = np.asarray(rate_baseline_to_first).flat[:n_first]
        corrosion_rate[col_baseline] = col_values

        # ------------------------------------------------------------------
        # If only 1 log in total, we're done
        # ------------------------------------------------------------------
        if n_logs == 1:
            self.outputs["measuredCorrosionRate"] = corrosion_rate
            self.get_remaining_thickness_at_log_dates()
            return

        # 3) If we have 2+ logs, do each consecutive pair (logs can have fewer joints than tally)
        baseline_date = datetime.strptime(sorted_logs[0][1], "%H-%M-%S %d-%m-%Y")
        baseline_data = sorted_logs[0][3]

        for i in range(1, n_logs):
            current_date = datetime.strptime(sorted_logs[i][1], "%H-%M-%S %d-%m-%Y")
            current_data = sorted_logs[i][3]

            duration_days = (current_date - baseline_date).total_seconds() / 86400
            if duration_days <= 0:
                duration_days = 1.0

            n_use = min(n_tally, len(baseline_data), len(current_data))
            baseline_mm = (
                baseline_data["Mean. ID [inch]"].iloc[:n_use].astype(float) * 25.4
            ).values
            current_mm = (current_data["Mean. ID [inch]"].iloc[:n_use].astype(float) * 25.4).values

            measured_rate = (abs(baseline_mm - current_mm) * 365 / abs(duration_days)).round(5)
            col_name = (
                f"Corrosion rate [mm/year] "
                f"({baseline_date.strftime('%Y-%m-%d')} -> "
                f"{current_date.strftime('%Y-%m-%d')})"
            )
            col_values = np.full(n_tally, np.nan, dtype=float)
            col_values[:n_use] = measured_rate
            corrosion_rate[col_name] = col_values

            baseline_date = current_date
            baseline_data = current_data

        self.outputs["measuredCorrosionRate"] = corrosion_rate
        self.get_remaining_thickness_at_log_dates()

    def get_remaining_thickness_at_log_dates(self):
        """Compute remaining wall thickness [mm] at each log date.

        For each processed log (sorted by date), remaining thickness at that date
        is (OD - Max. ID) from well tally and log, converted to mm.
        Output: self.outputs["remainingThicknessAtLogDate"] DataFrame with columns
        Joint No. and one column per log date: "Remaining thickness [mm] (YYYY-MM-DD)".
        """
        n_logs = len(self.outputs["processedLogs"])
        if n_logs == 0:
            self.outputs["remainingThicknessAtLogDate"] = None
            return

        unsorted_logs = list(
            zip(
                self.inputs["uploadedLogs"]["logName"],
                self.inputs["uploadedLogs"]["logDate"],
                self.inputs["uploadedLogs"]["logData"],
                self.outputs["processedLogs"],
            )
        )
        sorted_logs = sorted(
            unsorted_logs, key=lambda x: datetime.strptime(x[1], "%H-%M-%S %d-%m-%Y")
        )
        n_tally = len(self.inputs["well_tally"])
        OD_nominal = np.array([row.get("OD") for row in self.inputs["well_tally"]], dtype=float)

        remaining = pd.DataFrame(
            range(1, n_tally + 1),
            index=range(n_tally),
            columns=["Joint No."],
        )
        INCH_TO_MM = 25.4
        fmt_log = "%H-%M-%S %d-%m-%Y"
        for log_name, log_date_str, _log_data, log_df in sorted_logs:
            log_date = datetime.strptime(log_date_str, fmt_log)
            n_use = min(n_tally, len(log_df))
            max_id = log_df["Min. ID [inch]"].iloc[:n_use].astype(float).values
            # Remaining thickness in inches, then convert to mm
            remaining_thickness_inch = OD_nominal[:n_use] - max_id
            remaining_thickness_mm = np.full(n_tally, np.nan, dtype=float)
            remaining_thickness_mm[:n_use] = (remaining_thickness_inch * INCH_TO_MM).flat[:n_use]
            col_name = f"Remaining thickness [mm] ({log_date.strftime('%Y-%m-%d')})"
            remaining[col_name] = np.round(remaining_thickness_mm, 3)

        self.outputs["remainingThicknessAtLogDate"] = remaining

    def get_remaining_days_to_min_thickness(self, min_remaining_thickness_mm):
        """Compute remaining days until remaining thickness reaches the minimum.

        Uses the latest (by date) corrosion rate and remaining thickness:
        - Latest corrosion rate: last interval in measuredCorrosionRate (chronologically).
        - Latest remaining thickness: last log date column in remainingThicknessAtLogDate.

        Formula: days = (remaining_thickness_mm - min_remaining_thickness_mm) /
        (corrosion_rate_mm_per_year) * 365.25

        Output: self.outputs["remainingDaysToMinThickness"] DataFrame with columns
        Joint No. and "Remaining days to min. thickness [days]".
        """
        measured = self.outputs.get("measuredCorrosionRate")
        remaining = self.outputs.get("remainingThicknessAtLogDate")
        if measured is None or remaining is None or remaining.empty:
            self.outputs["remainingDaysToMinThickness"] = None
            return

        try:
            min_mm = float(min_remaining_thickness_mm)
        except (TypeError, ValueError):
            self.outputs["remainingDaysToMinThickness"] = None
            return

        n_tally = len(self.inputs["well_tally"])

        # Find latest corrosion rate column: "Corrosion rate [mm/year] (YYYY-MM-DD -> YYYY-MM-DD)"
        rate_cols = [
            c
            for c in measured.columns
            if c != "Joint No." and c.startswith("Corrosion rate [mm/year]")
        ]
        date_end_re = re.compile(r"->\s*(\d{4}-\d{2}-\d{2})\s*\)?$")
        latest_rate_col = None
        latest_rate_date = None
        for c in rate_cols:
            m = date_end_re.search(c)
            if m:
                try:
                    dt = datetime.strptime(m.group(1).strip(), "%Y-%m-%d")
                    if latest_rate_date is None or dt >= latest_rate_date:
                        latest_rate_date = dt
                        latest_rate_col = c
                except ValueError:
                    pass
        if latest_rate_col is None and rate_cols:
            latest_rate_col = rate_cols[-1]

        # Find latest remaining thickness column: "Remaining thickness [mm] (YYYY-MM-DD)"
        thick_cols = [
            c
            for c in remaining.columns
            if c != "Joint No." and c.startswith("Remaining thickness [mm]")
        ]
        date_re = re.compile(r"\((\d{4}-\d{2}-\d{2})\)\s*$")
        latest_thick_col = None
        latest_thick_date = None
        for c in thick_cols:
            m = date_re.search(c)
            if m:
                try:
                    dt = datetime.strptime(m.group(1), "%Y-%m-%d")
                    if latest_thick_date is None or dt >= latest_thick_date:
                        latest_thick_date = dt
                        latest_thick_col = c
                except ValueError:
                    pass
        if latest_thick_col is None and thick_cols:
            latest_thick_col = thick_cols[-1]

        if latest_rate_col is None or latest_thick_col is None:
            self.outputs["remainingDaysToMinThickness"] = None
            return

        rate_mm_per_year = np.asarray(measured[latest_rate_col], dtype=float)
        remaining_mm = np.asarray(remaining[latest_thick_col], dtype=float)
        n_use = min(n_tally, len(rate_mm_per_year), len(remaining_mm))

        # days = (T_current - T_min) / R * 365.25  [R in mm/year]
        days_per_year = 365.25
        days_arr = np.full(n_tally, np.nan, dtype=float)
        for i in range(n_use):
            t_cur = remaining_mm[i]
            r = rate_mm_per_year[i]
            if np.isnan(t_cur) or np.isnan(r):
                continue
            if t_cur <= min_mm:
                days_arr[i] = 0.0
                continue
            if r <= 0 or not np.isfinite(r):
                days_arr[i] = np.inf
                continue
            thickness_to_lose = t_cur - min_mm
            days_arr[i] = (thickness_to_lose / r) * days_per_year

        result = pd.DataFrame(
            {
                "Joint No.": range(1, n_tally + 1),
                "Remaining days to min. thickness [days]": days_arr,
            },
            index=range(n_tally),
        )
        self.outputs["remainingDaysToMinThickness"] = result

    def process_caliper_logs(self):
        """Build processed caliper logs for each log.

        If no logs, or only one, we'll handle in get_corrosion_rate_from_logs.
        """
        # Check well type
        if "production" in self.unit.name:
            pass
        elif "injection" in self.unit.name:
            pass

        processedLogs = []

        if len(self.inputs["uploadedLogs"]) == 0:
            # No logs => nothing to process. We'll handle fallback in get_corrosion_rate_from_logs.
            self.outputs["processed_caliper_logs"] = processedLogs
            return

        # Process each log
        for log_nr, log in enumerate(self.inputs["uploadedLogs"]["logData"]):
            # Create a fresh DataFrame for each log to avoid duplication
            df = pd.DataFrame(
                range(1, len(self.inputs["well_tally"]) + 1),
                index=range(len(self.inputs["well_tally"])),
                columns=["Joint No."],
            )
            processed_log = self.add_corrosion_columns(df)

            for joint_nr, joint in enumerate(self.inputs["well_tally"]):

                # Extract the slice from the log data using the 'Top [m MD]' and
                # 'Bottom [m MD]' values from the joint dictionary
                # TODO: Make more robust regex filter
                caliper_subset = log.loc[joint["TopMD"] : joint["BottomMD"]].filter(
                    regex=r"^D\d{2}$"
                )
                try:
                    # Calculate statistics from the caliper subset
                    mean_caliper = caliper_subset.mean().mean()
                    max_caliper = caliper_subset.max().max()
                    min_caliper = caliper_subset.min().min()

                    # Determine the location indices of the max and min caliper values
                    max_cal_loc = caliper_subset.stack().idxmax()[0]
                    min_cal_loc = caliper_subset.stack().idxmin()[0]

                    # Get the base inner and outer diameters from the joint dictionary
                    base_id = joint["ID"]
                    base_od = joint["OD"]

                    # Calculate maximum penetration percentage
                    max_penetration = 100 * (max_caliper - base_id) / (base_od - base_id)

                    # Calculate maximum circumferential wall loss
                    max_circ_wall_loss = (
                        100
                        / 60
                        * ((caliper_subset**2 - base_id**2) / (base_od**2 - base_id**2)).sum(axis=1)
                    ).mean()

                    # Remaining wall thickness
                    remaining_wall_thickness = base_od - max_caliper

                    # Build a dictionary with the computed result values
                    result_values = {
                        "Max. Pen. Depth [m]": max_cal_loc,
                        "Min. Pen. Depth [m]": min_cal_loc,
                        "Max. Pen. [%]": np.round(max_penetration, 1),
                        "Max. Loss [%]": np.round(max_circ_wall_loss, 1),
                        "Max. ID [inch]": max_caliper,
                        "Min. ID [inch]": min_caliper,
                        "Mean. ID [inch]": np.round(mean_caliper, 3),
                        "Remaining wall thickness [inch]": np.round(remaining_wall_thickness, 3),
                    }
                    # Update the processed_log DataFrame at the row corresponding to joint_nr
                    # Convert the keys and values to lists for assignment
                    processed_log.loc[joint_nr, list(result_values.keys())] = list(
                        result_values.values()
                    )

                except (KeyError, IndexError, ValueError):
                    # If any issue occurs (e.g., missing keys or empty subsets), skip this joint.
                    continue

            # Append a copy of the processed log to avoid reference issues
            processedLogs.append(processed_log.copy())

        self.outputs["processedLogs"] = processedLogs
        # print("Log Processed successfully!")

    def get_corrosion_rate_from_models_segmented(self):
        """Compute modelled corrosion in multiple intervals.

        - Baseline date -> 1st log date
        - 1st log date -> 2nd log date
        - 2nd log date -> 3rd log date
        - etc.

        For each interval, we:

        1. Filter the flow/pressure/temp data to [start_date, end_date)
        2. Compute partial corrosion with a pairwise approach
        3. Convert the sum of partial corrosion to [mm/year] over that interval
        4. Store in a new column in ``self.outputs['modelledCorrosionRate']``
        """
        # Check well type
        if self.unit.parameters["type"] == "production_well":
            pass
        elif self.unit.parameters["type"] == "injection_well":
            pass

        # We'll store multiple columns, one per interval
        # Start with the "base" DataFrame
        self.outputs["modelledCorrosionRate"] = pd.DataFrame(
            range(1, len(self.corrosion_models) + 1),
            index=range(len(self.corrosion_models)),
            columns=["Joint No."],
        )

        unsorted_logs = list(
            zip(
                self.inputs["uploadedLogs"]["logName"],
                self.inputs["uploadedLogs"]["logDate"],
                self.inputs["uploadedLogs"]["logData"],
                self.outputs["processedLogs"],
            )
        )
        sorted_logs = sorted(
            unsorted_logs, key=lambda x: datetime.strptime(x[1], "%H-%M-%S %d-%m-%Y")
        )

        # 2) Build a sorted list of log dates plus baseline date from start_time
        fmt = "%Y-%m-%d %H:%M:%S"  # The format of your date string
        baseline_date = datetime.strptime(self.inputs["start_time"], fmt)
        sorted_log_dates = []
        for log in sorted_logs:
            sorted_log_dates.append(datetime.strptime(log[1], "%H-%M-%S %d-%m-%Y"))

        # If no logs at all => just 1 interval from baseline_date -> now (or skip)
        if len(sorted_log_dates) == 0:
            print("No logs => single interval from baseline to 'end of data' assumed.")
            interval_label = (
                f"Modelled Corrosion "
                f"({baseline_date.strftime('%Y-%m-%d')}->{datetime.now().strftime('%Y-%m-%d')})"
            )
            self._compute_corrosion_for_interval(baseline_date, datetime.now(), interval_label)
            return

        # If we have logs, compute each interval:
        # 3) Compute first interval: baseline_date -> first_log_date
        first_log_date = sorted_log_dates[0]
        if first_log_date > baseline_date:
            start_date = baseline_date
            end_date = first_log_date
            col_label = (
                f"Corrosion rate [mm/year] "
                f"({start_date.strftime('%Y-%m-%d')} -> "
                f"{end_date.strftime('%Y-%m-%d')})"
            )
            # Calculate the corrosion rate for the interval
            self._compute_corrosion_for_interval(start_date, end_date, col_label)

        # 4) For each pair of consecutive logs:
        for i in range(1, len(sorted_log_dates)):
            start_date = sorted_log_dates[i - 1]
            end_date = sorted_log_dates[i]
            col_label = (
                f"Corrosion rate [mm/year] "
                f"({start_date.strftime('%Y-%m-%d')} -> "
                f"{end_date.strftime('%Y-%m-%d')})"
            )
            # Calculate the corrosion rate for the interval
            self._compute_corrosion_for_interval(start_date, end_date, col_label)

    def _compute_corrosion_for_interval(
        self, start_date, end_date, column_label, output_switch="rate"
    ):
        """Compute the corrosion rate for a specific interval."""
        # Check well type
        try:
            well_type = self.unit.parameters["type"]
            if well_type == "production_well":
                # TODO: For production well, change to ESP
                well_type = "productionwell"
            elif well_type == "injection_well":
                well_type = "injectionwell"
        except KeyError:
            pass

        flow_df = pd.DataFrame(
            {"datetime": self.inputs["time"], "value": self.inputs["flow"]}
        ).copy()
        if self.inputs["interval_type"] == "logs":
            # Get the subset of the data for the interval
            flow_subset = flow_df[
                (flow_df["datetime"] >= start_date) & (flow_df["datetime"] < end_date)
            ].sort_values("datetime")
        else:
            # Get the subset of the data for the interval
            flow_subset = flow_df[
                (flow_df["datetime"] >= start_date) & (flow_df["datetime"] < end_date)
            ].sort_values("datetime")

            pressure_df = pd.DataFrame(
                {"datetime": self.inputs["time"], "value": self.inputs["pressure"]}
            ).copy()
            pressure_subset = pressure_df[
                (pressure_df["datetime"] >= start_date) & (pressure_df["datetime"] < end_date)
            ].sort_values("datetime")

            temperature_df = pd.DataFrame(
                {"datetime": self.inputs["time"], "value": self.inputs["temperature"]}
            ).copy()
            temperature_subset = temperature_df[
                (temperature_df["datetime"] >= start_date) & (temperature_df["datetime"] < end_date)
            ].sort_values("datetime")

            # Check if we have data for the interval
            if flow_subset.empty or pressure_subset.empty or temperature_subset.empty:
                print(f"No data for interval {start_date} to {end_date}")
                return

        # Get the number of joints
        n_joints = len(self.inputs["well_tally"])

        # Initialize the corrosion rate arrays
        corrosion_rates = np.zeros(n_joints)
        partial_corrosion = np.zeros(n_joints)

        # Try to coarsen the time series
        try:
            flow_subset, pressure_subset, temperature_subset = (
                self.coarsen_timeseries_by_change_point(
                    flow_subset, pressure_subset, temperature_subset
                )
            )
        except Exception:
            pass

        # Get the flow, pressure, and temperature values for the interval
        flow_values = flow_subset["value"].values
        pressure_values = pressure_subset["value"].values
        temperature_values = temperature_subset["value"].values

        # Check if we have data for the interval
        if len(flow_values) == 0 or len(pressure_values) == 0 or len(temperature_values) == 0:
            print(f"No data for interval {start_date} to {end_date}")
            return

        # Here for simplicity, we say i-th row in flow_subset aligns with
        # i-th row in pressure_subset, etc.
        n_time_points = len(flow_values)

        # Initialize the well hydraulic model
        well_hydraulic_param = {
            "flow": flow_values,
            "pressure": pressure_values,
            "temperature": temperature_values,
            "n_time_points": n_time_points,
            "n_joints": n_joints,
            "water_chemistry_data": self.inputs.get("water_chemistry"),
            "monthly_production_data": self.inputs.get("monthly_production_data"),
            "monthly_dates": self.inputs.get("monthly_dates"),
            "direction": "down",
        }
        self.VLP.update_parameters(well_hydraulic_param)

        # Loop through each joint
        for joint_idx in range(n_joints):
            # Calculate the corrosion rate for this joint
            for sec_idx, (sec_temp_c, sec_pres_bar) in enumerate(
                zip(temperature_values, pressure_values)
            ):
                # Get the CO2 partial pressure
                co2_partial_pressure = self.co2_models[joint_idx].get_co2_partial_pressure(
                    sec_temp_c, sec_pres_bar, self.inputs.get("water_chemistry")
                )
                # Get the corrosion rate
                corrosion_rate = self.corrosion_models[joint_idx].get_corrosion_rate(
                    sec_temp_c, sec_pres_bar, co2_partial_pressure
                )
                # Add the corrosion rate to the total
                corrosion_rates[joint_idx] += corrosion_rate

            # Calculate the average corrosion rate for this joint
            corrosion_rates[joint_idx] /= n_time_points

            # Calculate the partial corrosion for this joint
            delta_time = end_date - start_date
            partial_corrosion[joint_idx] = (
                corrosion_rates[joint_idx] * delta_time.total_seconds() / 31536000
            )

        # Store the results in the outputs
        try:
            # Create a DataFrame with the corrosion rates
            corrosion_df = pd.DataFrame(
                {"Joint": range(1, n_joints + 1), column_label: corrosion_rates}
            )
            # Set the index to the joint number
            corrosion_df.set_index("Joint", inplace=True)
            # Store the corrosion rates in the outputs
            self.outputs["modelledCorrosionRate"][column_label] = corrosion_df[column_label]

            # Store the partial corrosion in the outputs
            if output_switch == "partial":
                if "modelledCorrosionRateCalibrated" not in self.outputs:
                    self.outputs["modelledCorrosionRateCalibrated"] = pd.DataFrame()
                self.outputs["modelledCorrosionRateCalibrated"][column_label] = partial_corrosion

        except Exception:
            pass

    def optimize_models(self):
        """Optimize the corrosion models to fit the observed data."""
        OptCO2Corrosion(self.inputs, self.outputs, self.corrosion_models, self.co2_models, self.VLP)

    def inches_to_meters(self, inches):
        """Convert inches to meters."""
        return inches * 0.0254

    def coarsen_timeseries_by_change_point(
        self, df1, df2, df3, value_col="value", pen=3, plot=False
    ):
        """Coarsen a time series by detecting segments where the values do not change much.

        Parameters:
          df (pd.DataFrame): DataFrame with a DateTime index.
          value_col (str): The column name containing the values to analyze.
          pen (float or int): Penalty parameter for the PELT change-point
                             detection algorithm.
          plot (bool): If True, plot the original time series with detected
                      change points.

        Returns:
          pd.DataFrame: A DataFrame with columns ['start_date', 'end_date',
                       'mean_value'] for each segment.
        """
        # Fit the change-point detection algorithm (PELT) on the time series values
        algo = rpt.Pelt(model="l2").fit(df1[value_col].values)
        change_points = algo.predict(pen=pen)

        dfs = [df1, df2, df3]
        dfs_coarse = []

        for df in dfs:
            segments = []
            start = 0
            segments.append({"datetime": df.datetime.iloc[0], "value": df.value.iloc[0]})
            for cp in change_points:
                # Extract the segment from start index to the current change point
                segment = df.iloc[start:cp]
                mean_value = segment[value_col].mean()
                segments.append(
                    {"datetime": segment.datetime[(segment.index[-1])], "value": mean_value}
                )
                start = cp
            dfs_coarse.append(pd.DataFrame(segments))

        return dfs_coarse
