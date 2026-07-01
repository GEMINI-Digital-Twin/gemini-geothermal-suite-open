"""CO2 corrosion analysis application with caliper log processing and model optimization."""

import json
import os
from datetime import datetime, timedelta, timezone

import lasio as ls
import numpy as np
import pandas as pd
import pytz

from gemini_application.application_abstract import ApplicationAbstract
from gemini_application.wims.corrosion_from_logs import (
    ANNUAL_WALL_THICKNESS_CHANGE_RATE_COL,
    PREDICTED_WALL_THICKNESS_CHANGE_RATE_PREFIX,
    WALL_THICKNESS_CHANGE_PREFIX,
    detect_joints,
    get_measured_corrosion_rate_from_logs,
    get_remaining_days_to_min_thickness,
    get_remaining_thickness_at_log_dates,
    process_caliper_logs,
)
from gemini_application.wims.corrosion_from_prod_data import (
    build_prod_corrosion_context,
    coarsen_timeseries_by_change_point,
    compute_corrosion_for_interval,
    corroded_mm_for_interval,
    get_corrosion_rate_from_prod_data,
)
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

    def _get_esp_depth_m(self):
        """Return ESP setting depth in meters MD, or None if no ESP unit found.

        Looks for an ESP unit in ``self.unit.to_units`` and reads
        ``esp_unit.parameters["property"]["esp_depth"]``.
        """
        for u in getattr(self.unit, "to_units", []):
            if "esp" in u.name.lower():
                prop = u.parameters.get("property") or {}
                depths = prop.get("esp_depth")
                if depths:
                    return float(depths[0])
        return None

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

    def _load_logs_metadata(self):
        """Load per-log metadata from logs_information.json.

        Returns the ``"logs"`` dict or an empty dict if the file is missing
        or malformed (production-only wells may not have this file).
        """
        try:
            project_folder = os.path.join(self.plant.project_path, self.plant.name + "/wims_data")
            unit_data_folder = os.path.join(project_folder, self.unit.name)
            logs_info_path = os.path.join(unit_data_folder, "logs_information.json")

            if not os.path.exists(logs_info_path):
                return {}

            with open(logs_info_path, "r") as f:
                data = json.load(f)

            if isinstance(data, dict) and isinstance(data.get("logs"), dict):
                return data["logs"]
            return {}
        except (OSError, json.JSONDecodeError, AttributeError):
            return {}

    def init_parameters(self, corrosion_model_name="DLD"):
        """Initialize model parameters using tally from well parameters only."""
        well_tally = self._get_tally_from_well_parameters()
        if not well_tally:
            raise ValueError("No well tally found in Well Parameters (app builder).")
        self.inputs["well_tally"] = well_tally

        # Load per-log metadata from logs_information.json (graceful if missing).
        self.inputs["logs_metadata"] = self._load_logs_metadata()

        # -- determine ESP joint offset for production wells ---
        well_type = self._get_well_type()
        esp_joint_start_idx = 0

        if well_type == "productionwell":
            esp_depth_m = self._get_esp_depth_m()
            if esp_depth_m is not None:
                for idx, entry in enumerate(well_tally):
                    if float(entry["TopMD"]) >= esp_depth_m:
                        esp_joint_start_idx = idx
                        break
                else:
                    esp_joint_start_idx = len(well_tally)

        self.inputs["esp_joint_start_idx"] = esp_joint_start_idx

        # -- build corrosion/CO2 models for active joints (at/below ESP) ---
        active_tally = well_tally[esp_joint_start_idx:]

        # VLP geometry covers only joints *below* the ESP joint; the ESP
        # joint itself uses the measured P/T directly (no VLP needed).

        # Ensure repeated calls do not keep appending stale models.
        self.corrosion_models = []
        self.co2_models = []

        inch_to_m = 0.0254
        required_keys = ("TopMD", "BottomMD", "TopTVD", "BottomTVD", "ID", "Roughness")
        opt_param = {"A": 4.93, "B": 1119, "C": 0.58, "D": 2.45}

        vlp_length = []
        vlp_diameter = []
        vlp_angle = []
        vlp_roughness = []

        for i, entry in enumerate(active_tally):
            orig_idx = esp_joint_start_idx + i
            missing_keys = [key for key in required_keys if key not in entry]
            if missing_keys:
                raise ValueError(
                    f"Invalid well tally row at index {orig_idx}: missing keys {missing_keys}."
                )

            top_md = float(entry["TopMD"])
            bot_md = float(entry["BottomMD"])
            top_tvd = float(entry["TopTVD"])
            bot_tvd = float(entry["BottomTVD"])

            md = bot_md - top_md
            tvd = bot_tvd - top_tvd
            if md <= 0:
                raise ValueError(
                    f"Invalid well tally row at index {orig_idx}: "
                    "BottomMD must be larger than TopMD."
                )

            nominal_id_m = float(entry["ID"]) * inch_to_m

            # Guard against floating-point noise outside acos domain [-1, 1].
            ratio = np.clip(tvd / md, -1.0, 1.0)
            incl_deg = 90 - np.degrees(np.arccos(ratio))
            incl_rad = np.radians(incl_deg)

            roughness_val = float(entry["Roughness"])

            # VLP geometry: skip the ESP joint (i==0 when esp_joint_start_idx>0)
            if esp_joint_start_idx == 0 or i > 0:
                vlp_length.append(md)
                vlp_diameter.append(nominal_id_m)
                vlp_angle.append(incl_rad)
                vlp_roughness.append(roughness_val)

            self.co2_models.append(CO2PartialPressureModel())

            # Initialize corrosion model for each well section.
            joint_param = {
                "roughness": roughness_val,
                "corrosion_model": corrosion_model_name,
                "diameter": nominal_id_m,
            }
            corrosion_model = CO2CorrosionOpt()
            corrosion_model.update_parameters(joint_param)
            corrosion_model.update_parameters(opt_param)
            self.corrosion_models.append(corrosion_model)

        # Init PVT model;
        self.VLP.PVT = PVTConstantSTP()
        # Build well_param and update the VLP (joints below ESP only)
        well_param = {
            "friction_correlation": "darcy_weisbach",
            "friction_correlation_2p": "BeggsBrill",
            "correction_factors": [1, 0],
            "diameter": np.array(vlp_diameter, dtype=float),
            "length": np.array(vlp_length, dtype=float),
            "angle": np.array(vlp_angle, dtype=float),
            "roughness": np.array(vlp_roughness, dtype=float),
        }
        self.VLP.update_parameters(well_param)

    def get_caliper_logs(self):
        """Get caliper logs data."""
        # Will hold caliper logs if any exist
        caliper_logs = {
            "name": [],
            "date": [],
            "data": [],
            "is_baseline": [],
            "finger_units": [],
            "joint_identification_marker": [],
            "depth_corrected": [],
            "finger_name": [],
            "max_column_name": [],
            "min_column_name": [],
            "average_column_name": [],
        }

        if len(self.inputs["selectedLogs"]) == 0:
            print("No caliper logs provided. Skipping caliper read.")
            self.inputs["uploadedLogs"] = caliper_logs
            return

        project_folder = os.path.join(self.plant.project_path, self.plant.name + "/wims_data")
        unit_data_folder = os.path.join(project_folder, self.unit.name)
        selected_well_data_folder = os.path.join(unit_data_folder, "calipers")

        logs_metadata = self.inputs.get("logs_metadata", {})
        if not logs_metadata:
            raise ValueError(
                "No logs metadata available. Ensure logs_information.json exists "
                "in the well's wims_data folder with per-log metadata."
            )

        for caliper_log_name in self.inputs["selectedLogs"]:
            log_info = logs_metadata.get(caliper_log_name)
            if not isinstance(log_info, dict):
                raise ValueError(
                    f"Missing metadata for selected log '{caliper_log_name}' "
                    f"in logs_information.json under logs['{caliper_log_name}']."
                )
            stored_date = (log_info.get("date") or "").strip()
            if not stored_date:
                raise ValueError(
                    f"Missing date for selected log '{caliper_log_name}' in "
                    "logs_information.json. Set logs[<log_name>].date as YYYY-MM-DD."
                )
            try:
                parsed_date = datetime.strptime(stored_date, "%Y-%m-%d")
                internal_log_date = parsed_date.strftime("%H-%M-%S %d-%m-%Y")
            except ValueError as exc:
                raise ValueError(
                    f"Invalid date '{stored_date}' for selected log '{caliper_log_name}' in "
                    "logs_information.json. Expected format YYYY-MM-DD."
                ) from exc

            caliper_logs["name"].append(caliper_log_name)
            log_path = os.path.join(selected_well_data_folder, caliper_log_name)
            caliper_log_file = ls.read(log_path, ignore_data=False)
            caliper_logs["data"].append(caliper_log_file.df().sort_index())
            caliper_logs["date"].append(internal_log_date)
            caliper_logs["is_baseline"].append(bool(log_info.get("is_baseline", False)))
            caliper_logs["finger_units"].append(log_info.get("finger_units"))
            caliper_logs["joint_identification_marker"].append(
                log_info.get("joint_identification_marker")
            )
            caliper_logs["depth_corrected"].append(bool(log_info.get("depth_corrected", False)))
            caliper_logs["finger_name"].append(log_info.get("finger_name"))
            caliper_logs["max_column_name"].append(log_info.get("max_column_name"))
            caliper_logs["min_column_name"].append(log_info.get("min_column_name"))
            caliper_logs["average_column_name"].append(log_info.get("average_column_name"))

            print(f"Caliper {caliper_log_name} loaded successfully!")

        self.inputs["uploadedLogs"] = caliper_logs

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

    def set_production_window_from_logs_metadata(self):
        """Set ``start_time`` and ``end_time`` in inputs from ``logs_metadata`` dates.

        Uses the baseline log date for start when ``is_baseline`` is set, otherwise
        the earliest log date. End time is the latest log date (end of day).

        Returns
        -------
        str or None
            Error message if no valid log dates were found, otherwise None.
        """
        logs_metadata = self.inputs.get("logs_metadata") or {}
        log_dates = []
        baseline_date = None
        for entry in logs_metadata.values():
            if not isinstance(entry, dict):
                continue
            stored = (entry.get("date") or "").strip()
            if not stored:
                continue
            try:
                dt = datetime.strptime(stored, "%Y-%m-%d")
            except ValueError:
                continue
            log_dates.append(dt)
            if entry.get("is_baseline"):
                baseline_date = dt

        if not log_dates:
            return "No log dates in logs_metadata. Set dates in logs_information.json."

        start_dt = baseline_date if baseline_date is not None else min(log_dates)
        end_dt = max(log_dates)
        self.inputs["start_time"] = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        self.inputs["end_time"] = end_dt.strftime("%Y-%m-%d 23:59:59")
        return None

    def _get_sorted_log_dates(self):
        """Extract sorted log dates from logs_metadata as UTC-aware Timestamps."""
        logs_metadata = self.inputs.get("logs_metadata") or {}
        log_dates = []
        for entry in logs_metadata.values():
            if not isinstance(entry, dict):
                continue
            stored = (entry.get("date") or "").strip()
            if not stored:
                continue
            try:
                dt = pd.Timestamp(stored, tz="UTC")
            except (ValueError, TypeError):
                continue
            log_dates.append(dt)
        return sorted(log_dates)

    def _coarsen_production_data(self, pen=3, predecimate_bin_hours=24):
        """Reduce flow/pressure/temperature series using change-point segmentation.

        When multiple log dates are available, coarsening is performed
        independently for each interval between consecutive log dates so that
        PELT detects regime changes within each period separately.
        """
        flow = self.inputs.get("flow")
        if flow is None or len(flow) == 0:
            return

        flow_df = pd.DataFrame({"datetime": self.inputs["time"], "value": self.inputs["flow"]})
        pressure_df = pd.DataFrame(
            {"datetime": self.inputs["time"], "value": self.inputs["pressure"]}
        )
        temperature_df = pd.DataFrame(
            {"datetime": self.inputs["time"], "value": self.inputs["temperature"]}
        )

        flow_df["datetime"] = pd.to_datetime(flow_df["datetime"])
        pressure_df["datetime"] = pd.to_datetime(pressure_df["datetime"])
        temperature_df["datetime"] = pd.to_datetime(temperature_df["datetime"])

        log_dates = self._get_sorted_log_dates()

        if len(log_dates) < 2:
            try:
                flow_df, pressure_df, temperature_df = coarsen_timeseries_by_change_point(
                    flow_df,
                    pressure_df,
                    temperature_df,
                    pen=pen,
                    predecimate_bin_hours=predecimate_bin_hours,
                )
            except Exception:
                return
        else:
            flow_parts = []
            pressure_parts = []
            temperature_parts = []

            for i in range(len(log_dates) - 1):
                start = log_dates[i]
                end = log_dates[i + 1]

                mask = (flow_df["datetime"] >= start) & (flow_df["datetime"] < end)
                flow_seg = flow_df.loc[mask].reset_index(drop=True)
                pressure_seg = pressure_df.loc[mask].reset_index(drop=True)
                temperature_seg = temperature_df.loc[mask].reset_index(drop=True)

                if flow_seg.empty:
                    continue

                try:
                    flow_c, pres_c, temp_c = coarsen_timeseries_by_change_point(
                        flow_seg,
                        pressure_seg,
                        temperature_seg,
                        pen=pen,
                        predecimate_bin_hours=predecimate_bin_hours,
                    )
                except Exception:
                    flow_c, pres_c, temp_c = flow_seg, pressure_seg, temperature_seg

                flow_parts.append(flow_c)
                pressure_parts.append(pres_c)
                temperature_parts.append(temp_c)

            if not flow_parts:
                return

            flow_df = pd.concat(flow_parts, ignore_index=True)
            pressure_df = pd.concat(pressure_parts, ignore_index=True)
            temperature_df = pd.concat(temperature_parts, ignore_index=True)

        self.inputs["time"] = flow_df["datetime"].values
        self.inputs["flow"] = flow_df["value"].values
        self.inputs["pressure"] = pressure_df["value"].values
        self.inputs["temperature"] = temperature_df["value"].values
        self.inputs["production_data_coarsened"] = True

    def get_production_data(self, coarsen=False, pen=3, predecimate_bin_hours=12):
        """Get production data from the plant database.

        Parameters
        ----------
        coarsen : bool
            If True, downsample flow, pressure, and temperature using change-point
            detection (see ``coarsen_timeseries_by_change_point``).
        pen : float
            Penalty passed to the change-point detector when ``coarsen`` is True.
        predecimate_bin_hours : float
            Hours per bin used before PELT when the native sampling interval is
            finer than this value. The resulting bin count follows from the data
            time span (e.g. hourly data over ~8 years with ``24`` yields ~2920 bins).
        """
        well_type = self._get_well_type()

        start_time = datetime.strptime(self.inputs["start_time"], "%Y-%m-%d %H:%M:%S")
        start_time = tzobject.localize(start_time)
        start_time = start_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        end_time = datetime.strptime(self.inputs["end_time"], "%Y-%m-%d %H:%M:%S")
        end_time = tzobject.localize(end_time)
        end_time = end_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        timestep = 3600  # hardcoded 1 hour since flowrate is in m3/h

        # -- select database tags and asset name by well type -----
        if well_type == "productionwell":
            flow_tag = "esp_flow.measured"
            pressure_tag = "esp_inlet_pressure.measured"
            temperature_tag = "esp_inlet_temperature.measured"
            asset_name = self.unit.to_units[0].name
        else:
            flow_tag = f"{well_type}_flow.measured"
            pressure_tag = f"{well_type}_wellhead_pressure.measured"
            temperature_tag = f"{well_type}_wellhead_temperature.measured"
            asset_name = self.unit.name

        try:
            result, time = self.plant.database.read_internal_database(
                self.unit.plant.name,
                asset_name,
                flow_tag,
                start_time,
                end_time,
                timestep,
            )
            self.inputs["flow"] = np.array(result)  # m3/hr
            self.inputs["time"] = np.array(time)

            result, time = self.plant.database.read_internal_database(
                self.unit.plant.name,
                asset_name,
                pressure_tag,
                start_time,
                end_time,
                timestep,
            )
            self.inputs["pressure"] = np.array(result)

            result, time = self.plant.database.read_internal_database(
                self.unit.plant.name,
                asset_name,
                temperature_tag,
                start_time,
                end_time,
                timestep,
            )
            self.inputs["temperature"] = np.array(result)
        except Exception:
            pass

        if coarsen and self.inputs.get("flow") is not None:
            self._coarsen_production_data(pen=pen, predecimate_bin_hours=predecimate_bin_hours)

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
        # print('Corrosion rate from production data started')
        self.get_corrosion_rate_from_prod_data()
        # print('Corrosion rate prediction started')
        self.predict_corrosion_rate()

    def predict_corrosion_rate(self):
        """Predict corrosion rate."""
        n_total_joints = len(self.inputs["well_tally"])
        self.outputs["predictedCorrosionRate"] = pd.DataFrame(
            range(1, n_total_joints + 1),
            index=range(n_total_joints),
            columns=["Joint No."],
        )
        self.outputs["predictedThickness"] = pd.DataFrame(
            range(1, n_total_joints + 1),
            index=range(n_total_joints),
            columns=["Joint No."],
        )
        if len(self.outputs["processedLogs"]) > 0:
            # Sort logs by date
            unsorted_logs = list(
                zip(
                    self.inputs["uploadedLogs"]["name"],
                    self.inputs["uploadedLogs"]["date"],
                    self.inputs["uploadedLogs"]["data"],
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
            max_id_values = sorted_logs[-1][3]["Max. Radius [inch]"].values.astype(float) * 2
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
        self.outputs["measuredCorrosionRate"] = get_measured_corrosion_rate_from_logs(
            well_tally=self.inputs["well_tally"],
            logs_metadata=self.inputs.get("logs_metadata", {}),
            selected_log_names=self.inputs.get("selectedLogs", []),
            processed_logs=self.outputs["processedLogs"],
            start_time=self.inputs["start_time"],
        )
        self.get_remaining_thickness_at_log_dates()

    def get_remaining_thickness_at_log_dates(self):
        """Compute remaining wall thickness [mm] at each log date.

        For each processed log (sorted by date), remaining thickness at that date
        is (OD - Max. ID) from well tally and log, converted to mm.
        Output: self.outputs["remainingThicknessAtLogDate"] DataFrame with columns
        Joint No. and one column per log date: "Remaining thickness [mm] (YYYY-MM-DD)".
        """
        self.outputs["remainingThicknessAtLogDate"] = get_remaining_thickness_at_log_dates(
            well_tally=self.inputs["well_tally"],
            uploaded_logs=self.inputs["uploadedLogs"],
            processed_logs=self.outputs["processedLogs"],
        )

    def get_remaining_days_to_min_thickness(self, min_remaining_thickness_mm):
        """Compute remaining days until remaining thickness reaches the minimum.

        Uses the latest (by date) corrosion rate and remaining thickness:
        - Latest corrosion rate: last interval in measuredCorrosionRate (chronologically).
        - Latest remaining thickness: last log date column in remainingThicknessAtLogDate.

        Formula: days = (remaining_thickness_mm - min_remaining_thickness_mm)
        / (corrosion_rate_mm_per_year) * 365.25

        Output: self.outputs["remainingDaysToMinThickness"] DataFrame with columns
        Joint No. and "Remaining days to min. thickness [days]".
        """
        self.outputs["remainingDaysToMinThickness"] = get_remaining_days_to_min_thickness(
            well_tally=self.inputs["well_tally"],
            measured=self.outputs.get("measuredCorrosionRate"),
            remaining=self.outputs.get("remainingThicknessAtLogDate"),
            min_remaining_thickness_mm=min_remaining_thickness_mm,
        )

    def detect_joints(self, detection_params=None):
        """Detect joint candidates for each uploaded log (QA/QC step).

        Stores results in ``self.outputs["detectedJoints"]`` -- a list (per log)
        of candidate dicts with keys: joint_no, top, bottom, method, tally.
        """
        self.outputs["detectedJoints"] = detect_joints(
            uploaded_logs=self.inputs["uploadedLogs"],
            well_tally=self.inputs["well_tally"],
            detection_params=detection_params,
        )

    def process_caliper_logs(self, approved_joints=None, qa_log_dir=None):
        """Build processed caliper logs for each log.

        Parameters
        ----------
        approved_joints : list[list[dict]] or None
            Pre-approved joint boundaries from QA/QC. When provided, detection
            is skipped and these are used directly.
        qa_log_dir : str or Path or None
            Directory to write per-log QA JSON files for joint-to-tally matching.
        """
        self.outputs["processedLogs"] = process_caliper_logs(
            uploaded_logs=self.inputs["uploadedLogs"],
            well_tally=self.inputs["well_tally"],
            approved_joints=approved_joints,
            qa_log_dir=qa_log_dir,
        )
        # print("Log Processed successfully!")

    def get_corrosion_rate_from_prod_data(self):
        """Compute corrosion rate from production data using VLP per-joint P/T.

        Splits the production window into intervals defined by log dates from
        ``logs_metadata``.  Output is stored in
        ``self.outputs['measuredCorrosionRate']`` with columns 'Joint No.',
        'Corrosion rate [mm/year] (date1 -> date2)', and
        'Corroded [mm] (date1 -> date2)' for each interval.
        """
        self.outputs["measuredCorrosionRate"] = get_corrosion_rate_from_prod_data(
            well_tally=self.inputs["well_tally"],
            inputs=self.inputs,
            corrosion_models=self.corrosion_models,
            co2_models=self.co2_models,
            vlp=self.VLP,
            esp_joint_start_idx=self.inputs.get("esp_joint_start_idx", 0),
        )

    def _compute_corrosion_for_interval(
        self, start_date, end_date, column_label, output_switch="rate"
    ):
        """Compute the corrosion rate for a specific interval."""
        compute_corrosion_for_interval(
            inputs=self.inputs,
            outputs=self.outputs,
            vlp=self.VLP,
            co2_models=self.co2_models,
            corrosion_models=self.corrosion_models,
            start_date=start_date,
            end_date=end_date,
            column_label=column_label,
            output_switch=output_switch,
            esp_joint_start_idx=self.inputs.get("esp_joint_start_idx", 0),
        )

    def _corrosion_opt_params_path(self):
        """Return the path to the persisted corrosion calibration parameters.

        Mirrors :meth:`_load_logs_metadata`
        (``<project>/<plant>/wims_data/<unit>/corrosion_opt_params.json``).
        Returns ``None`` when plant/unit context is unavailable, so calibration
        still runs without persistence.
        """
        try:
            project_folder = os.path.join(self.plant.project_path, self.plant.name + "/wims_data")
            unit_data_folder = os.path.join(project_folder, self.unit.name)
            return os.path.join(unit_data_folder, "corrosion_opt_params.json")
        except AttributeError:
            return None

    def optimize_models(self, progress_callback=None):
        """Calibrate corrosion models against log-measured corrosion.

        Fits per-joint DLD parameters so the production-data modelled rate
        matches the caliper-log measured rate, writes the optimized parameters
        back into ``self.corrosion_models``, stores modelled/measured rates in
        ``self.outputs``, and persists the parameters for reuse.

        Parameters
        ----------
        progress_callback : callable or None
            Forwarded to :meth:`OptCO2Corrosion.calibrate`; invoked as
            ``fn(completed, total, per_joint)`` after each joint is solved.
        """
        # -- prerequisites: production data and processed logs --------------
        if self.inputs.get("time") is None or len(self.inputs["time"]) == 0:
            print("Corrosion calibration skipped: no production data loaded.")
            return None
        if not self.outputs.get("processedLogs"):
            print("Corrosion calibration skipped: no processed logs available.")
            return None

        # -- run the per-joint calibration ----------------------------------
        opt = OptCO2Corrosion(
            self.inputs,
            self.outputs,
            self.corrosion_models,
            self.co2_models,
            self.VLP,
            esp_joint_start_idx=self.inputs.get("esp_joint_start_idx", 0),
            param_store_path=self._corrosion_opt_params_path(),
        )
        return opt.calibrate(progress_callback=progress_callback)

    def _load_latest_opt_params(self, n_active_joints, esp_joint_start_idx):
        """Return ``(latest_interval_params, error)`` from the persisted store.

        ``latest_interval_params`` is the per-active-joint list (each a dict with
        A, B, C, D, E) for the most recent interval, or ``(None, message)`` when
        the store is missing or incompatible.  Prediction requires that
        optimization has been run, so a missing store is an error.
        """
        path = self._corrosion_opt_params_path()
        if not path or not os.path.exists(path):
            return None, "No optimized parameters found. Run Optimize first."
        try:
            with open(path, "r", encoding="utf-8") as f:
                stored = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None, "Could not read optimized parameters. Re-run Optimize."

        intervals = stored.get("intervals")
        if (
            not isinstance(intervals, list)
            or not intervals
            or stored.get("esp_joint_start_idx") != esp_joint_start_idx
        ):
            return None, "Optimized parameters are incompatible with this well. Re-run Optimize."

        latest = intervals[-1].get("params") if isinstance(intervals[-1], dict) else None
        if not isinstance(latest, list) or len(latest) != n_active_joints:
            return None, "Optimized parameter set is incomplete. Re-run Optimize."
        return latest, None

    def _latest_processed_log(self):
        """Return ``(latest_date, processed_df, error)`` for the newest dated log."""
        processed_logs = self.outputs.get("processedLogs") or []
        selected = self.inputs.get("selectedLogs") or []
        logs_metadata = self.inputs.get("logs_metadata") or {}
        if not processed_logs or not selected:
            return None, None, "No processed logs available. Process logs first."

        # -- pair each selected log with its metadata date ------------------
        dated = []
        for i, name in enumerate(selected):
            if i >= len(processed_logs):
                break
            info = logs_metadata.get(name) or {}
            stored_date = (info.get("date") or "").strip()
            try:
                parsed = datetime.strptime(stored_date, "%Y-%m-%d")
            except ValueError:
                continue
            dated.append((parsed, processed_logs[i]))

        if not dated:
            return None, None, "No dated processed logs available. Set log dates first."

        # -- newest log is the prediction starting point --------------------
        dated.sort(key=lambda pair: pair[0])
        latest_date, latest_df = dated[-1]
        return latest_date, latest_df, None

    def _coarsen_prediction_window(self, pen=3, predecimate_bin_hours=24):
        """Coarsen the loaded production window in one pass (log-date agnostic).

        Unlike :meth:`_coarsen_production_data`, there are no log-date boundaries
        inside a latest-log -> now window, so the whole window is coarsened
        together.  Also yields tz-naive ``datetime64`` (via ``.values``) so the
        window aligns with the naive boundaries handed to the context builder.
        """
        flow = self.inputs.get("flow")
        if flow is None or len(flow) == 0:
            return

        # -- assemble aligned series, then change-point coarsen -------------
        times = pd.to_datetime(self.inputs["time"])
        flow_df = pd.DataFrame({"datetime": times, "value": self.inputs["flow"]})
        pressure_df = pd.DataFrame({"datetime": times, "value": self.inputs["pressure"]})
        temperature_df = pd.DataFrame({"datetime": times, "value": self.inputs["temperature"]})
        try:
            flow_df, pressure_df, temperature_df = coarsen_timeseries_by_change_point(
                flow_df,
                pressure_df,
                temperature_df,
                pen=pen,
                predecimate_bin_hours=predecimate_bin_hours,
            )
        except Exception:
            return

        self.inputs["time"] = flow_df["datetime"].values
        self.inputs["flow"] = flow_df["value"].values
        self.inputs["pressure"] = pressure_df["value"].values
        self.inputs["temperature"] = temperature_df["value"].values

    def predict_remaining_thickness(self):
        """Predict remaining wall thickness per joint from the latest log to now.

        Uses the *latest* interval's optimized parameters (and their sign E)
        persisted by :meth:`optimize_models`, integrates the calibrated corrosion
        model over the production data between the latest log date and now, and
        applies the resulting (signed) bore change to the latest log's measured
        bore.  The sign is carried forward, so a joint whose latest interval fit
        a negative rate predicts the bore continuing in that direction.

        Requires that optimization has been run; returns an
        ``{"status": "error", "message": ...}`` dict otherwise.  On success the
        per-joint result is stored in ``outputs["predictedRemainingThickness"]``.
        """
        # -- joint bookkeeping ----------------------------------------------
        well_tally = self.inputs["well_tally"]
        n_total_joints = len(well_tally)
        esp_joint_start_idx = self.inputs.get("esp_joint_start_idx", 0)
        n_active_joints = n_total_joints - esp_joint_start_idx

        # -- require persisted optimized params (latest interval) -----------
        latest_params, error = self._load_latest_opt_params(n_active_joints, esp_joint_start_idx)
        if error:
            return {"status": "error", "message": error}

        # -- find the latest processed log + its date -----------------------
        latest_date, latest_log_df, error = self._latest_processed_log()
        if error:
            return {"status": "error", "message": error}

        # -- production window [latest log -> now] --------------------------
        now = datetime.now()
        if now <= latest_date:
            return {
                "status": "error",
                "message": "Latest log date is not in the past; nothing to predict.",
            }
        self.inputs["start_time"] = latest_date.strftime("%Y-%m-%d %H:%M:%S")
        self.inputs["end_time"] = now.strftime("%Y-%m-%d %H:%M:%S")
        self.get_production_data(coarsen=False)
        self._coarsen_prediction_window()
        if self.inputs.get("time") is None or len(self.inputs["time"]) == 0:
            return {
                "status": "error",
                "message": "No production data between the latest log and now.",
            }

        # -- normalise window timestamps to tz-naive (match boundaries) -----
        window_times = pd.DatetimeIndex(pd.to_datetime(self.inputs["time"]))
        if window_times.tz is not None:
            window_times = window_times.tz_convert("UTC").tz_localize(None)
        self.inputs["time"] = window_times.values

        # -- apply latest-interval A, B, C, D per joint; keep sign E --------
        sign_by_active = {}
        for active_idx in range(n_active_joints):
            entry = latest_params[active_idx] if isinstance(latest_params[active_idx], dict) else {}
            self.corrosion_models[active_idx].update_parameters(
                {
                    name: float(entry[name])
                    for name in ("A", "B", "C", "D")
                    if entry.get(name) is not None
                }
            )
            sign_by_active[active_idx] = float(entry.get("E", 1.0))

        # -- single forward window context [latest log -> now] --------------
        context = build_prod_corrosion_context(
            well_tally,
            self.inputs,
            self.VLP,
            self.co2_models,
            esp_joint_start_idx=esp_joint_start_idx,
            verbose=False,
            boundaries=[latest_date, now],
        )
        if context["degenerate"] or not context["intervals"]:
            return {
                "status": "error",
                "message": "Could not build a prediction window from production data.",
            }
        interval = context["intervals"][0]
        if interval.get("n_eff_steps", 0) == 0:
            return {
                "status": "error",
                "message": (
                    "No production data after the latest log; cannot compute "
                    "predicted corrosion."
                ),
            }
        duration_yr = interval["total_duration_yr"]

        # -- per-joint signed corroded [mm] + rate over the window ----------
        corroded_mm = np.full(n_total_joints, np.nan)
        rate_mm_yr = np.full(n_total_joints, np.nan)
        for active_idx in range(n_active_joints):
            total_idx = esp_joint_start_idx + active_idx
            raw_corroded_mm = corroded_mm_for_interval(
                interval, active_idx, self.corrosion_models[active_idx]
            )
            signed_corroded_mm = sign_by_active[active_idx] * raw_corroded_mm
            corroded_mm[total_idx] = signed_corroded_mm
            rate_mm_yr[total_idx] = signed_corroded_mm / duration_yr if duration_yr > 0 else 0.0

        # -- remaining wall thickness from the latest log bore (radial) -----
        # The DLD corrosion_rate is a one-sided penetration and the calibration
        # target is now a radial bore change, so "Corroded [mm]" is a one-sided
        # (radial) wall loss.  Hence: predicted_ir = latest max IR + corroded;
        # remaining wall = nominal OR - predicted_ir.
        od_nominal_inch = np.array([float(e.get("OD")) for e in well_tally], dtype=float)
        nominal_or_inch = od_nominal_inch / 2.0
        latest_max_ir_inch = np.full(n_total_joints, np.nan)
        log_max_ir_inch = latest_log_df["Max. Radius [inch]"].values.astype(float)
        n_fill = min(n_total_joints, len(log_max_ir_inch))
        latest_max_ir_inch[:n_fill] = log_max_ir_inch[:n_fill]

        predicted_ir_inch = latest_max_ir_inch + corroded_mm / 25.4
        remaining_wall_mm = (nominal_or_inch - predicted_ir_inch) * 25.4

        # -- assemble result DataFrame --------------------------------------
        latest_str = latest_date.strftime("%Y-%m-%d")
        now_str = now.strftime("%Y-%m-%d")
        window = f"({latest_str} -> {now_str})"
        result_df = pd.DataFrame(
            {
                "Joint No.": context["joint_labels"],
                "Latest log IR [inch]": np.round(latest_max_ir_inch, 4),
                f"{PREDICTED_WALL_THICKNESS_CHANGE_RATE_PREFIX} {window}": np.round(rate_mm_yr, 5),
                f"{WALL_THICKNESS_CHANGE_PREFIX} {window}": np.round(corroded_mm, 5),
                f"Predicted IR [inch] ({now_str})": np.round(predicted_ir_inch, 4),
                f"Remaining wall thickness [mm] ({now_str})": np.round(remaining_wall_mm, 4),
            },
            index=range(n_total_joints),
        )

        self.outputs["predictedRemainingThickness"] = result_df
        print(
            f"Corrosion prediction complete: {n_active_joints} joints, "
            f"window {latest_str} -> {now_str}."
        )
        return {
            "status": "ok",
            "latest_log_date": latest_str,
            "end_date": now_str,
            "n_joints": int(n_active_joints),
        }

    def predict_years_to_min_thickness(self, min_thickness_by_od):
        """Predict years until each casing size reaches its minimum thickness.

        Projects the recent corrosion trend forward linearly: the per-joint
        annual corrosion rate is taken from the *calibrated* DLD model run over
        the **last 12 months** of production data, and the current remaining
        wall is the predicted bore *now* (latest log + corrosion since).  For
        each casing size the top 5 worst (soonest) joints are ranked; the
        soonest sets the casing's summary result::

            years_to_min = (remaining_wall_now_mm - min_thickness_mm)
                           / annual_corrosion_rate_mm_yr

        Parameters
        ----------
        min_thickness_by_od : dict
            Minimum allowable wall thickness [mm] keyed by nominal casing OD
            [inch].  Keys may be floats or strings; only ODs present here are
            evaluated.  These come from the dashboard Wall thickness inputs.

        Returns
        -------
        dict
            ``{"status": "ok", ...}`` with a JSON-safe ``per_casing`` list and a
            ``per_joint`` table, or ``{"status": "error", "message": ...}`` when
            a prerequisite (optimization, processed logs, production) is missing.
        """
        # -- normalise the per-OD minimum-thickness lookup ------------------
        min_by_key = {}
        for raw_key, raw_val in (min_thickness_by_od or {}).items():
            try:
                min_by_key[f"{float(raw_key):.4f}"] = float(raw_val)
            except (TypeError, ValueError):
                continue
        if not min_by_key:
            return {
                "status": "error",
                "message": "No minimum thickness provided. Enter a value for at "
                "least one casing in the dashboard Wall thickness table.",
            }

        # -- baseline: remaining wall now per joint (reuse Predict) ---------
        pred_result = self.predict_remaining_thickness()
        if pred_result.get("status") != "ok":
            return pred_result
        pred_df = self.outputs.get("predictedRemainingThickness")
        if pred_df is None or getattr(pred_df, "empty", True):
            return {
                "status": "error",
                "message": "Could not determine current remaining wall thickness.",
            }
        remaining_cols = [
            c for c in pred_df.columns if str(c).startswith("Remaining wall thickness [mm]")
        ]
        if not remaining_cols:
            return {
                "status": "error",
                "message": "Could not determine current remaining wall thickness.",
            }
        remaining_now_mm = np.asarray(pred_df[remaining_cols[0]].values, dtype=float)

        # -- joint bookkeeping + calibrated params --------------------------
        well_tally = self.inputs["well_tally"]
        n_total_joints = len(well_tally)
        esp_joint_start_idx = self.inputs.get("esp_joint_start_idx", 0)
        n_active_joints = n_total_joints - esp_joint_start_idx
        joint_labels = [e.get("Joint", str(i + 1)) for i, e in enumerate(well_tally)]

        latest_params, error = self._load_latest_opt_params(n_active_joints, esp_joint_start_idx)
        if error:
            return {"status": "error", "message": error}

        # -- annual rate window [now - 12 months -> now] --------------------
        now = datetime.now()
        year_ago = now - timedelta(days=365)
        self.inputs["start_time"] = year_ago.strftime("%Y-%m-%d %H:%M:%S")
        self.inputs["end_time"] = now.strftime("%Y-%m-%d %H:%M:%S")
        self.get_production_data(coarsen=False)
        self._coarsen_prediction_window()
        if self.inputs.get("time") is None or len(self.inputs["time"]) == 0:
            return {
                "status": "error",
                "message": "No production data in the last 12 months.",
            }

        # -- normalise window timestamps to tz-naive (match boundaries) -----
        window_times = pd.DatetimeIndex(pd.to_datetime(self.inputs["time"]))
        if window_times.tz is not None:
            window_times = window_times.tz_convert("UTC").tz_localize(None)
        self.inputs["time"] = window_times.values

        # -- apply latest-interval A, B, C, D per joint; keep sign E --------
        sign_by_active = {}
        for active_idx in range(n_active_joints):
            entry = latest_params[active_idx] if isinstance(latest_params[active_idx], dict) else {}
            self.corrosion_models[active_idx].update_parameters(
                {
                    name: float(entry[name])
                    for name in ("A", "B", "C", "D")
                    if entry.get(name) is not None
                }
            )
            sign_by_active[active_idx] = float(entry.get("E", 1.0))

        # -- single trailing-year context -> per-joint annual rate ----------
        context = build_prod_corrosion_context(
            well_tally,
            self.inputs,
            self.VLP,
            self.co2_models,
            esp_joint_start_idx=esp_joint_start_idx,
            verbose=False,
            boundaries=[year_ago, now],
        )
        if context["degenerate"] or not context["intervals"]:
            return {
                "status": "error",
                "message": "Could not build a 12-month window from production data.",
            }
        interval = context["intervals"][0]
        if interval.get("n_eff_steps", 0) == 0:
            return {
                "status": "error",
                "message": "No usable production data in the last 12 months.",
            }
        duration_yr = interval["total_duration_yr"]

        rate_mm_yr = np.full(n_total_joints, np.nan)
        for active_idx in range(n_active_joints):
            total_idx = esp_joint_start_idx + active_idx
            raw_corroded_mm = corroded_mm_for_interval(
                interval, active_idx, self.corrosion_models[active_idx]
            )
            signed_corroded_mm = sign_by_active[active_idx] * raw_corroded_mm
            rate_mm_yr[total_idx] = signed_corroded_mm / duration_yr if duration_yr > 0 else 0.0

        # -- JSON-safe rounding helpers -------------------------------------
        def _safe(x, ndigits):
            return None if (x is None or np.isnan(x) or np.isinf(x)) else round(float(x), ndigits)

        def _years_sort_key(years_to_min_yr):
            """Finite years first (ascending); infinite last."""
            if np.isinf(years_to_min_yr):
                return (1, float("inf"))
            return (0, float(years_to_min_yr))

        # -- group joints by casing OD, rank top 5 soonest -------------------
        groups = {}
        group_order = []
        for total_idx, entry in enumerate(well_tally):
            od_raw = entry.get("OD")
            if od_raw is None:
                continue
            od_inch = float(od_raw)
            key = f"{od_inch:.4f}"
            if key not in groups:
                groups[key] = {"od_inch": od_inch, "joints": []}
                group_order.append(key)
            groups[key]["joints"].append(total_idx)

        per_casing = []
        for key in group_order:
            if key not in min_by_key:
                continue  # no minimum entered for this casing -> leave untouched
            min_mm = min_by_key[key]
            candidates = []
            for total_idx in groups[key]["joints"]:
                t_cur_mm = (
                    remaining_now_mm[total_idx] if total_idx < len(remaining_now_mm) else np.nan
                )
                r_mm_yr = rate_mm_yr[total_idx]
                if np.isnan(t_cur_mm) or np.isnan(r_mm_yr):
                    continue
                if t_cur_mm <= min_mm:
                    years_to_min_yr = 0.0
                elif r_mm_yr <= 0 or not np.isfinite(r_mm_yr):
                    years_to_min_yr = np.inf
                else:
                    years_to_min_yr = (t_cur_mm - min_mm) / r_mm_yr
                candidates.append(
                    {
                        "years_to_min_yr": years_to_min_yr,
                        "joint": joint_labels[total_idx],
                        "remaining_now_mm": t_cur_mm,
                        "rate_mm_yr": r_mm_yr,
                    }
                )
            if not candidates:
                continue  # no joint with both a valid rate and remaining wall

            candidates.sort(key=lambda c: _years_sort_key(c["years_to_min_yr"]))
            top_joints = []
            for rank, cand in enumerate(candidates[:5], start=1):
                y = cand["years_to_min_yr"]
                top_joints.append(
                    {
                        "rank": rank,
                        "joint": cand["joint"],
                        "remaining_now_mm": round(float(cand["remaining_now_mm"]), 4),
                        "rate_mm_yr": round(float(cand["rate_mm_yr"]), 5),
                        "years_to_min_yr": None if not np.isfinite(y) else round(float(y), 2),
                    }
                )

            worst = candidates[0]
            worst_y = worst["years_to_min_yr"]
            per_casing.append(
                {
                    "od_inch": round(groups[key]["od_inch"], 4),
                    "min_thickness_mm": round(min_mm, 4),
                    "years_to_min_yr": (
                        None if not np.isfinite(worst_y) else round(float(worst_y), 2)
                    ),
                    "limiting_joint": worst["joint"],
                    "remaining_now_mm": round(float(worst["remaining_now_mm"]), 4),
                    "rate_mm_yr": round(float(worst["rate_mm_yr"]), 5),
                    "top_joints": top_joints,
                }
            )

        # -- per-joint detail table -----------------------------------------
        per_joint = {
            "Joint No.": joint_labels,
            "OD [inch]": [
                round(float(e.get("OD")), 4) if e.get("OD") is not None else None
                for e in well_tally
            ],
            "Remaining wall thickness now [mm]": [_safe(x, 4) for x in remaining_now_mm],
            ANNUAL_WALL_THICKNESS_CHANGE_RATE_COL: [_safe(x, 5) for x in rate_mm_yr],
        }

        print(
            f"Years-to-min forecast complete: {len(per_casing)} casing size(s), "
            f"window {year_ago.strftime('%Y-%m-%d')} -> {now.strftime('%Y-%m-%d')}."
        )
        return {
            "status": "ok",
            "now": now.strftime("%Y-%m-%d"),
            "rate_window": [year_ago.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")],
            "n_casings": len(per_casing),
            "per_casing": per_casing,
            "per_joint": per_joint,
        }

    def inches_to_meters(self, inches):
        """Convert inches to meters."""
        return inches * 0.0254
