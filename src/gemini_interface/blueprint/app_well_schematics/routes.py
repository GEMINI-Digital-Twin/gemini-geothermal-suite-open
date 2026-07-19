"""
Well Schematics Application Routes.

==================================

This module handles well schematic generation and CO2 corrosion analysis including caliper log
processing and corrosion pattern analysis.
"""

import glob
import json
import os
import re
from datetime import datetime, timezone

import requests
from celery import Celery
from flask import Blueprint, current_app, jsonify, request

# TODO: Change to well integrity application
from gemini_application.wims.corrosion_model import CO2CorrosionApplication
from gemini_framework.modules.injectionwell.unit import InjectionWellUnit
from gemini_framework.modules.productionwell.unit import ProductionWellUnit

# Create the well schematics application blueprint
app_well_schematics = Blueprint("app_well_schematics", __name__)

# Initialize Celery for background task processing
celery = Celery(
    "gemini-celery-app",
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379"),
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379"),
)


def _sanitize_schematic_name(schematic_name):
    """Strip path separators and unsafe characters from a schematic filename stem."""
    if not schematic_name or not str(schematic_name).strip():
        return None
    name = str(schematic_name).strip()
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = name.replace("..", "_")
    return name if name else None


def _well_schematics_folder(selected_well):
    """Return the on-disk schematics folder for a well."""
    project_data_folder = os.path.join(
        app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
    )
    return os.path.join(project_data_folder, selected_well, "schematics")


@app_well_schematics.route("/app/well_schematics/load_plant", methods=["POST"])
def load_plant():
    """Load a plant/project into the well schematics application instance."""
    global app_instance

    app_instance = CO2CorrosionApplication()

    project_name = request.json["field_name"]
    project_folder_path = current_app.config["GEMINI_PROJECT_FOLDER"]

    app_instance.load_plant(project_folder_path, project_name)

    return "OK"


@app_well_schematics.route("/app/well_schematics/get_well_list", methods=["POST"])
def get_well_list():
    """Get list of well names (Injection or Production) from the loaded plant."""
    well_unit_list = []
    for unit in app_instance.plant.units:
        if isinstance(unit, InjectionWellUnit) or isinstance(unit, ProductionWellUnit):
            well_unit_list.append(unit.name)
    return jsonify(well_unit_list)


@app_well_schematics.route("/app/well_schematics/get_log_list", methods=["POST"])
def get_log_list():
    """Return a list of uploaded LAS log files for the selected well."""
    log_list = []

    selected_well = request.json.get("selected_well")

    project_data_folder = os.path.join(
        app_instance.plant.project_path, app_instance.plant.name + "/wims_data"
    )

    for unit in app_instance.plant.units:
        if selected_well == unit.name:
            print("DEBUG: ", unit.parameters)
            unit_data_folder = os.path.join(project_data_folder, unit.name)
            if not os.path.exists(unit_data_folder):
                os.makedirs(unit_data_folder)

            uploaded_logs = glob.glob(os.path.join(unit_data_folder, "*.las"))
            for file in uploaded_logs:
                log_list.append(os.path.basename(file))

    return jsonify(log_list)


@app_well_schematics.route("/app/well_schematics/get_saved_schematics", methods=["POST"])
def get_saved_schematics():
    """Get list of saved schematics for the selected well."""
    try:
        selected_well = request.json.get("selected_well")

        if not selected_well:
            return jsonify([])

        # Create schematics folder path
        well_data_folder = _well_schematics_folder(selected_well)

        if not os.path.exists(well_data_folder):
            return jsonify([])

        # Get all JSON files in the schematics folder
        schematic_files = glob.glob(os.path.join(well_data_folder, "*.json"))
        schematic_list = []

        for file_path in schematic_files:
            filename = os.path.basename(file_path)
            # Remove .json extension for display
            schematic_name = filename[:-5] if filename.endswith(".json") else filename
            modified_at = None
            try:
                mtime = os.path.getmtime(file_path)
                modified_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            except OSError:
                pass
            schematic_list.append(
                {
                    "name": schematic_name,
                    "filename": filename,
                    "path": file_path,
                    "modified_at": modified_at,
                }
            )

        schematic_list.sort(key=lambda item: item.get("name", "").lower())
        return jsonify(schematic_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_well_schematics.route("/app/well_schematics/load_schematic", methods=["POST"])
def load_schematic():
    """Load a specific schematic file for the selected well."""
    try:
        selected_well = request.json.get("selected_well")
        schematic_filename = request.json.get("schematic_filename")

        if not selected_well or not schematic_filename:
            return jsonify({"error": "Missing well name or schematic filename"}), 400

        # Create path to schematic file
        well_data_folder = _well_schematics_folder(selected_well)
        schematic_path = os.path.join(well_data_folder, schematic_filename)

        if not os.path.exists(schematic_path):
            return jsonify({"error": "Schematic file not found"}), 404

        # Load and return the JSON data
        with open(schematic_path, "r") as f:
            schematic_data = json.load(f)

        return jsonify(schematic_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_well_schematics.route("/app/well_schematics/save_schematic", methods=["POST"])
def save_schematic():
    """Save a schematic for the selected well."""
    try:
        data = request.get_json()
        selected_well = data.get("selected_well")
        schematic_name = data.get("schematic_name")
        schematic_data = data.get("schematic_data")

        if not selected_well or not schematic_name or not schematic_data:
            return jsonify({"error": "Missing required data"}), 400

        safe_name = _sanitize_schematic_name(schematic_name)
        if not safe_name:
            return jsonify({"error": "Invalid schematic name"}), 400

        # Create schematics folder path
        well_data_folder = _well_schematics_folder(selected_well)

        # Create directory if it doesn't exist
        os.makedirs(well_data_folder, exist_ok=True)

        # Save schematic file
        filename = f"{safe_name}.json"
        schematic_path = os.path.join(well_data_folder, filename)

        with open(schematic_path, "w") as f:
            json.dump(schematic_data, f, indent=2)

        return jsonify({"message": "Schematic saved successfully", "filename": filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_well_schematics.route("/app/well_schematics/delete_schematic", methods=["POST"])
def delete_schematic():
    """Delete a saved schematic file for the selected well."""
    try:
        data = request.get_json()
        selected_well = data.get("selected_well")
        schematic_filename = data.get("schematic_filename")

        if not selected_well or not schematic_filename:
            return jsonify({"error": "Missing well name or schematic filename"}), 400

        if ".." in schematic_filename or "/" in schematic_filename or "\\" in schematic_filename:
            return jsonify({"error": "Invalid schematic filename"}), 400

        well_data_folder = _well_schematics_folder(selected_well)
        schematic_path = os.path.join(well_data_folder, schematic_filename)

        if not os.path.exists(schematic_path):
            return jsonify({"error": "Schematic file not found"}), 404

        os.remove(schematic_path)
        return jsonify({"message": "Schematic deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app_well_schematics.route("/app/well_schematics/generate_schematic", methods=["POST"])
def generate_schematic():
    """Proxy route to generate a well schematic image from external backend API."""
    try:
        schematic_data = request.get_json()

        # Forward request to external backend server
        backend_url = app_instance.plant.parameters["wims_backend_url"]
        response = requests.post(
            backend_url,
            json=schematic_data,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        # Check if request was successful
        response.raise_for_status()

        # Return the response from the backend
        return jsonify(response.json())
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to schematic generation server"}), 503
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
        return jsonify({"error": error_msg}), e.response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 400
