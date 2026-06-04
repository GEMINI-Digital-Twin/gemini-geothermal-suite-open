"""
Well Integrity Monitoring Application Routes.

=============================================

This module handles well integrity assessment and monitoring functionality including caliper log
processing, corrosion analysis, and well integrity assessment.
"""

import glob
import json
import os
from datetime import datetime

import matplotlib
import numpy as np
import pandas as pd
import requests
from flask import Blueprint, current_app, jsonify, request

# Import the same application instance as well_schematics
from gemini_application.wims.co2_corrosion import CO2CorrosionApplication
from gemini_framework.modules.injectionwell.unit import InjectionWellUnit
from gemini_framework.modules.productionwell.unit import ProductionWellUnit
from gemini_interface.blueprint.celerytasks import celery, wellintegrity_app_process_caliper_logs

# Configure matplotlib for non-GUI backend (perfect for server)
matplotlib.use("Agg")

app_wellintegrity_monitoring = Blueprint("app_wellintegrity_monitoring", __name__)

# Application instance set by load_plant(); used by routes that need project path / plant.
app_instance = None


@app_wellintegrity_monitoring.route("/app/wellintegrity/load_plant", methods=["POST"])
def load_plant():
    """Load a plant into the well integrity monitoring application instance."""
    global app_instance
    try:
        if request.json is None:
            return jsonify({"error": "Request body must be JSON"}), 400
        project_name = request.json.get("field_name") or ""
        if not project_name.strip():
            return jsonify({"error": "field_name is required"}), 400
        project_folder_path = current_app.config.get("GEMINI_PROJECT_FOLDER")
        if not project_folder_path:
            return jsonify({"error": "GEMINI_PROJECT_FOLDER not configured"}), 500
        app_instance = CO2CorrosionApplication()
        app_instance.load_plant(project_folder_path, project_name.strip())
        return jsonify({"message": "OK"})
    except Exception as e:
        app_instance = None
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_well_list", methods=["POST"])
def get_well_list():
    """Get list of wells for well integrity monitoring."""
    if app_instance is None:
        return jsonify([])
    well_unit_list = []
    for unit in app_instance.plant.units:
        if isinstance(unit, InjectionWellUnit) or isinstance(unit, ProductionWellUnit):
            well_unit_list.append(unit.name)
    return jsonify(well_unit_list)


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_saved_schematics", methods=["POST"])
def get_saved_schematics():
    """Get list of saved well schematics for the selected well (WIMS card schematic selector)."""
    try:
        selected_well = request.json.get("selected_well")

        if not selected_well:
            return jsonify([])

        # Create schematics folder path
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well, "schematics")

        if not os.path.exists(well_data_folder):
            return jsonify([])

        # Get all JSON files in the schematics folder
        schematic_files = glob.glob(os.path.join(well_data_folder, "*.json"))
        schematic_list = []

        for file_path in schematic_files:
            filename = os.path.basename(file_path)
            # Remove .json extension for display
            schematic_name = filename[:-5] if filename.endswith(".json") else filename
            schematic_list.append({"name": schematic_name, "filename": filename, "path": file_path})

        return jsonify(schematic_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/load_schematic", methods=["POST"])
def load_schematic():
    """Load a specific integrity schematic file for the selected well."""
    try:
        selected_well = request.json.get("selected_well")
        schematic_filename = request.json.get("schematic_filename")

        if not selected_well or not schematic_filename:
            return jsonify({"error": "Missing well name or schematic filename"}), 400

        # Create path to schematic file
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well, "schematics")
        schematic_path = os.path.join(well_data_folder, schematic_filename)

        if not os.path.exists(schematic_path):
            return jsonify({"error": "Schematic file not found"}), 404

        # Load and return the JSON data
        with open(schematic_path, "r") as f:
            schematic_data = json.load(f)

        return jsonify(schematic_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# @app_wellintegrity_monitoring.route("/app/wellintegrity/generate_schematic", methods=["POST"])
# def generate_schematic():
#     """Generate a schematic image from JSON data."""
#     try:
#         schematic_data = request.get_json()

#         # Use caliper_data from request if provided, else fallback to sample
#         caliper_data = schematic_data.get("caliper_data")

#         # caliper_data = caliper_data2

#         well = build_well_from_json(schematic_data)
#         well.draw(
#             show_legend=True, caliper_unit_index=0, show_caliper=True, caliper_data=caliper_data
#         )
#         fig = plt.gcf()
#         buf = io.BytesIO()
#         plt.savefig(buf, format="png", bbox_inches="tight")
#         plt.close(fig)
#         buf.seek(0)
#         img_base64 = base64.b64encode(buf.read()).decode("utf-8")
#         return jsonify({"image_base64": img_base64})
#     except Exception as e:
#         return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/generate_schematic_image", methods=["POST"])
def generate_schematic_image():
    """Proxy route to generate a well schematic image from external backend API.

    URL: (http://185.92.222.87:8001/generate). Also requests annulus information in the same call
    (return_annulus_information=True).
    """
    try:
        schematic_data = request.get_json()
        if schematic_data is None:
            return jsonify({"error": "No JSON body"}), 400

        schematic_data = dict(schematic_data)
        schematic_data["return_annulus_information"] = True
        schematic_data["return_drawn_items"] = True

        backend_url = app_instance.plant.parameters["wims_backend_url"]
        response = requests.post(
            backend_url,
            json=schematic_data,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.ConnectionError:
        return (
            jsonify(
                {
                    "error": "Cannot connect to schematic generation server.",
                }
            ),
            503,
        )
    except requests.exceptions.Timeout:
        return jsonify({"error": "Request to schematic generation server timed out"}), 504
    except requests.exceptions.HTTPError as e:
        error_msg = f"Error from backend server: {e.response.status_code}"
        try:
            error_data = e.response.json()
            if "error" in error_data:
                error_msg = error_data["error"]
        except Exception:
            pass
        return jsonify({"error": error_msg}), (
            e.response.status_code if e.response is not None else 502
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400


def _build_item_colors_from_barriers(drawn_items, primary_elements, secondary_elements):
    """Build item_colors list.

    From drawn_items and primary/secondary barrier elements (same logic as
    JS buildItemColorsFromBarriers).
    """
    table_by_key = {}
    for item in primary_elements or []:
        el = (item.get("element") or "").strip()
        if " | " in el:
            name, type_val = el.split(" | ", 1)
            name, type_val = name.strip(), type_val.strip()
            if name:
                table_by_key[(name, type_val)] = "primary"
    for item in secondary_elements or []:
        el = (item.get("element") or "").strip()
        if " | " in el:
            name, type_val = el.split(" | ", 1)
            name, type_val = name.strip(), type_val.strip()
            if name:
                table_by_key[(name, type_val)] = "secondary"
    item_colors = []
    for item in drawn_items or []:
        name = (item.get("element_name") or item.get("name") or item.get("id") or "").strip()
        type_val = (item.get("element_type") or "").strip()
        pt = (item.get("patch_type") or "").strip()
        table_type = table_by_key.get((name, type_val))
        if not name or not pt or not table_type:
            continue
        if type_val == "Valve" and "valve_ellipse" not in pt:
            continue
        color = "#0d6efd" if table_type == "primary" else "red"
        item_colors.append(
            {
                "element_name": name,
                "element_type": type_val,
                "patch_type": pt,
                "color": color,
            }
        )
    return item_colors


@app_wellintegrity_monitoring.route(
    "/app/wellintegrity/generate_schematic_image_with_barriers", methods=["POST"]
)
def generate_schematic_image_with_barriers():
    """Single-call endpoint: generate schematic, optionally apply barrier colors.

    Server-side (one request from frontend, 1–2 calls to schematic server).
    """
    backend_url = app_instance.plant.parameters["wims_backend_url"]
    try:
        body = request.get_json()
        if body is None:
            return jsonify({"error": "No JSON body"}), 400
        body = dict(body)
        primary_barrier_elements = body.pop("primary_barrier_elements", None)
        secondary_barrier_elements = body.pop("secondary_barrier_elements", None)
        schematic_data = body
        schematic_data["return_annulus_information"] = True
        schematic_data["return_drawn_items"] = True

        response = requests.post(
            backend_url,
            json=schematic_data,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        drawn_items = data.get("drawn_items") or []
        item_colors = _build_item_colors_from_barriers(
            drawn_items, primary_barrier_elements, secondary_barrier_elements
        )
        if item_colors:
            schematic_with_colors = dict(schematic_data)
            schematic_with_colors["item_colors"] = item_colors
            response2 = requests.post(
                backend_url,
                json=schematic_with_colors,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            response2.raise_for_status()
            data = response2.json()
        return jsonify(data)
    except requests.exceptions.ConnectionError:
        return (
            jsonify(
                {
                    "error": "Cannot connect to schematic generation server.",
                }
            ),
            503,
        )
    except requests.exceptions.Timeout:
        return jsonify({"error": "Request to schematic generation server timed out"}), 504
    except requests.exceptions.HTTPError as e:
        error_msg = f"Error from backend server: {e.response.status_code}"
        try:
            err = e.response.json() if e.response is not None else {}
            if "error" in err:
                error_msg = err["error"]
        except Exception:
            pass
        return jsonify({"error": error_msg}), (
            e.response.status_code if e.response is not None else 502
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_log_list", methods=["POST"])
def get_log_list():
    """Get list of available logs for the selected well."""
    try:
        selected_well = request.json.get("selected_well")

        if not selected_well:
            return jsonify([])

        log_list = []
        # Use the same folder logic as get_saved_schematics
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        calipers_folder = os.path.join(well_data_folder, "calipers")

        if not os.path.exists(calipers_folder):
            os.makedirs(calipers_folder)

        # Get all .las files in the calipers folder
        uploaded_logs = glob.glob(os.path.join(calipers_folder, "*.las"))
        for file in uploaded_logs:
            log_list.append(os.path.basename(file))

        return jsonify(log_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_log_status", methods=["POST"])
def get_log_status():
    """Get the processing status of logs for the selected well."""
    try:
        selected_well = request.json.get("selected_well")

        if not selected_well:
            return jsonify([])

        # Get log files
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        calipers_folder = os.path.join(well_data_folder, "calipers")
        processed_folder = os.path.join(well_data_folder, "processed_logs")

        if not os.path.exists(calipers_folder):
            os.makedirs(calipers_folder)

        if not os.path.exists(processed_folder):
            os.makedirs(processed_folder)

        # Get all .las files
        uploaded_logs = glob.glob(os.path.join(calipers_folder, "*.las"))
        # Create list with processing status
        log_status_list = []
        for file_path in uploaded_logs:
            log_name = os.path.basename(file_path)
            # Check if processed file exists (JSON file with same base name)
            processed_file_name = log_name.replace(".las", "_processed.json")
            processed_file_path = os.path.join(processed_folder, processed_file_name)

            log_status_list.append(
                {"name": log_name, "processed": os.path.exists(processed_file_path)}
            )

        return jsonify(log_status_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/upload_log", methods=["POST"])
def upload_log():
    """Upload a log file to the calipers folder for the selected well."""
    try:

        if "las_file" not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files["las_file"]

        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        selected_well = request.form["selected_well"]
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        calipers_folder = os.path.join(well_data_folder, "calipers")

        if not os.path.exists(calipers_folder):
            os.makedirs(calipers_folder)

        file.save(os.path.join(calipers_folder, file.filename))
        return jsonify({"message": "File uploaded successfully!"})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/process_caliper_logs", methods=["POST"])
def process_caliper_logs():
    """Start processing selected caliper logs using Celery task."""
    try:
        selected_well = request.json.get("selected_well")
        selected_logs = request.json.get("selected_logs", [])

        if not selected_well:
            return jsonify({"error": "No well selected"}), 400

        if not selected_logs:
            return jsonify({"error": "No logs selected"}), 400

        # Prepare inputs for the Celery task
        inputs = {"selected_logs": selected_logs}

        project_folder_path = app_instance.plant.project_path
        project_name = app_instance.plant.name
        well_name = selected_well

        # Start the Celery task
        task = wellintegrity_app_process_caliper_logs.delay(
            project_folder_path, project_name, well_name, inputs
        )

        task_id = str(task.id)

        return jsonify(
            {
                "task_id": task_id,
                "message": "Caliper logs processing started",
                "selected_logs": selected_logs,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_processing_results", methods=["POST"])
def get_processing_results():
    """Get the results of the caliper logs processing task."""
    try:
        task_id = request.json.get("task_id")

        if not task_id:
            return jsonify({"error": "No task ID provided"}), 400

        task_result = celery.AsyncResult(task_id)

        result = {
            "task_id": task_id,
            "task_status": task_result.status,
            "task_result": task_result.result,
        }

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_tally_list", methods=["POST"])
def get_tally_list():
    """Get a list of available well tally files for the selected well."""
    try:
        selected_well = request.json.get("selected_well")

        if not selected_well:
            return jsonify([])

        tally_list = []
        # Use the same folder logic as get_saved_schematics
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        tally_folder = os.path.join(well_data_folder, "tally")

        if not os.path.exists(tally_folder):
            os.makedirs(tally_folder)

        # Get all .csv and .txt files in the tally folder
        uploaded_tallies = glob.glob(os.path.join(tally_folder, "*.csv"))
        uploaded_tallies.extend(glob.glob(os.path.join(tally_folder, "*.txt")))
        for file in uploaded_tallies:
            tally_list.append(os.path.basename(file))

        return jsonify(tally_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/upload_tally", methods=["POST"])
def upload_tally():
    """Upload a well tally file to the tally folder for the selected well."""
    try:

        if "tally_file" not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files["tally_file"]

        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        # Check if file is a valid tally file
        if not file.filename.lower().endswith((".csv", ".txt")):
            return jsonify({"error": "Please select a .csv or .txt file"}), 400

        selected_well = request.form["selected_well"]
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        tally_folder = os.path.join(well_data_folder, "tally")

        if not os.path.exists(tally_folder):
            os.makedirs(tally_folder)

        file.save(os.path.join(tally_folder, file.filename))
        return jsonify({"message": "Tally file uploaded successfully!"})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/load_processed_logs", methods=["POST"])
def load_processed_logs():
    """Load previously processed logs from saved JSON files."""
    try:
        selected_well = request.json.get("selected_well")
        selected_logs = request.json.get("selected_logs", [])

        if not selected_well:
            return jsonify({"error": "No well selected"}), 400

        if not selected_logs:
            return jsonify({"error": "No logs selected"}), 400

        # Get processed logs folder
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        processed_folder = os.path.join(well_data_folder, "processed_logs")

        if not os.path.exists(processed_folder):
            return jsonify({"error": "No processed logs found"}), 404

        # Load processed logs
        processed_logs_dict = {}

        for log_name in selected_logs:
            processed_file_name = log_name.replace(".las", "_processed.json")
            processed_file_path = os.path.join(processed_folder, processed_file_name)

            if os.path.exists(processed_file_path):
                with open(processed_file_path, "r") as f:
                    processed_data = json.load(f)
                processed_logs_dict[log_name] = processed_data
            else:
                processed_logs_dict[log_name] = []

        return jsonify(
            {
                "message": "Processed logs loaded successfully",
                "processed_logs": selected_logs,
                "results": {"processedLogs": processed_logs_dict},
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 400


LOG_DATES_FILENAME = "log_dates.json"
FMT_LOG_DATE = "%H-%M-%S %d-%m-%Y"  # used by co2_corrosion for log date strings
FMT_LOG_DATE_STORAGE = "%Y-%m-%d"  # stored in JSON as YYYY-MM-DD


def _get_log_dates_path(processed_folder):
    return os.path.join(processed_folder, LOG_DATES_FILENAME)


def _load_saved_log_dates(processed_folder):
    """Load saved log name -> date (YYYY-MM-DD) from log_dates.json. Returns dict or {}."""
    path = _get_log_dates_path(processed_folder)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data.get("log_dates", data) if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError):
        return {}


def _load_forecast_config(processed_folder):
    """Load full forecast config from log_dates.

    json: log_dates, start_time, minimum_remaining_thickness_mm.
    """
    path = _get_log_dates_path(processed_folder)
    if not os.path.exists(path):
        return {"log_dates": {}, "start_time": None, "minimum_remaining_thickness_mm": None}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"log_dates": {}, "start_time": None, "minimum_remaining_thickness_mm": None}
        return {
            "log_dates": data.get("log_dates", {}),
            "start_time": data.get("start_time") or None,
            "minimum_remaining_thickness_mm": data.get("minimum_remaining_thickness_mm"),
        }
    except (json.JSONDecodeError, IOError):
        return {"log_dates": {}, "start_time": None, "minimum_remaining_thickness_mm": None}


def _read_forecast_config_full(processed_folder):
    """Read full forecast config dict from log_dates.json (for merging and saving)."""
    path = _get_log_dates_path(processed_folder)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError):
        return {}


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_log_dates", methods=["POST"])
def get_log_dates():
    """Get saved log dates for the selected well (from processed_logs/log_dates.json)."""
    try:
        if app_instance is None:
            return (
                jsonify({"error": "Plant not loaded. Select a field first.", "log_dates": {}}),
                400,
            )
        selected_well = request.json.get("selected_well")
        if not selected_well:
            return jsonify({"error": "No well selected", "log_dates": {}}), 400
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        processed_folder = os.path.join(project_data_folder, selected_well, "processed_logs")
        config = _load_forecast_config(processed_folder)
        return jsonify(
            {
                "log_dates": config["log_dates"],
                "start_time": config["start_time"],
                "minimum_remaining_thickness_mm": config.get("minimum_remaining_thickness_mm"),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e), "log_dates": {}}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/save_log_dates", methods=["POST"])
def save_log_dates():
    """Save log name -> date (YYYY-MM-DD) into processed_logs/log_dates.json."""
    try:
        if app_instance is None:
            return jsonify({"error": "Plant not loaded. Select a field first."}), 400
        selected_well = request.json.get("selected_well")
        log_dates = request.json.get("log_dates")
        start_time = request.json.get("start_time")  # optional YYYY-MM-DD
        if not selected_well:
            return jsonify({"error": "No well selected"}), 400
        if log_dates is None or not isinstance(log_dates, dict):
            return jsonify({"error": "log_dates must be an object"}), 400
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        processed_folder = os.path.join(project_data_folder, selected_well, "processed_logs")
        if not os.path.exists(processed_folder):
            os.makedirs(processed_folder)
        path = _get_log_dates_path(processed_folder)
        payload = {"log_dates": log_dates}
        if start_time and isinstance(start_time, str) and start_time.strip():
            payload["start_time"] = start_time.strip()
        else:
            # Preserve existing start_time if not provided
            existing = _load_forecast_config(processed_folder)
            if existing.get("start_time"):
                payload["start_time"] = existing["start_time"]
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        return jsonify({"message": "Log dates saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/save_corrosion_limits", methods=["POST"])
def save_corrosion_limits():
    """Save minimum remaining thickness [mm] into processed_logs/log_dates.json."""
    try:
        if app_instance is None:
            return jsonify({"error": "Plant not loaded. Select a field first."}), 400
        selected_well = request.json.get("selected_well")
        minimum_remaining_thickness_mm = request.json.get("minimum_remaining_thickness_mm")
        if not selected_well:
            return jsonify({"error": "No well selected"}), 400
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        processed_folder = os.path.join(project_data_folder, selected_well, "processed_logs")
        if not os.path.exists(processed_folder):
            os.makedirs(processed_folder)
        path = _get_log_dates_path(processed_folder)
        data = _read_forecast_config_full(processed_folder)
        if not data:
            data = {"log_dates": {}}
        if (
            minimum_remaining_thickness_mm is not None
            and str(minimum_remaining_thickness_mm).strip() != ""
        ):
            try:
                data["minimum_remaining_thickness_mm"] = float(minimum_remaining_thickness_mm)
            except (TypeError, ValueError):
                data["minimum_remaining_thickness_mm"] = None
        else:
            data["minimum_remaining_thickness_mm"] = None
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return jsonify({"message": "Corrosion limits saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route(
    "/app/wellintegrity/get_corrosion_rate_from_logs", methods=["POST"]
)
def get_corrosion_rate_from_logs():
    """Compute corrosion rate from processed logs.

    saved JSONs and return for display in the panel.
    """
    try:
        selected_well = request.json.get("selected_well")
        if not selected_well:
            return jsonify({"error": "No well selected", "corrosion_rate": None}), 400

        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        processed_folder = os.path.join(well_data_folder, "processed_logs")

        if not os.path.exists(processed_folder):
            return jsonify({"corrosion_rate": None, "message": "No processed logs folder"})

        pattern = os.path.join(processed_folder, "*_processed.json")
        files = glob.glob(pattern)
        if not files:
            return jsonify({"corrosion_rate": None, "message": "No processed logs"})

        app_instance.select_unit(selected_well)
        app_instance.init_parameters()
        n_joints = len(app_instance.inputs["well_tally"])
        saved_log_dates = _load_saved_log_dates(processed_folder)
        fmt_log = FMT_LOG_DATE

        # Only use logs that have a date defined in log_dates.json (no file mtime fallback)
        entries_with_date = []
        for file_path in files:
            base = os.path.basename(file_path)
            log_name = base.replace("_processed.json", ".las")
            saved = saved_log_dates.get(log_name)
            if not saved:
                continue
            try:
                dt = datetime.strptime(saved, FMT_LOG_DATE_STORAGE)
                date_str = dt.strftime(fmt_log)
            except ValueError:
                continue
            entries_with_date.append((file_path, log_name, date_str))

        if not entries_with_date:
            return jsonify(
                {
                    "corrosion_rate": None,
                    "message": "Define and save log dates for at least one processed log, "
                    "then click Calculate.",
                }
            )

        entries_with_date.sort(key=lambda x: x[2])

        log_names = []
        log_dates = []
        processed_dfs = []
        for file_path, log_name, date_str in entries_with_date:
            with open(file_path, "r") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data)
                log_names.append(log_name)
                log_dates.append(date_str)
                processed_dfs.append(df)

        if not processed_dfs:
            return jsonify(
                {
                    "corrosion_rate": None,
                    "message": "No valid processed log data.",
                }
            )

        joints_processed = min(len(df) for df in processed_dfs)
        config = _load_forecast_config(processed_folder)
        saved_start = config.get("start_time")
        if not saved_start or not str(saved_start).strip():
            return jsonify(
                {
                    "corrosion_rate": None,
                    "message": "Set Baseline date and save dates, "
                    "then click Calculate corrosion rate.",
                }
            )
        try:
            start_dt = datetime.strptime(saved_start.strip(), FMT_LOG_DATE_STORAGE)
            start_time = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return jsonify(
                {
                    "corrosion_rate": None,
                    "message": "Baseline date must be YYYY-MM-DD. Set and save dates, "
                    "then click Calculate.",
                }
            )
        app_instance.inputs["start_time"] = start_time
        app_instance.inputs["uploadedLogs"] = {
            "logName": log_names,
            "logDate": log_dates,
            "logData": [None] * len(log_names),
        }
        app_instance.outputs["processedLogs"] = processed_dfs

        app_instance.get_corrosion_rate_from_logs()
        measured = app_instance.outputs.get("measuredCorrosionRate")
        if measured is None:
            return jsonify({"corrosion_rate": None, "message": "Corrosion rate not calculated"})

        # Compute remaining days to min. thickness if minimum is set
        min_thickness = config.get("minimum_remaining_thickness_mm")
        if min_thickness is not None and str(min_thickness).strip() != "":
            try:
                min_mm = float(min_thickness)
                app_instance.get_remaining_days_to_min_thickness(min_mm)
            except (TypeError, ValueError):
                pass

        # Ensure Joint No. is the first column for display
        if "Joint No." in measured.columns:
            other_cols = [c for c in measured.columns if c != "Joint No."]
            measured = measured[["Joint No."] + other_cols]

        # DataFrame to JSON-friendly dict; replace NaN for JSON serialization
        corrosion_rate_data = measured.to_dict(orient="list")
        for k, v in corrosion_rate_data.items():
            if hasattr(v, "__iter__") and not isinstance(v, (list, str)):
                v = list(v)
            if isinstance(v, list):
                v = [None if (isinstance(x, float) and pd.isna(x)) else x for x in v]
            corrosion_rate_data[k] = v

        # Add Remaining thickness at log date columns to the same table
        # Use n_joints as target length so column lengths always match (avoid pandas "length of
        # values does not match index" when switching wells)
        n_rows = n_joints
        remaining = app_instance.outputs.get("remainingThicknessAtLogDate")
        if remaining is not None and not remaining.empty:
            if "Joint No." in remaining.columns:
                other_remaining = [c for c in remaining.columns if c != "Joint No."]
                remaining = remaining[["Joint No."] + other_remaining]
            for col in remaining.columns:
                if col == "Joint No.":
                    continue
                v = remaining[col].tolist()
                v = [None if (isinstance(x, float) and pd.isna(x)) else x for x in v]
                # Pad or truncate to n_rows so all columns have the same length
                if len(v) < n_rows:
                    v = v + [None] * (n_rows - len(v))
                elif len(v) > n_rows:
                    v = v[:n_rows]
                corrosion_rate_data[col] = v

        # Add Remaining days to min. thickness column if computed
        days_df = app_instance.outputs.get("remainingDaysToMinThickness")
        if (
            days_df is not None
            and not days_df.empty
            and "Remaining days to min. thickness [days]" in days_df.columns
        ):
            v = days_df["Remaining days to min. thickness [days]"].tolist()
            v = [
                (
                    None
                    if (isinstance(x, float) and (pd.isna(x) or np.isposinf(x)))
                    else (int(round(x)) if isinstance(x, float) and np.isfinite(x) else x)
                )
                for x in v
            ]
            if len(v) < n_rows:
                v = v + [None] * (n_rows - len(v))
            elif len(v) > n_rows:
                v = v[:n_rows]
            corrosion_rate_data["Remaining days to min. thickness [days]"] = v

        # Ensure "Remaining days to min. thickness [days]" is the last column
        days_col = "Remaining days to min. thickness [days]"
        if days_col in corrosion_rate_data:
            keys_ordered = [k for k in corrosion_rate_data if k != days_col] + [days_col]
            corrosion_rate_data = {k: corrosion_rate_data[k] for k in keys_ordered}

        return jsonify(
            {
                "corrosion_rate": corrosion_rate_data,
                "joints_in_tally": n_joints,
                "joints_processed": joints_processed,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e), "corrosion_rate": None}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_annulus_information", methods=["POST"])
def get_annulus_information():
    """Get annulus information.

    From the external API by ending schematic JSON with return_annulus_information=True.
    """
    try:
        selected_well = request.json.get("selected_well")
        schematic_filename = request.json.get("schematic_filename")

        if not selected_well or not schematic_filename:
            return jsonify({"error": "Missing well name or schematic filename"}), 400

        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well, "schematics")
        schematic_path = os.path.join(well_data_folder, schematic_filename)

        if not os.path.exists(schematic_path):
            return jsonify({"error": "Schematic file not found"}), 404

        with open(schematic_path, "r") as f:
            json_data = json.load(f)

        json_data["return_annulus_information"] = True
        backend_url = app_instance.plant.parameters["wims_backend_url"]

        response = requests.post(
            backend_url,
            json=json_data,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.ConnectionError:
        return (
            jsonify(
                {
                    "error": "Cannot connect to schematic server.",
                }
            ),
            503,
        )
    except requests.exceptions.Timeout:
        return jsonify({"error": "Request to schematic server timed out"}), 504
    except requests.exceptions.HTTPError as e:
        error_msg = f"Error from backend: {e.response.status_code}"
        try:
            err = e.response.json()
            if "error" in err:
                error_msg = err["error"]
        except Exception:
            pass
        return jsonify({"error": error_msg}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_measured_tags", methods=["POST"])
def get_measured_tags():
    """Get measured tags from the selected unit for monitoring."""
    try:
        selected_well = request.json.get("selected_well")

        if not selected_well:
            return jsonify({"error": "No well selected"}), 400

        # Select the unit to access tags
        app_instance.select_unit(selected_well)

        # Get measured tags from the unit
        measured_tags = app_instance.unit.tags.get("measured", {})

        # Convert tags to serializable format
        tags_data = []
        for tag_name, tag_info in measured_tags.items():
            tags_data.append(
                {
                    "tag_name": tag_name,
                    "description": getattr(tag_info, "description", tag_name),
                    "unit": getattr(tag_info, "unit", ""),
                    "value": getattr(tag_info, "value", None),
                }
            )

        return jsonify({"measured_tags": tags_data, "count": len(tags_data)})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_tag_data", methods=["POST"])
def get_tag_data():
    """Get data for a specific tag from the application using real database functionality."""
    try:
        body = request.get_json(silent=True) or {}
        selected_well = body.get("selected_well")
        tag_name = body.get("tag_name")
        print(
            "[get_tag_data] POST body: selected_well={!r}, tag_name={!r}".format(
                selected_well, tag_name
            )
        )

        if not selected_well or not tag_name:
            return jsonify({"error": "Missing well name or tag name"}), 400

        # Select the unit
        app_instance.select_unit(selected_well)

        # Get the tag data
        measured_tags = app_instance.unit.tags.get("measured", {})

        if tag_name not in measured_tags:
            return jsonify({"error": f"Tag '{tag_name}' not found"}), 404

        tag_info = measured_tags[tag_name]

        # Get current value - first try from tag object, then from database
        current_value = getattr(tag_info, "value", None)
        timestamp = getattr(tag_info, "timestamp", None)

        # If tag object doesn't have a value, try database
        if current_value is None:
            try:
                # Use the plant database to get the latest value
                from datetime import datetime, timedelta, timezone

                # Get current time and a time range for the last hour
                end_time = datetime.now(timezone.utc)
                start_time = end_time - timedelta(hours=1)

                # Format times for database query
                start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
                end_time_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

                timestep = 3600  # 1 hour

                # Read from internal database - construct full tag path
                full_tag_name = f"{tag_name}.measured"

                result, time_data = app_instance.plant.database.read_internal_database(
                    app_instance.plant.name,
                    app_instance.unit.name,
                    full_tag_name,
                    start_time_str,
                    end_time_str,
                    timestep,
                )

                # Get the most recent value if available
                if result and len(result) > 0:
                    current_value = result[-1]  # Most recent value
                    if time_data and len(time_data) > 0:
                        timestamp = time_data[-1]

            except Exception as db_error:
                print(f"Database read error for tag {tag_name}: {db_error}")
                # current_value remains None if both tag object and database fail

        # Extract tag data
        tag_data = {
            "tag_name": tag_name,
            "description": getattr(tag_info, "description", tag_name),
            "unit": getattr(tag_info, "unit", ""),
            "current_value": current_value,
            "timestamp": timestamp or getattr(tag_info, "timestamp", None),
        }
        print("[get_tag_data] response: tag_data={}".format(tag_data))
        return jsonify({"tag_data": tag_data, "success": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/save_monitors", methods=["POST"])
def save_monitors():
    """Save monitor configurations for a specific well and schematic."""
    try:
        selected_well = request.json.get("selected_well")
        schematic_filename = request.json.get("schematic_filename")
        monitors = request.json.get("monitors")

        if not selected_well or not schematic_filename or not monitors:
            return jsonify({"error": "Missing required parameters"}), 400

        # Create monitors folder path
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        monitors_folder = os.path.join(well_data_folder, "monitors")

        if not os.path.exists(monitors_folder):
            os.makedirs(monitors_folder)

        # Save monitors to file (using schematic name as filename)
        schematic_name = schematic_filename.replace(".json", "")
        monitors_file = os.path.join(monitors_folder, f"{schematic_name}_monitors.json")

        with open(monitors_file, "w") as f:
            json.dump(monitors, f, indent=2)

        return jsonify({"message": "Monitors saved successfully"})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/load_monitors", methods=["POST"])
def load_monitors():
    """Load monitor configurations for a specific well and schematic."""
    try:
        selected_well = request.json.get("selected_well")
        schematic_filename = request.json.get("schematic_filename")

        if not selected_well or not schematic_filename:
            return jsonify({"error": "Missing required parameters"}), 400

        # Create monitors folder path
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        monitors_folder = os.path.join(well_data_folder, "monitors")

        # Load monitors from file (using schematic name as filename)
        schematic_name = schematic_filename.replace(".json", "")
        monitors_file = os.path.join(monitors_folder, f"{schematic_name}_monitors.json")

        if not os.path.exists(monitors_file):
            return jsonify({"monitors": []})

        with open(monitors_file, "r") as f:
            monitors = json.load(f)

        return jsonify({"monitors": monitors})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/save_wims_panel", methods=["POST"])
def save_wims_panel():
    """Save WIMS panel state.

    overall status, last update date, barrier elements for the selected well and schematic.
    """
    try:
        selected_well = request.json.get("selected_well")
        schematic_filename = request.json.get("schematic_filename")
        panel_data = request.json.get("panel_data")

        if not selected_well or not schematic_filename:
            return jsonify({"error": "Missing well name or schematic filename"}), 400
        if panel_data is None:
            return jsonify({"error": "Missing panel_data"}), 400

        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        wims_panel_folder = os.path.join(well_data_folder, "wims_panel")

        if not os.path.exists(wims_panel_folder):
            os.makedirs(wims_panel_folder)

        schematic_name = schematic_filename.replace(".json", "")
        panel_file = os.path.join(wims_panel_folder, f"{schematic_name}_wims_panel.json")

        with open(panel_file, "w") as f:
            json.dump(panel_data, f, indent=2)

        return jsonify({"message": "WIMS panel saved successfully"})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/load_wims_panel", methods=["POST"])
def load_wims_panel():
    """Load WIMS panel state for the selected well and schematic."""
    try:
        selected_well = request.json.get("selected_well")
        schematic_filename = request.json.get("schematic_filename")

        if not selected_well or not schematic_filename:
            return jsonify({"error": "Missing well name or schematic filename"}), 400

        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        wims_panel_folder = os.path.join(well_data_folder, "wims_panel")
        schematic_name = schematic_filename.replace(".json", "")
        panel_file = os.path.join(wims_panel_folder, f"{schematic_name}_wims_panel.json")

        if not os.path.exists(panel_file):
            return jsonify({"panel_data": None})

        with open(panel_file, "r") as f:
            panel_data = json.load(f)

        return jsonify({"panel_data": panel_data})

    except Exception as e:
        return jsonify({"error": str(e)}), 400
