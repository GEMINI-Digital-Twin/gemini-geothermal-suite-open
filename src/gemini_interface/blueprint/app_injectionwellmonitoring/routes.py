"""
Injection Well Monitoring Application Routes.

============================================

This module handles injection well monitoring and analysis functionality including Hall integral
calculations and skin factor analysis.
"""

import os

from celery import Celery
from flask import Blueprint, current_app, jsonify, request

from gemini_application.injectionwell.injectionwell_monitoring import InjectionWellMonitoring
from gemini_framework.modules.injectionwell.unit import InjectionWellUnit
from gemini_interface.blueprint.celerytasks import (
    injectionwellmonitoring_app_calculate_hall_integral,
    injectionwellmonitoring_app_calculate_skin_lines,
)

# Create the injection well monitoring application blueprint
app_injectionwellmonitoring = Blueprint("app_injectionwellmonitoring", __name__)

# Initialize Celery for background task processing
celery = Celery(
    "gemini-celery-app",
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379"),
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379"),
)

# Global application instance for injection well operations
app_instance = None


@app_injectionwellmonitoring.route("/app/injectionwellmonitoring/load_plant", methods=["POST"])
def load_plant():
    """Load a plant/project into the injection well monitoring application instance."""
    global app_instance

    app_instance = InjectionWellMonitoring()

    project_name = request.json["field_name"]
    print(project_name)
    project_folder_path = current_app.config["GEMINI_PROJECT_FOLDER"]

    app_instance.load_plant(project_folder_path, project_name)

    return "OK"


@app_injectionwellmonitoring.route("/app/injectionwellmonitoring/get_well_list", methods=["POST"])
def get_well_list():
    """Get list of injection wells for monitoring."""
    well_unit_list = []
    for unit in app_instance.plant.units:
        if isinstance(unit, InjectionWellUnit):
            well_unit_list.append(unit.name)

    return jsonify(well_unit_list)


@app_injectionwellmonitoring.route(
    "/app/injectionwellmonitoring/calculate_hall_integral", methods=["POST"]
)
def calculate_hall_integral():
    """Calculate Hall integral for injection well monitoring."""
    inputs = {"parameters": request.json["parameters"], "boundary": request.json["boundary"]}

    project_folder_path = app_instance.plant.project_path
    project_name = app_instance.plant.name
    well_name = app_instance.unit.name

    task = injectionwellmonitoring_app_calculate_hall_integral.delay(
        project_folder_path, project_name, well_name, inputs
    )

    task_id = str(task.id)

    return task_id


@app_injectionwellmonitoring.route(
    "/app/injectionwellmonitoring/get_results_hall_integral", methods=["POST"]
)
def get_results_hall_integral():
    """Get results from the Hall integral calculation task."""
    task_id = request.json["task_id"]
    task_result = celery.AsyncResult(task_id)

    result = {
        "task_id": task_id,
        "task_status": task_result.status,
        "task_result": task_result.result,
    }
    print(result)
    return result


@app_injectionwellmonitoring.route(
    "/app/injectionwellmonitoring/calculate_skin_lines", methods=["POST"]
)
def calculate_skin_lines():
    """Calculate skin factor lines for injection well monitoring."""
    inputs = {"parameters": request.json["parameters"], "boundary": request.json["boundary"]}

    project_folder_path = app_instance.plant.project_path
    project_name = app_instance.plant.name
    well_name = app_instance.unit.name

    task = injectionwellmonitoring_app_calculate_skin_lines.delay(
        project_folder_path, project_name, well_name, inputs
    )

    task_id = str(task.id)

    return task_id


@app_injectionwellmonitoring.route(
    "/app/injectionwellmonitoring/get_results_skin_lines", methods=["POST"]
)
def get_results_skin_lines():
    """Get results from the skin lines calculation task."""
    task_id = request.json["task_id"]
    task_result = celery.AsyncResult(task_id)

    result = {
        "task_id": task_id,
        "task_status": task_result.status,
        "task_result": task_result.result,
    }
    print(result)
    return result


@app_injectionwellmonitoring.route("/app/injectionwellmonitoring/get_parameters", methods=["POST"])
def get_parameters():
    """Get parameters for the selected injection well."""
    well_name = request.json["well_name"]
    app_instance.select_unit(well_name)

    res_par = app_instance.unit.to_units[0].parameters
    well_par = app_instance.unit.parameters

    return {"res_par": res_par, "well_par": well_par}
