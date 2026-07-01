"""Celery Tasks Module."""

import os
import sys

sys.path.append(os.path.join(os.getcwd(), "src"))
from celery import Celery

from gemini_application.chatpopup.chatpopup import ChatPopup
from gemini_application.esp.esp import ESPApp
from gemini_application.injectionwell.injectionwell_monitoring import InjectionWellMonitoring
from gemini_application.productionwell.productionwell_performance import ProductionWellPerformance

celery = Celery(
    "gemini-celery-app",
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379"),
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379"),
)


@celery.task(name="productionwellperformance_app_calculate_vlp_ipr")
def productionwellperformance_app_calculate_vlp_ipr(
    project_folder_path, project_name, well_name, inputs
):
    """Calculate VLP and IPR for production well performance analysis."""
    app_instance = ProductionWellPerformance()

    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(well_name)

    app_instance.init_parameters(inputs["parameters"])
    app_instance.set_input(inputs["boundary"])
    app_instance.calculate()
    app_instance.get_solution()

    # preparing output
    inputs = app_instance.get_input()
    outputs = app_instance.get_output()

    if outputs["sol_flow"]:
        results = {
            "bottomhole_pressure_from_reservoir": outputs["pbh_res"].tolist(),
            "bottomhole_pressure_from_well": outputs["pbh_well"].tolist(),
            "intake_pressure": outputs["intake_pressure"].tolist(),
            "discharge_pressure": outputs["discharge_pressure"].tolist(),
            "flow": inputs["flow"].tolist(),
            "reservoir_pressure": inputs["reservoir_pressure"].tolist(),
            "sol_flow": outputs["sol_flow"].tolist(),
            "sol_pbh": outputs["sol_pbh"].tolist(),
            "sol_esp_head": outputs["sol_esp_head"].tolist(),
            "sol_esp_power": outputs["sol_esp_power"].tolist(),
            "sol_esp_eff": outputs["sol_esp_eff"].tolist(),
            "sol_intake_pressure": outputs["sol_intake_pressure"].tolist(),
            "sol_discharge_pressure": outputs["sol_discharge_pressure"].tolist(),
        }
    else:
        results = {
            "bottomhole_pressure_from_reservoir": outputs["pbh_res"].tolist(),
            "bottomhole_pressure_from_well": outputs["pbh_well"].tolist(),
            "intake_pressure": outputs["intake_pressure"].tolist(),
            "discharge_pressure": outputs["discharge_pressure"].tolist(),
            "flow": inputs["flow"].tolist(),
            "reservoir_pressure": inputs["reservoir_pressure"].tolist(),
            "sol_flow": None,
            "sol_pbh": None,
            "sol_esp_head": None,
            "sol_esp_power": None,
            "sol_esp_eff": None,
            "sol_intake_pressure": None,
            "sol_discharge_pressure": None,
        }

    return results


@celery.task(name="injectionwellmonitoring_app_calculate_hall_integral")
def injectionwellmonitoring_app_calculate_hall_integral(
    project_folder_path, project_name, well_name, inputs
):
    """Calculate Hall integral for injection well monitoring."""
    app_instance = InjectionWellMonitoring()

    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(well_name)

    app_instance.init_parameters(inputs["parameters"])
    app_instance.set_input(inputs["boundary"])
    app_instance.get_data()
    app_instance.calculate_hall_integral()

    inputs = app_instance.get_input()
    outputs = app_instance.get_output()

    if len(outputs["cumulative_flow"]) > 1:
        results = {
            "cumulative_flow": outputs["cumulative_flow"].tolist(),
            "hall_integral": outputs["hall_integral"].tolist(),
            "hall_derivative_numerical": outputs["hall_derivative_numerical"].tolist(),
        }
    else:
        results = {"cumulative_flow": [], "hall_integral": [], "hall_derivative_numerical": []}

    return results


@celery.task(name="injectionwellmonitoring_app_calculate_skin_lines")
def injectionwellmonitoring_app_calculate_skin_lines(
    project_folder_path, project_name, well_name, inputs
):
    """Calculate skin lines for injection well monitoring."""
    app_instance = InjectionWellMonitoring()

    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(well_name)

    app_instance.init_parameters(inputs["parameters"])
    app_instance.set_input(inputs["boundary"])
    app_instance.get_data()
    app_instance.calculate_skin_lines()

    inputs = app_instance.get_input()
    outputs = app_instance.get_output()

    results = {
        "starttime": inputs["start_time"],
        "endtime": inputs["end_time"],
        "min_flow_plot": inputs["min_flow_plot"],
        "max_flow_plot": inputs["max_flow_plot"],
        "no_interval_flow_plot": inputs["no_interval_flow_plot"],
        "min_skin_plot": inputs["min_skin_plot"],
        "max_skin_plot": inputs["max_skin_plot"],
        "no_interval_skin_plot": inputs["no_interval_skin_plot"],
        "wellbore_radius": inputs["wellbore_radius"],
        "max_flow_rate": inputs["max_flow_rate"],
        "max_pressure": inputs["max_pressure"],
        "realTime_time": inputs["time"].tolist(),
        "realTime_flow": inputs["flow"].tolist(),
        "realTime_pressure": inputs["wellhead_pressure"].tolist(),
        "injection_pressure": outputs["injection_pressure"],
        "max_cal_P_inj": outputs["max_cal_P_inj"],
        "skin_array": inputs["skin_array"].tolist(),
        "flow_array": inputs["flow_array"].tolist(),
    }

    return results


@celery.task(name="wellintegrity_app_process_caliper_logs")
def wellintegrity_app_process_caliper_logs(project_folder_path, project_name, well_name, inputs):
    """Process caliper logs for well integrity monitoring."""
    import json
    import os

    import pandas as pd

    from gemini_application.wims.corrosion_model import CO2CorrosionApplication

    app_instance = CO2CorrosionApplication()

    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(well_name)

    selected_logs = inputs["selected_logs"]

    project_data_folder = os.path.join(project_folder_path, project_name + "/wims_data")
    well_data_folder = os.path.join(project_data_folder, well_name)
    processed_folder = os.path.join(well_data_folder, "processed_logs")

    if not os.path.exists(processed_folder):
        os.makedirs(processed_folder)

    approved_joints_folder = os.path.join(well_data_folder, "approved_joints")
    use_approved_joints = inputs.get("use_approved_joints", False)

    all_approved_joints = None
    if use_approved_joints:
        all_approved_joints = []
        for log_name in selected_logs:
            approved_file = os.path.join(
                approved_joints_folder,
                log_name.replace(".las", "_approved_joints.json"),
            )
            if os.path.exists(approved_file):
                with open(approved_file, "r") as f:
                    all_approved_joints.append(json.load(f))
            else:
                all_approved_joints.append(None)

    app_instance.set_input({"selectedLogs": selected_logs})
    app_instance.init_parameters()
    app_instance.get_data()
    app_instance.process_caliper_logs(
        approved_joints=all_approved_joints,
        qa_log_dir=processed_folder,
    )

    outputs = app_instance.get_output()
    processed_logs_data = outputs.get("processedLogs", [])

    def make_json_serializable(data):
        if isinstance(data, pd.DataFrame):
            return make_json_serializable(data.to_dict(orient="records"))
        elif isinstance(data, list):
            return [make_json_serializable(entry) for entry in data]
        elif isinstance(data, dict):
            return {k: make_json_serializable(v) for k, v in data.items()}
        elif data is None:
            return ""
        return data

    processed_logs_dict = {}
    for i, log_name in enumerate(selected_logs):
        if i < len(processed_logs_data):
            processed_data = make_json_serializable(processed_logs_data[i])
            processed_logs_dict[log_name] = processed_data

            processed_file_name = log_name.replace(".las", "_processed.json")
            processed_file_path = os.path.join(processed_folder, processed_file_name)
            with open(processed_file_path, "w") as f:
                json.dump(processed_data, f, indent=2)
        else:
            processed_logs_dict[log_name] = []

    # Pre-extract per-joint finger data for fast detail view
    finger_data_folder = os.path.join(well_data_folder, "finger_data")
    if not os.path.exists(finger_data_folder):
        os.makedirs(finger_data_folder)

    uploaded_logs = app_instance.inputs["uploadedLogs"]
    for i, log_name in enumerate(selected_logs):
        if i >= len(processed_logs_data):
            continue
        caliper_df = uploaded_logs["data"][i]
        processed_df = processed_logs_data[i]
        finger_name_val = (uploaded_logs.get("finger_name") or [None])[i] or "D"
        finger_units_val = (uploaded_logs.get("finger_units") or [None])[i] or ""

        _extract_finger_data_for_log(
            caliper_df,
            processed_df,
            log_name,
            finger_name_val,
            finger_units_val,
            finger_data_folder,
        )

    results = {"processed_logs": selected_logs, "results": {"processedLogs": processed_logs_dict}}

    return results


def _extract_finger_data_for_log(
    caliper_df, processed_df, log_name, finger_name, finger_units, finger_data_folder
):
    """Extract and save per-joint finger data as small JSON files."""
    import json
    import re

    import numpy as np
    import pandas as pd

    if isinstance(processed_df, pd.DataFrame):
        records = processed_df.to_dict(orient="records")
    elif isinstance(processed_df, list):
        records = processed_df
    else:
        return

    finger_regex = rf"^{re.escape(finger_name)}\d{{1,2}}$"
    finger_cols = [c for c in caliper_df.columns if re.match(finger_regex, c)]
    if not finger_cols:
        return

    for joint_idx, row in enumerate(records):
        top_depth = row.get("Top Depth [m]")
        bottom_depth = row.get("Bottom Depth [m]")
        if top_depth is None or bottom_depth is None:
            continue

        try:
            top_depth = float(top_depth)
            bottom_depth = float(bottom_depth)
        except (TypeError, ValueError):
            continue

        joint_df = caliper_df.loc[top_depth:bottom_depth]
        if joint_df.empty:
            continue

        finger_df = joint_df[finger_cols].apply(pd.to_numeric, errors="coerce")
        if finger_units in ("double_radius", "diameter"):
            finger_df = finger_df / 2

        depths = finger_df.index.values.astype(float).tolist()
        fingers = {col: finger_df[col].tolist() for col in finger_cols}
        row_max = finger_df.max(axis=1).tolist()
        row_min = finger_df.min(axis=1).tolist()
        row_mean = finger_df.mean(axis=1).tolist()
        max_finger = finger_df.idxmax(axis=1).tolist()
        min_finger = finger_df.idxmin(axis=1).tolist()

        mxrd = None
        if "MXRD" in joint_df.columns:
            mxrd_series = pd.to_numeric(joint_df["MXRD"], errors="coerce")
            if finger_units in ("double_radius", "diameter"):
                mxrd_series = mxrd_series / 2
            mxrd = mxrd_series.tolist()

        mnrd = None
        if "MNRD" in joint_df.columns:
            mnrd_series = pd.to_numeric(joint_df["MNRD"], errors="coerce")
            if finger_units in ("double_radius", "diameter"):
                mnrd_series = mnrd_series / 2
            mnrd = mnrd_series.tolist()

        joint_data = {
            "depths": depths,
            "fingers": fingers,
            "max": row_max,
            "min": row_min,
            "mean": row_mean,
            "max_finger": max_finger,
            "min_finger": min_finger,
            "mxrd": mxrd,
            "mnrd": mnrd,
            "finger_cols": finger_cols,
            "top_depth": top_depth,
            "bottom_depth": bottom_depth,
        }

        def _default_serializer(obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if obj is None or (isinstance(obj, float) and np.isnan(obj)):
                return None
            return obj

        file_name = f"{log_name}_joint_{joint_idx}.json"
        file_path = os.path.join(finger_data_folder, file_name)
        with open(file_path, "w") as f:
            json.dump(joint_data, f, default=_default_serializer)


@celery.task(name="wellintegrity_app_detect_joints")
def wellintegrity_app_detect_joints(project_folder_path, project_name, well_name, inputs):
    """Detect joint candidates for QA/QC review before processing caliper logs."""
    import json
    import os

    import numpy as np

    from gemini_application.wims.corrosion_model import CO2CorrosionApplication

    def _make_serializable(obj):
        """Recursively convert numpy types to native Python for JSON."""
        if isinstance(obj, dict):
            return {k: _make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [_make_serializable(item) for item in obj]
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    app_instance = CO2CorrosionApplication()

    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(well_name)

    selected_logs = inputs["selected_logs"]

    project_data_folder = os.path.join(project_folder_path, project_name + "/wims_data")
    well_data_folder = os.path.join(project_data_folder, well_name)
    detected_folder = os.path.join(well_data_folder, "detected_joints")
    approved_joints_folder = os.path.join(well_data_folder, "approved_joints")

    if not os.path.exists(detected_folder):
        os.makedirs(detected_folder)

    all_results = {}

    for log_name in selected_logs:
        approved_file = os.path.join(
            approved_joints_folder,
            log_name.replace(".las", "_approved_joints.json"),
        )
        if os.path.exists(approved_file):
            os.remove(approved_file)

        task_inputs = {"selectedLogs": [log_name]}
        app_instance.set_input(task_inputs)
        app_instance.init_parameters()
        app_instance.get_data()

        log_info_entry = app_instance.inputs.get("logs_metadata", {}).get(log_name, {})
        detection_params = {}
        if log_info_entry.get("min_marker_score") is not None:
            detection_params["min_marker_score"] = log_info_entry["min_marker_score"]
        if log_info_entry.get("min_gradient_score") is not None:
            detection_params["min_gradient_score"] = log_info_entry["min_gradient_score"]
        app_instance.detect_joints(
            detection_params=[detection_params] if detection_params else None
        )

        detected = app_instance.outputs.get("detectedJoints", [])
        log_result = (
            detected[0]
            if detected
            else {
                "method": "unknown",
                "candidates": [],
                "chart_depths": [],
                "chart_values": [],
                "joint_boundaries": [],
            }
        )

        log_result = _make_serializable(log_result)

        detected_file_name = log_name.replace(".las", "_detected_joints.json")
        detected_file_path = os.path.join(detected_folder, detected_file_name)
        with open(detected_file_path, "w") as f:
            json.dump(log_result, f, indent=2)

        frontend_result = {
            "method": log_result.get("method", "unknown"),
            "candidates": log_result.get("candidates", []),
            "joint_boundaries": log_result.get("joint_boundaries", []),
            "chart_depths": log_result.get("chart_depths", []),
            "chart_values": log_result.get("chart_values", []),
        }
        all_results[log_name] = frontend_result

    return {"detected_joints": all_results}


@celery.task(bind=True, name="wellintegrity_app_optimize_corrosion")
def wellintegrity_app_optimize_corrosion(self, project_folder_path, project_name, well_name):
    """Calibrate per-joint CO2 corrosion parameters against caliper-log rates.

    Loads the well's production data and processed caliper logs, then runs the
    per-joint SLSQP calibration (``CO2CorrosionApplication.optimize_models`` ->
    ``OptCO2Corrosion.calibrate``).  Reports live progress via ``PROGRESS``
    state updates (one per solved joint) and returns the optimization summary
    plus the measured / un-calibrated / calibrated corrosion-rate tables and
    per-joint before/after errors for display.
    """
    import glob
    import json
    import os

    import numpy as np
    import pandas as pd

    from gemini_application.wims.corrosion_model import CO2CorrosionApplication

    # -- helper: DataFrame -> JSON-safe {col: [vals]} -----------------------
    def _df_to_json_columns(df):
        if df is None or getattr(df, "empty", True):
            return None
        data = {}
        for col in df.columns:
            vals = df[col].tolist()
            vals = [
                None if (isinstance(x, float) and (np.isnan(x) or np.isinf(x))) else x for x in vals
            ]
            data[col] = vals
        return data

    # -- helper: coerce numpy scalars in the summary to native types --------
    def _clean_summary(summary):
        cleaned = {}
        for key, value in (summary or {}).items():
            if key == "per_joint":
                continue  # returned separately at top level
            if isinstance(value, np.floating):
                value = float(value)
            elif isinstance(value, np.integer):
                value = int(value)
            cleaned[key] = value
        return cleaned

    app_instance = CO2CorrosionApplication()
    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(well_name)

    # -- discover processed caliper logs on disk (name/df in matching order)
    project_data_folder = os.path.join(project_folder_path, project_name + "/wims_data")
    well_data_folder = os.path.join(project_data_folder, well_name)
    processed_folder = os.path.join(well_data_folder, "processed_logs")

    selected_logs = []
    processed_dfs = []
    if os.path.exists(processed_folder):
        for processed_path in sorted(glob.glob(os.path.join(processed_folder, "*_processed.json"))):
            log_name = os.path.basename(processed_path).replace("_processed.json", ".las")
            try:
                with open(processed_path, "r") as f:
                    records = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(records, list) and records:
                selected_logs.append(log_name)
                processed_dfs.append(pd.DataFrame(records))

    if not processed_dfs:
        return {
            "summary": {"status": "skipped"},
            "message": "No processed caliper logs found. Process logs before optimizing.",
        }

    # -- inputs -> parameters -> production window -> production data -------
    app_instance.set_input({"selectedLogs": selected_logs})
    app_instance.init_parameters()

    window_error = app_instance.set_production_window_from_logs_metadata()
    if window_error:
        return {"summary": {"status": "skipped"}, "message": window_error}

    app_instance.get_production_data(coarsen=True, predecimate_bin_hours=24)
    app_instance.outputs["processedLogs"] = processed_dfs

    # -- report one PROGRESS update per solved joint ------------------------
    def _report_progress(completed, total, per_joint):
        self.update_state(
            state="PROGRESS",
            meta={
                "completed": int(completed),
                "total": int(total),
                "per_joint": per_joint,
            },
        )

    # -- run per-joint calibration ------------------------------------------
    summary = app_instance.optimize_models(progress_callback=_report_progress)
    if summary is None:
        return {
            "summary": {"status": "skipped"},
            "message": "Optimization skipped: missing production data or processed logs.",
        }

    # -- serialise summary + corrosion tables -------------------------------
    outputs = app_instance.get_output()
    result_payload = {
        "summary": _clean_summary(summary),
        "per_joint": summary.get("per_joint", []),
        "measured": _df_to_json_columns(outputs.get("measuredCorrosionRateFromLogs")),
        "modelled_uncalibrated": _df_to_json_columns(outputs.get("modelledCorrosionRate")),
        "modelled_calibrated": _df_to_json_columns(outputs.get("modelledCorrosionRateCalibrated")),
    }

    # -- write a timestamped debug log (full result) for later inspection ---
    try:
        from datetime import datetime

        logs_dir = os.path.join(well_data_folder, "optimization_logs")
        os.makedirs(logs_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(logs_dir, f"corrosion_opt_{stamp}.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "well": well_name,
                    "timestamp": stamp,
                    "task_id": self.request.id,
                    **result_payload,
                },
                f,
                indent=2,
            )
        result_payload["log_file"] = log_path
        print(f"Corrosion optimization log written to {log_path}")
    except OSError as exc:
        print(f"Could not write optimization log: {exc}")

    return result_payload


@celery.task(name="wellintegrity_app_predict_corrosion")
def wellintegrity_app_predict_corrosion(project_folder_path, project_name, well_name):
    """Predict remaining wall thickness per joint from the latest log to now.

    Loads the well's processed caliper logs and the persisted optimized
    parameters, then runs ``CO2CorrosionApplication.predict_remaining_thickness``
    -- which integrates the latest interval's calibrated model over the
    production data between the latest log date and now.  Returns the per-joint
    prediction table (or an error message when optimization has not been run).
    """
    import glob
    import json
    import os

    import numpy as np
    import pandas as pd

    from gemini_application.wims.corrosion_model import CO2CorrosionApplication

    # -- helper: DataFrame -> JSON-safe {col: [vals]} -----------------------
    def _df_to_json_columns(df):
        if df is None or getattr(df, "empty", True):
            return None
        data = {}
        for col in df.columns:
            vals = df[col].tolist()
            vals = [
                None if (isinstance(x, float) and (np.isnan(x) or np.isinf(x))) else x for x in vals
            ]
            data[col] = vals
        return data

    app_instance = CO2CorrosionApplication()
    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(well_name)

    # -- discover processed caliper logs on disk (name/df in matching order)
    project_data_folder = os.path.join(project_folder_path, project_name + "/wims_data")
    well_data_folder = os.path.join(project_data_folder, well_name)
    processed_folder = os.path.join(well_data_folder, "processed_logs")

    selected_logs = []
    processed_dfs = []
    if os.path.exists(processed_folder):
        for processed_path in sorted(glob.glob(os.path.join(processed_folder, "*_processed.json"))):
            log_name = os.path.basename(processed_path).replace("_processed.json", ".las")
            try:
                with open(processed_path, "r") as f:
                    records = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(records, list) and records:
                selected_logs.append(log_name)
                processed_dfs.append(pd.DataFrame(records))

    if not processed_dfs:
        return {
            "status": "error",
            "message": "No processed caliper logs found. Process logs before predicting.",
        }

    # -- inputs -> parameters -> processed logs -----------------------------
    app_instance.set_input({"selectedLogs": selected_logs})
    app_instance.init_parameters()
    app_instance.outputs["processedLogs"] = processed_dfs

    # -- run the prediction (sets its own [latest log -> now] window) -------
    result = app_instance.predict_remaining_thickness()
    if result.get("status") != "ok":
        return {"status": "error", "message": result.get("message", "Prediction failed.")}

    # -- serialise the per-joint prediction table ---------------------------
    outputs = app_instance.get_output()
    return {
        "status": "ok",
        "latest_log_date": result.get("latest_log_date"),
        "end_date": result.get("end_date"),
        "n_joints": result.get("n_joints"),
        "prediction": _df_to_json_columns(outputs.get("predictedRemainingThickness")),
    }


@celery.task(name="wellintegrity_app_forecast_years_to_min")
def wellintegrity_app_forecast_years_to_min(project_folder_path, project_name, well_name, casings):
    """Forecast years until each casing size reaches its minimum thickness.

    Loads the well's processed caliper logs and the persisted optimized
    parameters, then runs
    ``CO2CorrosionApplication.predict_years_to_min_thickness`` -- which projects
    the calibrated model's trailing-12-month corrosion rate forward to estimate
    when each casing size reaches the minimum wall thickness supplied from the
    dashboard.  ``casings`` is a list of ``{"od_inch", "min_thickness_mm"}``
    dicts (the dashboard Wall thickness inputs).
    """
    import glob
    import json
    import os

    import pandas as pd

    from gemini_application.wims.corrosion_model import CO2CorrosionApplication

    app_instance = CO2CorrosionApplication()
    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(well_name)

    # -- discover processed caliper logs on disk (name/df in matching order)
    project_data_folder = os.path.join(project_folder_path, project_name + "/wims_data")
    well_data_folder = os.path.join(project_data_folder, well_name)
    processed_folder = os.path.join(well_data_folder, "processed_logs")

    selected_logs = []
    processed_dfs = []
    if os.path.exists(processed_folder):
        for processed_path in sorted(glob.glob(os.path.join(processed_folder, "*_processed.json"))):
            log_name = os.path.basename(processed_path).replace("_processed.json", ".las")
            try:
                with open(processed_path, "r") as f:
                    records = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(records, list) and records:
                selected_logs.append(log_name)
                processed_dfs.append(pd.DataFrame(records))

    if not processed_dfs:
        return {
            "status": "error",
            "message": "No processed caliper logs found. Process logs before forecasting.",
        }

    # -- inputs -> parameters -> processed logs -----------------------------
    app_instance.set_input({"selectedLogs": selected_logs})
    app_instance.init_parameters()
    app_instance.outputs["processedLogs"] = processed_dfs

    # -- minimum thickness [mm] keyed by casing OD [inch] -------------------
    min_thickness_by_od = {}
    for casing in casings or []:
        if not isinstance(casing, dict):
            continue
        try:
            od_inch = float(casing.get("od_inch"))
            min_mm = float(casing.get("min_thickness_mm"))
        except (TypeError, ValueError):
            continue
        min_thickness_by_od[f"{od_inch:.4f}"] = min_mm

    # -- run the forecast (result is already JSON-safe) ---------------------
    return app_instance.predict_years_to_min_thickness(min_thickness_by_od)


@celery.task(name="esp_app_get_pumphead_data")
def esp_app_get_pumphead_data(project_folder_path, project_name, esp_name, inputs):
    """Calculate pump head curve for ESP analysis."""
    app_instance = ESPApp()

    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(esp_name)

    app_instance.init_parameters()
    app_instance.set_input(inputs["boundary"])

    app_instance.calculate()
    app_instance.get_data()
    app_instance.calculate_pump_head_curve()

    inputs = app_instance.get_input()
    outputs = app_instance.get_output()

    results = {
        "starttime": inputs["start_time"],
        "endtime": inputs["end_time"],
        "realTime_time": outputs["time"].tolist(),
        "realTime_flow": outputs["flow_measured"].tolist(),
        "xValues": [x.tolist() for x in outputs["xValues"]],
        "frequency": outputs["frequency"].tolist(),
        "pump_head": [h for h in outputs["pump_head"]],
        "esp_vlp_head_calculated": outputs["esp_vlp_head_calculated"].tolist(),
        "frequency_measured": outputs["frequency_measured"].tolist(),
        "esp_theoretical_head_calculated": outputs["esp_theoretical_head_calculated"].tolist(),
        "esp_vlp_outlet_pressure_calculated": outputs[
            "esp_vlp_outlet_pressure_calculated"
        ].tolist(),
        "esp_vlp_ipr_inlet_pressure_calculated": outputs[
            "esp_vlp_ipr_inlet_pressure_calculated"
        ].tolist(),
        "inlet_pressure_measured": outputs["inlet_pressure_measured"].tolist(),
        "esp_theoretical_outlet_pressure_calculated": outputs[
            "esp_theoretical_outlet_pressure_calculated"
        ].tolist(),
    }

    return results


@celery.task(name="esp_app_calibrate_pumphead_data")
def esp_app_calibrate_pumphead_data(project_folder_path, project_name, esp_name, inputs):
    """Calibrate ESP pump head data."""
    app_instance = ESPApp()

    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(esp_name)
    app_instance.init_parameters()
    app_instance.set_input(inputs["boundary"])

    app_instance.calibrate_esp_head_simple()

    inputs = app_instance.get_input()
    outputs = app_instance.get_output()
    a, b = map(float, outputs["esp_correction_factor"].split(";"))

    results = {"esp_correction_factor": [a, b]}

    return results


def _clean_for_json(value):
    """Convert NaN/Inf values to None for JSON serialization.

    Needed for ML model predictions which can contain NaN/Inf values.
    """
    import numpy as np

    if isinstance(value, (list, np.ndarray)):
        return [
            None if (isinstance(x, float) and (np.isnan(x) or np.isinf(x))) else x for x in value
        ]
    elif isinstance(value, (float, np.floating)):
        return None if (np.isnan(value) or np.isinf(value)) else value
    return value


@celery.task(name="esp_app_predict_failure")
def esp_app_predict_failure(project_folder_path, project_name, esp_name, inputs):
    """Predict ESP failures using ML model."""
    import numpy as np
    import pandas as pd

    app_instance = ESPApp()
    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(esp_name)
    app_instance.init_parameters()
    app_instance.set_input(inputs["boundary"])

    prediction_mode = inputs["boundary"].get("prediction_mode", "forward")
    app_instance.predict_failures(prediction_mode=prediction_mode)

    outputs = app_instance.get_output()

    failure_times = outputs["failure_times"]
    timestamps = None
    if failure_times is not None:
        if isinstance(failure_times, pd.DatetimeIndex):
            timestamps = failure_times.strftime("%Y-%m-%dT%H:%M:%SZ").tolist()
        else:
            timestamps = [pd.to_datetime(t).strftime("%Y-%m-%dT%H:%M:%SZ") for t in failure_times]

    predictions = outputs["failure_predictions"]
    if isinstance(predictions, np.ndarray):
        predictions = predictions.tolist()

    results = {
        "prediction_mode": prediction_mode,
        "prediction_timestamps": timestamps,
        "prediction_probabilities": _clean_for_json(predictions),
        "selected_time": inputs["boundary"].get("selected_time"),
    }

    has_sensor_df = hasattr(app_instance, "_sensor_df_for_plot")
    if has_sensor_df and app_instance._sensor_df_for_plot is not None:
        df = app_instance._sensor_df_for_plot
        sensor_timestamps = df.index.strftime("%Y-%m-%dT%H:%M:%SZ").tolist()
        results["prediction_diagnostic_timestamps"] = sensor_timestamps
        results["prediction_feature_timestamps"] = sensor_timestamps
        results["prediction_preprocessed_sensors"] = {
            col: _clean_for_json(df[col].tolist() if col in df.columns else [])
            for col in [
                "Vibration",
                "ESP Motor temperature",
                "wellhead temperature",
                "wellhead pressure",
                "Brine flow rate",
                "intake pressure ESP",
                "discharge pressure ESP",
            ]
        }

    return results


@celery.task(name="rag_generate_response")
def rag_generate_response(parameters, user_message):
    """Generate AI-powered responses using RAG."""
    print("Celery task called, user_message = ", user_message)
    try:
        app_instance = ChatPopup()

        app_instance.init_parameters(parameters)

        # Takes several minutes to process, ~10 minutes
        response = app_instance.process_prompt(user_message)

        return response
    except Exception as e:
        print(f"ERROR: Exception in rag_generate_response: {e}")
        import traceback

        print(traceback.format_exc())
        raise
