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
from math import gcd

import matplotlib
import numpy as np
import pandas as pd
import requests
from flask import Blueprint, current_app, jsonify, request, send_file
from werkzeug.utils import secure_filename

# Import the same application instance as well_schematics
from gemini_application.wims.corrosion_model import CO2CorrosionApplication
from gemini_application.wims.erosion_model import ErosionApplication
from gemini_framework.modules.injectionwell.unit import InjectionWellUnit
from gemini_framework.modules.productionwell.unit import ProductionWellUnit
from gemini_interface.blueprint.celerytasks import (
    celery,
    wellintegrity_app_detect_joints,
    wellintegrity_app_forecast_years_to_min,
    wellintegrity_app_optimize_corrosion,
    wellintegrity_app_predict_corrosion,
    wellintegrity_app_process_caliper_logs,
)

# Configure matplotlib for non-GUI backend (perfect for server)
matplotlib.use("Agg")

app_wellintegrity_monitoring = Blueprint("app_wellintegrity_monitoring", __name__)
MAX_WELL_LOGS = 5

# Application instance set by load_plant(); used by routes that need project path / plant.
app_instance = None
erosion_app_instance = None


@app_wellintegrity_monitoring.route("/app/wellintegrity/load_plant", methods=["POST"])
def load_plant():
    """Load a plant into the well integrity monitoring application instance."""
    global app_instance, erosion_app_instance
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
        try:
            erosion_app_instance = ErosionApplication()
            erosion_app_instance.load_plant(project_folder_path, project_name.strip())
        except Exception as erosion_err:
            erosion_app_instance = None
            current_app.logger.warning("Erosion application failed to load: %s", erosion_err)
        return jsonify({"message": "OK"})
    except Exception as e:
        app_instance = None
        erosion_app_instance = None
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
    """Proxy route to generate a well schematic image.

    Calls the external backend API (http://185.92.222.87:8001/generate).
    Also requests annulus information in the same call (return_annulus_information=True).
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


def _barrier_color_rules(elements, table_type):
    """Extract name/type/depth-band rules from one barrier table."""
    rules = []
    for item in elements or []:
        el = (item.get("element") or "").strip()
        name = (item.get("element_name") or "").strip()
        type_val = (item.get("element_type") or "").strip()
        if (not name or not type_val) and " | " in el:
            parsed_name, parsed_type = el.split(" | ", 1)
            if not name:
                name = parsed_name.strip()
            if not type_val:
                type_val = parsed_type.strip()
        if not name:
            continue
        rule = {"name": name, "type_val": type_val, "table_type": table_type}
        rule["status"] = (item.get("status") or "verified").strip()
        patch_types = item.get("patch_types")
        if isinstance(patch_types, list) and patch_types:
            rule["patch_types"] = [str(p).strip() for p in patch_types if str(p).strip()]
        top_m = item.get("top_depth_m")
        bottom_m = item.get("bottom_depth_m")
        if top_m is not None and bottom_m is not None:
            try:
                rule["top_depth"] = float(top_m)
                rule["bottom_depth"] = float(bottom_m)
            except (TypeError, ValueError):
                pass
        rules.append(rule)
    return rules


def _barrier_schematic_color(table_type, status):
    """Primary blue; secondary red; failed elements bright yellow."""
    if status == "failed":
        return "#FFEB3B"
    if table_type == "secondary":
        return "red"
    return "#0d6efd"


def _build_item_colors_from_barriers(drawn_items, primary_elements, secondary_elements):
    """Build item_colors list from drawn_items and barrier elements.

    Uses the same logic as JS buildItemColorsFromBarriers for primary/secondary barriers.
    """
    rules = _barrier_color_rules(primary_elements, "primary") + _barrier_color_rules(
        secondary_elements, "secondary"
    )
    item_colors = []
    for rule in rules:
        for item in drawn_items or []:
            name = (item.get("element_name") or item.get("name") or item.get("id") or "").strip()
            type_val = (item.get("element_type") or "").strip()
            pt = (item.get("patch_type") or "").strip()
            if name != rule["name"] or type_val != rule["type_val"] or not pt:
                continue
            patch_filter = rule.get("patch_types")
            if patch_filter is not None:
                if pt not in patch_filter:
                    continue
            elif type_val == "Valve" and "valve_ellipse" not in pt:
                continue
            color = _barrier_schematic_color(rule["table_type"], rule.get("status", "verified"))
            entry = {
                "element_name": name,
                "element_type": type_val,
                "patch_type": pt,
                "color": color,
            }
            if "top_depth" in rule and "bottom_depth" in rule:
                entry["top_depth"] = rule["top_depth"]
                entry["bottom_depth"] = rule["bottom_depth"]
            item_colors.append(entry)
    return item_colors


@app_wellintegrity_monitoring.route(
    "/app/wellintegrity/generate_schematic_image_with_barriers", methods=["POST"]
)
def generate_schematic_image_with_barriers():
    """Generate schematic and optionally apply barrier colors server-side.

    Single request from frontend; one or two calls to the schematic server.
    """
    backend_url = "http://185.92.222.87:8001/generate"
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
    """Get the processing status of logs for the selected well.

    Returns four-state status per log: inputs_required / unprocessed / detected / processed.
    """
    try:
        selected_well = request.json.get("selected_well")

        if not selected_well:
            return jsonify([])

        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        calipers_folder = os.path.join(well_data_folder, "calipers")
        processed_folder = os.path.join(well_data_folder, "processed_logs")
        detected_folder = os.path.join(well_data_folder, "detected_joints")

        if not os.path.exists(calipers_folder):
            os.makedirs(calipers_folder)

        if not os.path.exists(processed_folder):
            os.makedirs(processed_folder)

        logs_info = _load_logs_information(well_data_folder).get("logs", {})

        uploaded_logs = glob.glob(os.path.join(calipers_folder, "*.las"))
        log_status_list = []
        for file_path in uploaded_logs:
            log_name = os.path.basename(file_path)
            processed_file_name = log_name.replace(".las", "_processed.json")
            processed_file_path = os.path.join(processed_folder, processed_file_name)
            detected_file_name = log_name.replace(".las", "_detected_joints.json")
            detected_file_path = os.path.join(detected_folder, detected_file_name)
            log_entry = logs_info.get(log_name, {}) if isinstance(logs_info, dict) else {}
            log_date = log_entry.get("date") if isinstance(log_entry, dict) else None

            if os.path.exists(processed_file_path):
                status = "processed"
            elif os.path.exists(detected_file_path):
                status = "detected"
            elif _log_has_required_info(logs_info.get(log_name)):
                status = "unprocessed"
            else:
                status = "inputs_required"

            log_status_list.append({"name": log_name, "status": status, "date": log_date})

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

        existing_logs = glob.glob(os.path.join(calipers_folder, "*.las"))
        if len(existing_logs) >= MAX_WELL_LOGS:
            return jsonify({"error": f"Maximum {MAX_WELL_LOGS} logs allowed per well."}), 400

        target_path = os.path.join(calipers_folder, file.filename)
        if os.path.exists(target_path):
            return jsonify({"error": "A log with this name already exists."}), 400

        file.save(target_path)
        return jsonify({"message": "File uploaded successfully!"})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/process_caliper_logs", methods=["POST"])
def process_caliper_logs():
    """Start processing selected caliper logs using Celery task."""
    try:
        selected_well = request.json.get("selected_well")
        selected_logs = request.json.get("selected_logs", [])
        use_approved_joints = request.json.get("use_approved_joints", False)

        if not selected_well:
            return jsonify({"error": "No well selected"}), 400

        if not selected_logs:
            return jsonify({"error": "No logs selected"}), 400

        inputs = {
            "selected_logs": selected_logs,
            "use_approved_joints": use_approved_joints,
        }

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


@app_wellintegrity_monitoring.route("/app/wellintegrity/detect_joints", methods=["POST"])
def detect_joints_route():
    """Start joint detection for selected caliper logs using Celery task."""
    try:
        selected_well = request.json.get("selected_well")
        selected_logs = request.json.get("selected_logs", [])

        if not selected_well:
            return jsonify({"error": "No well selected"}), 400

        if not selected_logs:
            return jsonify({"error": "No logs selected"}), 400

        inputs = {"selected_logs": selected_logs}

        project_folder_path = app_instance.plant.project_path
        project_name = app_instance.plant.name
        well_name = selected_well

        task = wellintegrity_app_detect_joints.delay(
            project_folder_path, project_name, well_name, inputs
        )

        task_id = str(task.id)

        return jsonify(
            {
                "task_id": task_id,
                "message": "Joint detection started",
                "selected_logs": selected_logs,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route(
    "/app/wellintegrity/get_detect_joints_results", methods=["POST"]
)
def get_detect_joints_results():
    """Get the results of the joint detection task.

    Supports incremental loading: checks which per-log JSON files have been
    saved to disk so far and returns them, even if the Celery task is still
    running.  The frontend can display results as they become available.
    """
    try:
        task_id = request.json.get("task_id")
        selected_well = request.json.get("selected_well")
        selected_logs = request.json.get("selected_logs", [])

        if not task_id:
            return jsonify({"error": "No task ID provided"}), 400

        task_result_obj = celery.AsyncResult(task_id)
        task_status = task_result_obj.status

        ready_logs = {}
        if selected_well and selected_logs:
            project_data_folder = os.path.join(
                app_instance.plant.project_path,
                app_instance.plant.name + "/wims_data",
            )
            well_data_folder = os.path.join(project_data_folder, selected_well)
            detected_folder = os.path.join(well_data_folder, "detected_joints")

            for log_name in selected_logs:
                detected_file = os.path.join(
                    detected_folder,
                    log_name.replace(".las", "_detected_joints.json"),
                )
                if os.path.exists(detected_file):
                    try:
                        with open(detected_file, "r") as f:
                            log_data = json.load(f)
                        entry = {
                            "method": log_data.get("method", "unknown"),
                            "candidates": log_data.get("candidates", []),
                            "joint_boundaries": log_data.get("joint_boundaries", []),
                            "chart_depths": log_data.get("chart_depths", []),
                            "chart_values": log_data.get("chart_values", []),
                        }
                        ready_logs[log_name] = entry
                    except (json.JSONDecodeError, IOError):
                        pass

        result = {
            "task_id": task_id,
            "task_status": task_status,
            "ready_logs": ready_logs,
            "total_logs": len(selected_logs),
            "completed_logs": len(ready_logs),
        }

        if task_status == "SUCCESS":
            final_result = task_result_obj.result
            if isinstance(final_result, dict) and "detected_joints" in final_result:
                result["task_result"] = final_result

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/save_approved_joints", methods=["POST"])
def save_approved_joints():
    """Save user-approved joint candidates after QA/QC review."""
    try:
        selected_well = request.json.get("selected_well")
        approved_joints = request.json.get("approved_joints")

        if not selected_well:
            return jsonify({"error": "No well selected"}), 400

        if not approved_joints or not isinstance(approved_joints, dict):
            return jsonify({"error": "approved_joints must be a dict keyed by log name"}), 400

        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        approved_folder = os.path.join(well_data_folder, "approved_joints")

        if not os.path.exists(approved_folder):
            os.makedirs(approved_folder)

        for log_name, joints_list in approved_joints.items():
            approved_file_name = log_name.replace(".las", "_approved_joints.json")
            approved_file_path = os.path.join(approved_folder, approved_file_name)

            with open(approved_file_path, "w") as f:
                json.dump(joints_list, f, indent=2)

        return jsonify({"message": "Approved joints saved successfully"})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/load_detected_joints", methods=["POST"])
def load_detected_joints():
    """Load previously saved detected-joints data (candidates + chart) for given logs."""
    try:
        selected_well = request.json.get("selected_well")
        selected_logs = request.json.get("selected_logs", [])

        if not selected_well:
            return jsonify({"error": "No well selected"}), 400

        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        detected_folder = os.path.join(well_data_folder, "detected_joints")

        approved_folder = os.path.join(well_data_folder, "approved_joints")

        results = {}
        for log_name in selected_logs:
            detected_file = os.path.join(
                detected_folder, log_name.replace(".las", "_detected_joints.json")
            )
            if not os.path.exists(detected_file):
                continue
            try:
                with open(detected_file, "r") as f:
                    log_data = json.load(f)
                all_candidates = log_data.get("candidates", [])
                entry = {
                    "method": log_data.get("method", "unknown"),
                    "candidates": all_candidates,
                    "joint_boundaries": log_data.get("joint_boundaries", []),
                    "chart_depths": log_data.get("chart_depths", []),
                    "chart_values": log_data.get("chart_values", []),
                }

                approved_file = os.path.join(
                    approved_folder,
                    log_name.replace(".las", "_approved_joints.json"),
                )
                if os.path.exists(approved_file):
                    with open(approved_file, "r") as af:
                        entry["approved_candidates"] = json.load(af)

                results[log_name] = entry
            except (json.JSONDecodeError, IOError):
                pass

        return jsonify({"detected_joints": results})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/load_approved_joints", methods=["POST"])
def load_approved_joints():
    """Load previously approved joints for the selected well."""
    try:
        selected_well = request.json.get("selected_well")
        selected_logs = request.json.get("selected_logs", [])

        if not selected_well:
            return jsonify({"error": "No well selected"}), 400

        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        approved_folder = os.path.join(well_data_folder, "approved_joints")

        approved_joints = {}

        if os.path.exists(approved_folder):
            for log_name in selected_logs:
                approved_file_name = log_name.replace(".las", "_approved_joints.json")
                approved_file_path = os.path.join(approved_folder, approved_file_name)

                if os.path.exists(approved_file_path):
                    with open(approved_file_path, "r") as f:
                        approved_joints[log_name] = json.load(f)

        return jsonify({"approved_joints": approved_joints})

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


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_joint_finger_data", methods=["POST"])
def get_joint_finger_data():
    """Return per-finger caliper measurements for a specific joint depth range."""
    import re

    import lasio

    try:
        selected_well = request.json.get("selected_well")
        log_name = request.json.get("log_name")
        top_depth = request.json.get("top_depth")
        bottom_depth = request.json.get("bottom_depth")
        joint_idx = request.json.get("joint_idx")

        if not selected_well or not log_name:
            return jsonify({"error": "Missing selected_well or log_name"}), 400
        if top_depth is None or bottom_depth is None:
            return jsonify({"error": "Missing top_depth or bottom_depth"}), 400

        top_depth = float(top_depth)
        bottom_depth = float(bottom_depth)

        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)

        # Try pre-extracted JSON first (fast path)
        if joint_idx is not None:
            finger_data_folder = os.path.join(well_data_folder, "finger_data")
            cached_file = os.path.join(
                finger_data_folder, f"{log_name}_joint_{int(joint_idx)}.json"
            )
            if os.path.exists(cached_file):
                with open(cached_file, "r") as f:
                    return jsonify(json.load(f))

        # Fallback: read from LAS file
        calipers_folder = os.path.join(well_data_folder, "calipers")
        log_path = os.path.join(calipers_folder, log_name)

        if not os.path.exists(log_path):
            return jsonify({"error": f"Log file not found: {log_name}"}), 404

        logs_info_path = os.path.join(well_data_folder, "logs_information.json")
        finger_name = "D"
        finger_units = ""
        if os.path.exists(logs_info_path):
            with open(logs_info_path, "r") as f:
                logs_info = json.load(f)
            log_info = logs_info.get("logs", {}).get(log_name, {})
            finger_name = log_info.get("finger_name") or "D"
            finger_units = log_info.get("finger_units") or ""

        las_file = lasio.read(log_path, ignore_data=False)
        df = las_file.df().sort_index()

        joint_df = df.loc[top_depth:bottom_depth]
        if joint_df.empty:
            return jsonify({"error": "No data in the specified depth range"}), 404

        finger_regex = rf"^{re.escape(finger_name)}\d{{1,2}}$"
        finger_cols = [c for c in joint_df.columns if re.match(finger_regex, c)]

        if not finger_cols:
            return jsonify({"error": f"No finger columns matching '{finger_name}N' found"}), 404

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

        return jsonify(
            {
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
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 400


LOGS_INFORMATION_FILENAME = "logs_information.json"
FMT_LOG_DATE = "%H-%M-%S %d-%m-%Y"  # used by co2_corrosion for log date strings
FMT_LOG_DATE_STORAGE = "%Y-%m-%d"  # stored in JSON as YYYY-MM-DD

_REQUIRED_LOG_INFO_FIELDS = (
    "date",
    "finger_units",
    "joint_identification_marker",
    "finger_name",
    "max_column_name",
    "min_column_name",
    "average_column_name",
)


def _get_logs_information_path(well_data_folder):
    return os.path.join(well_data_folder, LOGS_INFORMATION_FILENAME)


def _load_logs_information(well_data_folder):
    """Load full logs_information.json. Returns dict with key: logs."""
    path = _get_logs_information_path(well_data_folder)
    empty = {"logs": {}}
    if not os.path.exists(path):
        return empty
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return empty
        return {"logs": data.get("logs", {})}
    except (json.JSONDecodeError, IOError):
        return empty


def _read_logs_information_full(well_data_folder):
    """Read raw logs_information.json dict (for merging and saving)."""
    path = _get_logs_information_path(well_data_folder)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError):
        return {}


def _save_logs_information(well_data_folder, data):
    """Write logs_information.json atomically."""
    if not os.path.exists(well_data_folder):
        os.makedirs(well_data_folder)
    path = _get_logs_information_path(well_data_folder)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _log_has_required_info(log_info):
    """Check whether a log entry has all required metadata fields filled."""
    if not isinstance(log_info, dict):
        return False
    return all(
        [
            bool((log_info.get("date") or "").strip()),
            bool((log_info.get("finger_units") or "").strip()),
            bool((log_info.get("joint_identification_marker") or "").strip()),
            bool((log_info.get("finger_name") or "").strip()),
            bool((log_info.get("max_column_name") or "").strip()),
            bool((log_info.get("min_column_name") or "").strip()),
            bool((log_info.get("average_column_name") or "").strip()),
        ]
    )


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_log_info", methods=["POST"])
def get_log_info():
    """Get metadata for a single log from logs_information.json."""
    try:
        if app_instance is None:
            return jsonify({"error": "Plant not loaded."}), 400
        selected_well = request.json.get("selected_well")
        log_name = request.json.get("log_name")
        if not selected_well or not log_name:
            return jsonify({"error": "Missing selected_well or log_name"}), 400
        well_data_folder = os.path.join(
            app_instance.plant.project_path,
            app_instance.plant.name + "/wims_data",
            selected_well,
        )
        info = _load_logs_information(well_data_folder)
        log_entry = info["logs"].get(log_name, {})
        return jsonify({"log_name": log_name, "info": log_entry})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/save_log_info", methods=["POST"])
def save_log_info():
    """Save metadata for a single log into logs_information.json.

    Enforces single-baseline: if is_baseline is True, clears baseline from all other logs.
    """
    try:
        if app_instance is None:
            return jsonify({"error": "Plant not loaded."}), 400
        selected_well = request.json.get("selected_well")
        log_name = request.json.get("log_name")
        log_info = request.json.get("info")
        if not selected_well or not log_name:
            return jsonify({"error": "Missing selected_well or log_name"}), 400
        if not isinstance(log_info, dict):
            return jsonify({"error": "info must be an object"}), 400

        well_data_folder = os.path.join(
            app_instance.plant.project_path,
            app_instance.plant.name + "/wims_data",
            selected_well,
        )
        data = _read_logs_information_full(well_data_folder)
        if "logs" not in data:
            data["logs"] = {}

        entry = {
            "date": (log_info.get("date") or "").strip(),
            "is_baseline": bool(log_info.get("is_baseline")),
            "finger_units": (log_info.get("finger_units") or "").strip(),
            "joint_identification_marker": (
                log_info.get("joint_identification_marker") or ""
            ).strip(),
            "depth_corrected": bool(log_info.get("depth_corrected")),
            "finger_name": (log_info.get("finger_name") or "").strip(),
            "max_column_name": (log_info.get("max_column_name") or "").strip(),
            "min_column_name": (log_info.get("min_column_name") or "").strip(),
            "average_column_name": (log_info.get("average_column_name") or "").strip(),
        }

        if log_info.get("min_marker_score") is not None:
            entry["min_marker_score"] = float(log_info["min_marker_score"])
        if log_info.get("min_gradient_score") is not None:
            entry["min_gradient_score"] = float(log_info["min_gradient_score"])

        if entry["is_baseline"]:
            for other_name, other_entry in data["logs"].items():
                if isinstance(other_entry, dict) and other_name != log_name:
                    other_entry["is_baseline"] = False

        data["logs"][log_name] = entry
        _save_logs_information(well_data_folder, data)
        return jsonify({"message": "Log info saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/delete_log", methods=["POST"])
def delete_log():
    """Delete a log file, processed result file, and metadata entry for a selected well."""
    try:
        if app_instance is None:
            return jsonify({"error": "Plant not loaded."}), 400

        selected_well = request.json.get("selected_well")
        log_name = request.json.get("log_name")
        if not selected_well or not log_name:
            return jsonify({"error": "Missing selected_well or log_name"}), 400

        well_data_folder = os.path.join(
            app_instance.plant.project_path,
            app_instance.plant.name + "/wims_data",
            selected_well,
        )
        calipers_folder = os.path.join(well_data_folder, "calipers")
        processed_folder = os.path.join(well_data_folder, "processed_logs")

        log_path = os.path.join(calipers_folder, log_name)
        processed_name = log_name.replace(".las", "_processed.json")
        processed_path = os.path.join(processed_folder, processed_name)

        removed_any = False
        if os.path.exists(log_path):
            os.remove(log_path)
            removed_any = True
        if os.path.exists(processed_path):
            os.remove(processed_path)
            removed_any = True

        data = _read_logs_information_full(well_data_folder)
        logs_map = data.get("logs", {}) if isinstance(data.get("logs", {}), dict) else {}
        if log_name in logs_map:
            logs_map.pop(log_name, None)
            data["logs"] = logs_map
            _save_logs_information(well_data_folder, data)
            removed_any = True

        if not removed_any:
            return jsonify({"error": "Log not found"}), 404

        return jsonify({"message": "Log deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_log_dates", methods=["POST"])
def get_log_dates():
    """Get saved log dates for the selected well (from logs_information.json)."""
    try:
        if app_instance is None:
            return (
                jsonify({"error": "Plant not loaded. Select a field first.", "log_dates": {}}),
                400,
            )
        selected_well = request.json.get("selected_well")
        if not selected_well:
            return jsonify({"error": "No well selected", "log_dates": {}}), 400
        well_data_folder = os.path.join(
            app_instance.plant.project_path,
            app_instance.plant.name + "/wims_data",
            selected_well,
        )
        info = _load_logs_information(well_data_folder)
        log_dates = {}
        for log_name, entry in info["logs"].items():
            if isinstance(entry, dict) and entry.get("date"):
                log_dates[log_name] = entry["date"]
        return jsonify({"log_dates": log_dates})
    except Exception as e:
        return jsonify({"error": str(e), "log_dates": {}}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/save_log_dates", methods=["POST"])
def save_log_dates():
    """Save log name -> date (YYYY-MM-DD) into logs_information.json.

    Updates the date field per log.
    """
    try:
        if app_instance is None:
            return jsonify({"error": "Plant not loaded. Select a field first."}), 400
        selected_well = request.json.get("selected_well")
        log_dates = request.json.get("log_dates")
        if not selected_well:
            return jsonify({"error": "No well selected"}), 400
        if log_dates is None or not isinstance(log_dates, dict):
            return jsonify({"error": "log_dates must be an object"}), 400
        well_data_folder = os.path.join(
            app_instance.plant.project_path,
            app_instance.plant.name + "/wims_data",
            selected_well,
        )
        data = _read_logs_information_full(well_data_folder)
        if "logs" not in data:
            data["logs"] = {}
        for log_name, date_val in log_dates.items():
            if log_name not in data["logs"]:
                data["logs"][log_name] = {}
            data["logs"][log_name]["date"] = date_val
        _save_logs_information(well_data_folder, data)
        return jsonify({"message": "Log dates saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/save_corrosion_limits", methods=["POST"])
def save_corrosion_limits():
    """Stub for minimum_remaining_thickness_mm persistence.

    No longer stored in logs_information.json (to be redesigned).
    """
    return jsonify({"message": "Corrosion limits saved"})


@app_wellintegrity_monitoring.route(
    "/app/wellintegrity/get_corrosion_rate_from_logs", methods=["POST"]
)
def get_corrosion_rate_from_logs():
    """Compute corrosion rate from processed logs for panel display.

    Reads saved JSONs and returns corrosion rate data.
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
        logs_map = app_instance.inputs.get("logs_metadata", {})
        fmt_log = FMT_LOG_DATE

        entries_with_date = []
        for file_path in files:
            base = os.path.basename(file_path)
            log_name = base.replace("_processed.json", ".las")
            log_entry = logs_map.get(log_name, {})
            saved = log_entry.get("date") if isinstance(log_entry, dict) else None
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
                    "message": (
                        "Define and save log dates for at least one processed log, "
                        "then click Calculate."
                    ),
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
        saved_start = request.json.get("start_time")
        if not saved_start or not str(saved_start).strip():
            return jsonify(
                {
                    "corrosion_rate": None,
                    "message": "Provide a baseline date (start_time) to calculate corrosion rate.",
                }
            )
        try:
            start_dt = datetime.strptime(str(saved_start).strip(), FMT_LOG_DATE_STORAGE)
            start_time = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return jsonify(
                {
                    "corrosion_rate": None,
                    "message": "Baseline date (start_time) must be YYYY-MM-DD.",
                }
            )
        app_instance.inputs["start_time"] = start_time
        app_instance.inputs["uploadedLogs"] = {
            "name": log_names,
            "date": log_dates,
            "data": [None] * len(log_names),
        }
        app_instance.outputs["processedLogs"] = processed_dfs

        app_instance.get_corrosion_rate_from_logs()
        measured = app_instance.outputs.get("measuredCorrosionRate")
        if measured is None:
            return jsonify({"corrosion_rate": None, "message": "Corrosion rate not calculated"})

        # Compute remaining days to min. thickness if provided in request
        min_thickness = request.json.get("minimum_remaining_thickness_mm")
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
        # Use n_joints as target length so column lengths always match
        # (avoid pandas "length of values does not match index" when switching wells)
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


def _serialize_erosion_segments(segment_results):
    """Convert segment results to JSON-serializable dicts."""
    serialized = []
    for seg in segment_results:
        row = {}
        for key, val in seg.items():
            if val is None:
                row[key] = None
            elif isinstance(val, (np.floating, float)):
                row[key] = float(val) if np.isfinite(val) else None
            else:
                row[key] = val
        serialized.append(row)
    return serialized


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_esp_geometry", methods=["POST"])
def get_esp_geometry():
    """Load ESP geometry JSON for a well (or default template)."""
    try:
        if erosion_app_instance is None:
            return jsonify({"error": "Plant not loaded"}), 400

        selected_well = request.json.get("selected_well")
        if not selected_well:
            return jsonify({"error": "No well selected"}), 400

        erosion_app_instance.select_unit(selected_well)
        geometry = erosion_app_instance.load_esp_geometry()
        plant_esp_depth_m = erosion_app_instance._get_esp_depth_m()
        tally_geometry = {}
        if erosion_app_instance._get_well_type() == "productionwell":
            tally_geometry = erosion_app_instance.get_production_geometry_from_tally(geometry)

        return jsonify(
            {
                "esp_geometry": geometry,
                "plant_esp_depth_m": plant_esp_depth_m,
                "well_type": erosion_app_instance._get_well_type(),
                **tally_geometry,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/save_esp_geometry", methods=["POST"])
def save_esp_geometry():
    """Save ESP geometry JSON for a well."""
    try:
        if erosion_app_instance is None:
            return jsonify({"error": "Plant not loaded"}), 400

        selected_well = request.json.get("selected_well")
        geometry = request.json.get("esp_geometry")
        if not selected_well:
            return jsonify({"error": "No well selected"}), 400
        if not isinstance(geometry, dict):
            return jsonify({"error": "esp_geometry must be a JSON object"}), 400

        erosion_app_instance.select_unit(selected_well)
        erosion_app_instance.save_esp_geometry(geometry)
        return jsonify({"message": "ESP geometry saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/calculate_erosion", methods=["POST"])
def calculate_erosion():
    """Forward erosion calculation from well tally geometry and production data."""
    try:
        if erosion_app_instance is None:
            return jsonify({"error": "Plant not loaded"}), 400

        selected_well = request.json.get("selected_well")
        start_time = request.json.get("start_time")
        end_time = request.json.get("end_time")
        erosion_model = request.json.get("erosion_model", "DNVGL")
        erosion_params = request.json.get("erosion_params") or {}
        tubing_id_inch = request.json.get("tubing_id_inch")

        if not selected_well:
            return jsonify({"error": "No well selected"}), 400
        if not start_time or not end_time:
            return jsonify({"error": "start_time and end_time are required"}), 400

        erosion_app_instance.select_unit(selected_well)
        erosion_app_instance.inputs["start_time"] = f"{start_time} 00:00:00"
        erosion_app_instance.inputs["end_time"] = f"{end_time} 23:59:59"

        esp_geometry = erosion_app_instance.load_esp_geometry()
        inline_geometry = request.json.get("esp_geometry")
        if isinstance(inline_geometry, dict) and inline_geometry.get("components"):
            esp_geometry = inline_geometry

        if tubing_id_inch is None and isinstance(esp_geometry, dict):
            saved_tubing_id_inch = esp_geometry.get("production_tubing_id_inch")
            if saved_tubing_id_inch is not None and float(saved_tubing_id_inch) > 0:
                tubing_id_inch = float(saved_tubing_id_inch)

        result = erosion_app_instance.calculate_erosion(
            erosion_model,
            erosion_params,
            esp_geometry=esp_geometry,
            tubing_id_inch=tubing_id_inch,
        )

        segments = _serialize_erosion_segments(result.get("segments") or [])
        summary = result.get("summary") or {}

        return jsonify(
            {
                "status": result.get("status", "ok"),
                "well_type": result.get("well_type"),
                "esp_depth_m": result.get("esp_depth_m"),
                "segments": segments,
                "summary": summary,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/optimize_corrosion", methods=["POST"])
def optimize_corrosion():
    """Kick off a Celery task to calibrate corrosion model parameters against logs."""
    try:
        selected_well = request.json.get("selected_well")
        if not selected_well:
            return jsonify({"error": "No well selected"}), 400

        project_folder_path = app_instance.plant.project_path
        project_name = app_instance.plant.name

        task = wellintegrity_app_optimize_corrosion.delay(
            project_folder_path, project_name, selected_well
        )
        return jsonify({"task_id": task.id})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/optimization_status", methods=["POST"])
def optimization_status():
    """Report whether calibrated corrosion parameters exist for a well.

    Looks up the persisted ``corrosion_opt_params.json`` for the selected well
    and returns whether it exists plus when it was last written (the embedded
    ``optimized_at`` stamp, falling back to the file modification time). The
    Forecast UI uses this to show a "last optimized" note and to gate the Run
    (predict) button until calibration has been performed.
    """
    try:
        # -- guard: no plant loaded yet -------------------------------------
        if app_instance is None:
            return jsonify({"optimized": False, "optimized_at": None})

        selected_well = request.json.get("selected_well")
        if not selected_well:
            return jsonify({"error": "No well selected"}), 400

        # -- resolve the persisted params path for this well ----------------
        app_instance.select_unit(selected_well)
        params_path = app_instance._corrosion_opt_params_path()
        if not params_path or not os.path.exists(params_path):
            return jsonify({"optimized": False, "optimized_at": None})

        # -- prefer embedded stamp, fall back to file modification time -----
        optimized_at = None
        try:
            with open(params_path, "r", encoding="utf-8") as f:
                optimized_at = json.load(f).get("optimized_at")
        except (OSError, json.JSONDecodeError):
            optimized_at = None
        if not optimized_at:
            mtime = os.path.getmtime(params_path)
            optimized_at = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")

        return jsonify({"optimized": True, "optimized_at": optimized_at})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/predict_corrosion", methods=["POST"])
def predict_corrosion():
    """Kick off a Celery task to predict remaining wall thickness from logs to now."""
    try:
        selected_well = request.json.get("selected_well")
        if not selected_well:
            return jsonify({"error": "No well selected"}), 400

        project_folder_path = app_instance.plant.project_path
        project_name = app_instance.plant.name

        task = wellintegrity_app_predict_corrosion.delay(
            project_folder_path, project_name, selected_well
        )
        return jsonify({"task_id": task.id})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/forecast_years_to_min", methods=["POST"])
def forecast_years_to_min():
    """Kick off a Celery task forecasting years-to-min-thickness per casing.

    Accepts the per-casing minimum thicknesses entered in the dashboard Wall
    thickness table and projects the calibrated model's trailing-12-month
    corrosion rate forward to estimate when each casing reaches its minimum.
    """
    try:
        selected_well = request.json.get("selected_well")
        if not selected_well:
            return jsonify({"error": "No well selected"}), 400

        casings = request.json.get("casings") or []

        project_folder_path = app_instance.plant.project_path
        project_name = app_instance.plant.name

        task = wellintegrity_app_forecast_years_to_min.delay(
            project_folder_path, project_name, selected_well, casings
        )
        return jsonify({"task_id": task.id})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route(
    "/app/wellintegrity/corrosion_task_status/<task_id>", methods=["GET"]
)
def corrosion_task_status(task_id):
    """Poll the status of a corrosion Celery task.

    For in-progress tasks that publish a PROGRESS meta dict (e.g. the per-joint
    corrosion optimization), the meta is returned under ``progress`` so the
    frontend can render live progress.
    """
    result = celery.AsyncResult(task_id)
    if result.state == "SUCCESS":
        return jsonify({"state": "SUCCESS", "result": result.result})
    elif result.state == "FAILURE":
        return jsonify({"state": "FAILURE", "error": str(result.info)})
    else:
        progress = result.info if isinstance(result.info, dict) else None
        return jsonify({"state": result.state, "progress": progress})


# @app_wellintegrity_monitoring.route("/app/wellintegrity/get_pressure_elements", methods=["POST"])
# def get_pressure_elements():
#     """Retrieve pressure elements from the loaded schematic for integrity monitoring.."""
#     try:
#         selected_well = request.json.get("selected_well")
#         schematic_filename = request.json.get("schematic_filename")

#         if not selected_well or not schematic_filename:
#             return jsonify({"error": "Missing well name or schematic filename"}), 400

#         # Create path to schematic file
#         project_data_folder = os.path.join(
#             app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
#         )
#         well_data_folder = os.path.join(project_data_folder, selected_well, "schematics")
#         schematic_path = os.path.join(well_data_folder, schematic_filename)

#         if not os.path.exists(schematic_path):
#             return jsonify({"error": "Schematic file not found"}), 404

#         # Load the JSON data
#         with open(schematic_path, "r") as f:
#             schematic_data = json.load(f)

#         # Build well from JSON and get pressure elements
#         well = build_well_from_json(schematic_data)
#         pressure_elements = well.get_pressure_elements()

#         # Convert pressure elements to serializable format
#         elements_data = []
#         for elem in pressure_elements:
#             elements_data.append(
#                 {
#                     "id": elem.id,
#                     "name": elem.unit_name,
#                     "type": elem.element_type,
#                     "sealed": getattr(elem, "is_sealed", None),
#                     "depth": getattr(elem, "depth", None),
#                     "pressure": getattr(elem, "pressure", None),
#                 }
#             )

#         return jsonify({"pressure_elements": elements_data, "count": len(elements_data)})

#     except Exception as e:
#         return jsonify({"error": str(e)}), 400


# @app_wellintegrity_monitoring.route("/app/wellintegrity/get_annulus_readings", methods=["POST"])
# def get_annulus_readings():
#     """Get annulus information from the schematic for monitoring."""
#     try:
#         selected_well = request.json.get("selected_well")
#         schematic_filename = request.json.get("schematic_filename")

#         if not selected_well or not schematic_filename:
#             return jsonify({"error": "Missing well name or schematic filename"}), 400

#         # Select the unit to access tags
#         app_instance.select_unit(selected_well)

#         # Create path to schematic file
#         project_data_folder = os.path.join(
#             app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
#         )
#         well_data_folder = os.path.join(project_data_folder, selected_well, "schematics")
#         schematic_path = os.path.join(well_data_folder, schematic_filename)

#         if not os.path.exists(schematic_path):
#             return jsonify({"error": "Schematic file not found"}), 404

#         # Load the JSON data
#         with open(schematic_path, "r") as f:
#             schematic_data = json.load(f)

#         # Build well from JSON and get annuluses
#         well = build_well_from_json(schematic_data)
#         annuluses = well.get_all_annuluses()

#         # Convert annuluses to serializable format
#         annulus_data = []
#         for annulus in annuluses:
#             annulus_data.append(
#                 {
#                     "annulus_id": annulus["annulus_id"],
#                     "outer_unit": annulus["outer_unit"],
#                     "inner_unit": (
#                         annulus["inner_unit"] if annulus["inner_unit"] else "Open hole"
#                     ),
#                     "depth_top": annulus["depth_range"]["top"],
#                     "depth_bottom": annulus["depth_range"]["bottom"],
#                     "fluid_count": len(annulus["fluids"]),
#                     "fluids": annulus["fluids"],
#                 }
#             )

#         return jsonify({"annulus_data": annulus_data, "count": len(annulus_data)})

#     except Exception as e:
#         return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_annulus_information", methods=["POST"])
def get_annulus_information():
    """Get annulus information from the external API.

    Sends schematic JSON with return_annulus_information=True.
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
        backend_url = "http://185.92.222.87:8001/generate"

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

        # -- convert tags to serializable format ----------------------
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


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_tag_series", methods=["POST"])
def get_tag_series():
    """Return a tag's recent time series (default last 30 days) for annulus charts."""
    try:
        body = request.get_json(silent=True) or {}
        selected_well = body.get("selected_well")
        tag_name = body.get("tag_name")
        days = int(body.get("days", 30) or 30)

        if not selected_well or not tag_name:
            return jsonify({"error": "Missing well name or tag name"}), 400

        # -- select unit and resolve tag ------------------------------
        app_instance.select_unit(selected_well)
        measured_tags = app_instance.unit.tags.get("measured", {})
        if tag_name not in measured_tags:
            return jsonify({"error": f"Tag '{tag_name}' not found"}), 404

        tag_info = measured_tags[tag_name]

        # -- read last <days> of data from internal database ----------
        timestamps = []
        values = []
        try:
            from datetime import datetime, timedelta, timezone

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=days)
            start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            end_time_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            timestep_s = 86400  # daily resolution

            full_tag_name = f"{tag_name}.measured"
            result, time_data = app_instance.plant.database.read_internal_database(
                app_instance.plant.name,
                app_instance.unit.name,
                full_tag_name,
                start_time_str,
                end_time_str,
                timestep_s,
            )

            # -- drop empty (None) samples ----------------------------
            if result is not None and time_data is not None:
                for t_str, val in zip(time_data, result):
                    if val is None:
                        continue
                    timestamps.append(t_str)
                    values.append(val)
        except Exception as db_error:
            print(f"Database read error for tag series {tag_name}: {db_error}")

        return jsonify(
            {
                "tag_name": tag_name,
                "unit": getattr(tag_info, "unit", ""),
                "description": getattr(tag_info, "description", tag_name),
                "timestamps": timestamps,
                "values": values,
                "success": True,
            }
        )

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
    """Save WIMS panel state for the selected well and schematic.

    Persists overall status, last update date, and barrier elements.
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


def _format_inch_fraction(value):
    """Format a decimal inch value as a whole + nearest-eighth fraction label.

    Casing/tubing sizes are quoted in 1/8" increments, e.g. 13.375 -> "13 3/8",
    9.625 -> "9 5/8", 7.0 -> "7".
    """
    try:
        v_inch = float(value)
    except (TypeError, ValueError):
        return str(value)

    # -- split into whole inches and eighths ----
    whole = int(v_inch)
    eighths = int(round((v_inch - whole) * 8))
    if eighths == 8:
        whole += 1
        eighths = 0

    # -- no fractional part -----
    if eighths == 0:
        return str(whole)

    # -- reduce the eighths fraction -----
    divisor = gcd(eighths, 8)
    numerator = eighths // divisor
    denominator = 8 // divisor
    if whole == 0:
        return f"{numerator}/{denominator}"
    return f"{whole} {numerator}/{denominator}"


@app_wellintegrity_monitoring.route("/app/wellintegrity/get_tally_sizes", methods=["POST"])
def get_tally_sizes():
    """Return unique casing OD sizes (largest-first) from the well tally.

    Drives the auto-populated casing rows of the KPI dashboard wall-thickness
    panel. Reads the tally from well parameters (same source as init_parameters).
    """
    try:
        if app_instance is None:
            return jsonify({"sizes": []})

        selected_well = request.json.get("selected_well")
        if not selected_well:
            return jsonify({"error": "No well selected", "sizes": []}), 400

        # -- read tally from well parameters -----
        app_instance.select_unit(selected_well)
        well_tally = app_instance._get_tally_from_well_parameters()
        if not well_tally:
            return jsonify({"sizes": []})

        # -- collect unique OD values [inch], largest-first ----
        seen = set()
        od_values_inch = []
        for entry in well_tally:
            if not isinstance(entry, dict):
                continue
            od = entry.get("OD")
            if od is None:
                continue
            try:
                od_inch = float(od)
            except (TypeError, ValueError):
                continue
            key = round(od_inch, 4)
            if key in seen:
                continue
            seen.add(key)
            od_values_inch.append(od_inch)

        od_values_inch.sort(reverse=True)

        # -- format each size to a fractional-inch label -----
        sizes = [
            {"od_inch": od_inch, "label": _format_inch_fraction(od_inch)}
            for od_inch in od_values_inch
        ]

        return jsonify({"sizes": sizes})

    except Exception as e:
        return jsonify({"error": str(e), "sizes": []}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/save_dashboard", methods=["POST"])
def save_dashboard():
    """Save KPI dashboard state (manual fields) for the selected well and schematic."""
    try:
        selected_well = request.json.get("selected_well")
        schematic_filename = request.json.get("schematic_filename")
        dashboard_data = request.json.get("dashboard_data")

        if not selected_well or not schematic_filename:
            return jsonify({"error": "Missing well name or schematic filename"}), 400
        if dashboard_data is None:
            return jsonify({"error": "Missing dashboard_data"}), 400

        # -- build dashboard folder path -----
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        dashboard_folder = os.path.join(well_data_folder, "dashboard")

        if not os.path.exists(dashboard_folder):
            os.makedirs(dashboard_folder)

        # -- write JSON keyed by schematic name -----
        schematic_name = schematic_filename.replace(".json", "")
        dashboard_file = os.path.join(dashboard_folder, f"{schematic_name}_dashboard.json")

        with open(dashboard_file, "w") as f:
            json.dump(dashboard_data, f, indent=2)

        return jsonify({"message": "Dashboard saved successfully"})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/load_dashboard", methods=["POST"])
def load_dashboard():
    """Load KPI dashboard state for the selected well and schematic."""
    try:
        selected_well = request.json.get("selected_well")
        schematic_filename = request.json.get("schematic_filename")

        if not selected_well or not schematic_filename:
            return jsonify({"error": "Missing well name or schematic filename"}), 400

        # -- build dashboard file path -----
        project_data_folder = os.path.join(
            app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
        )
        well_data_folder = os.path.join(project_data_folder, selected_well)
        dashboard_folder = os.path.join(well_data_folder, "dashboard")
        schematic_name = schematic_filename.replace(".json", "")
        dashboard_file = os.path.join(dashboard_folder, f"{schematic_name}_dashboard.json")

        if not os.path.exists(dashboard_file):
            return jsonify({"dashboard_data": None})

        # -- read and return saved state -----
        with open(dashboard_file, "r") as f:
            dashboard_data = json.load(f)

        return jsonify({"dashboard_data": dashboard_data})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


HISTORY_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".txt",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".zip",
    ".las",
}


def _history_documents_folder(selected_well, schematic_filename):
    """Return the on-disk folder for history entry attachments."""
    project_data_folder = os.path.join(
        app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
    )
    well_data_folder = os.path.join(project_data_folder, selected_well)
    schematic_name = schematic_filename.replace(".json", "")
    docs_folder = os.path.join(well_data_folder, "dashboard", "history_documents", schematic_name)
    return docs_folder


def _history_document_path(docs_folder, document_id):
    """Resolve stored file path for a history document id."""
    if not document_id or not os.path.isdir(docs_folder):
        return None, None
    matches = glob.glob(os.path.join(docs_folder, f"{document_id}.*"))
    if not matches:
        return None, None
    return matches[0], os.path.basename(matches[0])


def _delete_history_document_file(docs_folder, document_id):
    """Remove all stored files for a history document id."""
    stored_path, _ = _history_document_path(docs_folder, document_id)
    if stored_path and os.path.isfile(stored_path):
        os.remove(stored_path)


@app_wellintegrity_monitoring.route("/app/wellintegrity/upload_history_document", methods=["POST"])
def upload_history_document():
    """Upload a document attached to a dashboard history entry."""
    try:
        if "history_document" not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files["history_document"]
        if not file or file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        selected_well = (request.form.get("selected_well") or "").strip()
        schematic_filename = (request.form.get("schematic_filename") or "").strip()
        document_id = (request.form.get("document_id") or "").strip()

        if not selected_well or not schematic_filename:
            return jsonify({"error": "Missing well name or schematic filename"}), 400
        if not document_id:
            return jsonify({"error": "Missing document_id"}), 400

        original_name = secure_filename(file.filename) or "document"
        ext = os.path.splitext(original_name)[1].lower()
        if ext not in HISTORY_DOCUMENT_EXTENSIONS:
            return jsonify({"error": f"File type not allowed: {ext or '(none)'}"}), 400

        docs_folder = _history_documents_folder(selected_well, schematic_filename)
        os.makedirs(docs_folder, exist_ok=True)

        _delete_history_document_file(docs_folder, document_id)
        stored_name = f"{document_id}{ext}"
        file.save(os.path.join(docs_folder, stored_name))

        return jsonify(
            {
                "message": "Document uploaded successfully",
                "document_id": document_id,
                "document_filename": original_name,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/history_document", methods=["GET"])
def download_history_document():
    """Download a document attached to a dashboard history entry."""
    try:
        selected_well = (request.args.get("selected_well") or "").strip()
        schematic_filename = (request.args.get("schematic_filename") or "").strip()
        document_id = (request.args.get("document_id") or "").strip()
        download_name = (request.args.get("document_filename") or "").strip()

        if not selected_well or not schematic_filename or not document_id:
            return jsonify({"error": "Missing well, schematic, or document_id"}), 400

        docs_folder = _history_documents_folder(selected_well, schematic_filename)
        stored_path, _ = _history_document_path(docs_folder, document_id)
        if not stored_path:
            return jsonify({"error": "Document not found"}), 404

        if not download_name:
            download_name = os.path.basename(stored_path)

        return send_file(stored_path, as_attachment=True, download_name=download_name)

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_wellintegrity_monitoring.route("/app/wellintegrity/delete_history_document", methods=["POST"])
def delete_history_document():
    """Delete a document attached to a dashboard history entry."""
    try:
        selected_well = request.json.get("selected_well")
        schematic_filename = request.json.get("schematic_filename")
        document_id = request.json.get("document_id")

        if not selected_well or not schematic_filename or not document_id:
            return jsonify({"error": "Missing well, schematic, or document_id"}), 400

        docs_folder = _history_documents_folder(selected_well, schematic_filename)
        _delete_history_document_file(docs_folder, document_id)

        return jsonify({"message": "Document deleted successfully"})

    except Exception as e:
        return jsonify({"error": str(e)}), 400
