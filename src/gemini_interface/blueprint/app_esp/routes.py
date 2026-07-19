"""
ESP Application Routes.

======================

This module handles ESP (Electric Submersible Pump) analysis and monitoring functionality including
pump head curve calculations and ESP performance analysis.
"""

import json
import os

from celery import Celery
from flask import Blueprint, current_app, jsonify, request

from gemini_application.esp.esp import ESPApp
from gemini_framework.modules.esp.unit import ESPUnit
from gemini_interface.blueprint.celerytasks import (
    esp_app_calibrate_pumphead_data,
    esp_app_get_pumphead_data,
    esp_app_predict_failure,
)

# Create the ESP application blueprint
app_esp = Blueprint("app_esp", __name__)

# Initialize Celery for background task processing
celery = Celery(
    "gemini-celery-app",
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379"),
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379"),
)

# Global application instance for ESP operations
app_instance = None


@app_esp.route("/app/esp/load_plant", methods=["POST"])
def load_plant():
    """Load a plant into the ESP application instance."""
    global app_instance

    app_instance = ESPApp()

    project_name = request.json["field_name"]
    project_folder_path = current_app.config["GEMINI_PROJECT_FOLDER"]

    app_instance.load_plant(project_folder_path, project_name)

    return "OK"


@app_esp.route("/app/esp/get_esp_list", methods=["POST"])
def get_esp_list():
    """Get list of ESP units in the loaded plant."""
    esp_unit_list = []
    for unit in app_instance.plant.units:
        if isinstance(unit, ESPUnit):
            esp_unit_list.append(unit.name)

    return jsonify(esp_unit_list)


@app_esp.route("/app/esp/calculate_pump_curve", methods=["POST"])
def calculate_pump_curve():
    """Calculate pump head curves for ESP analysis."""
    inputs = {"parameters": request.json["parameters"], "boundary": request.json["boundary"]}

    project_folder_path = app_instance.plant.project_path
    project_name = app_instance.plant.name
    esp_name = app_instance.unit.name

    task = esp_app_get_pumphead_data.delay(project_folder_path, project_name, esp_name, inputs)

    task_id = str(task.id)

    return task_id


@app_esp.route("/app/esp/get_results_pump_curve", methods=["POST"])
def get_results_pump_curve():
    """Get results from the pump curve calculation task."""
    task_id = request.json["task_id"]
    task_result = celery.AsyncResult(task_id)

    try:
        result_data = task_result.result
        if isinstance(result_data, Exception):
            result_data = str(result_data)
    except Exception as e:
        result_data = f"Error reading result: {e}"

    result = {"task_id": task_id, "task_status": task_result.status, "task_result": result_data}

    return jsonify(result)


@app_esp.route("/app/esp/get_esp_parameters", methods=["POST"])
def get_esp_parameters():
    """Get parameters for the selected ESP unit."""
    esp_name = request.json["esp_name"]
    app_instance.select_unit(esp_name)

    esp_par = app_instance.unit.parameters

    return {"esp_par": esp_par}


@app_esp.route("/app/esp/calibrate_esp_factor", methods=["POST"])
def calibrate_esp_factor():
    """Calibrate ESP correction factors."""
    inputs = {"parameters": request.json["parameters"], "boundary": request.json["boundary"]}

    project_folder_path = app_instance.plant.project_path
    project_name = app_instance.plant.name
    esp_name = app_instance.unit.name

    task = esp_app_calibrate_pumphead_data.delay(
        project_folder_path, project_name, esp_name, inputs
    )

    return str(task.id)


@app_esp.route("/app/esp/get_results_calibration_factor", methods=["POST"])
def get_results_calibration_factor():
    """Get results from the ESP calibration factor task."""
    task_id = request.json["task_id"]
    task_result = celery.AsyncResult(task_id)
    try:
        result_data = task_result.result
        if isinstance(result_data, Exception):
            result_data = str(result_data)
    except Exception as e:
        result_data = f"Error reading result: {e}"

    result = {"task_id": task_id, "task_status": task_result.status, "task_result": result_data}

    return jsonify(result)


@app_esp.route("/esp/update_correction_factors", methods=["POST"])
def update_correction_factors():
    """Update ESP correction factors in the project parameters."""
    try:
        field_name = request.json["field_name"]
        component_name = request.json["esp_name"]
        esp_correction_factor = request.json["esp_correction_factor"]

        if not isinstance(esp_correction_factor, str) or ";" not in esp_correction_factor:
            return jsonify({"message": "Invalid input"}), 400

        project_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], field_name)
        param_path = os.path.join(project_folder_path, f"{component_name}.param")

        with open(param_path, "r") as jsonfile:
            component_content = json.load(jsonfile)

        if "parameters" in component_content and "property" in component_content["parameters"]:
            component_content["parameters"]["property"]["esp_correction_factor"] = [
                esp_correction_factor
            ]
        else:
            return jsonify({"message": "Invalid input"}), 500

        with open(param_path, "w") as jsonfile:
            json.dump(component_content, jsonfile, indent=4, sort_keys=True)

        return jsonify({"message": "Correction factor updated successfully."})

    except Exception as e:
        return jsonify({"message": f"Internal server error: {str(e)}"}), 500


@app_esp.route("/app/esp/predict_failure", methods=["POST"])
def predict_failure():
    """Predict ESP failures using ML model."""
    inputs = {"parameters": request.json["parameters"], "boundary": request.json["boundary"]}

    project_folder_path = app_instance.plant.project_path
    project_name = app_instance.plant.name
    esp_name = app_instance.unit.name

    task = esp_app_predict_failure.delay(project_folder_path, project_name, esp_name, inputs)

    return str(task.id)


@app_esp.route("/app/esp/get_results_failure_prediction", methods=["POST"])
def get_results_failure_prediction():
    """Get results from the failure prediction task."""
    try:
        task_id = request.json["task_id"]
        task_result = celery.AsyncResult(task_id)

        try:
            result_data = task_result.result
            if isinstance(result_data, Exception):
                result_data = str(result_data)
        except Exception as e:
            result_data = f"Error reading result: {e}"

        result = {"task_id": task_id, "task_status": task_result.status, "task_result": result_data}

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Error processing request: {str(e)}"}), 500
