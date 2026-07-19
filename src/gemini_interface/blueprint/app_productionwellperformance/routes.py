"""
Production Well Performance Application Routes.

==============================================

This module handles production well performance analysis and optimization including
VLP (Vertical Lift Performance) calculations and IPR (Inflow Performance Relationship) analysis.
"""

import os

from celery import Celery
from flask import Blueprint, current_app, jsonify, request

from gemini_application.productionwell.productionwell_performance import ProductionWellPerformance
from gemini_framework.modules.productionwell.unit import ProductionWellUnit
from gemini_interface.blueprint.celerytasks import productionwellperformance_app_calculate_vlp_ipr

# Create the production well performance application blueprint
app_productionwellperformance = Blueprint("app_productionwellperformance", __name__)

# Initialize Celery for background task processing
celery = Celery(
    "gemini-celery-app",
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379"),
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379"),
)

# Global application instance for production well operations
app_instance = None


@app_productionwellperformance.route("/app/productionwellperformance/load_plant", methods=["POST"])
def load_plant():
    """Load a plant/project into the production well performance application instance."""
    global app_instance

    app_instance = ProductionWellPerformance()

    project_name = request.json["field_name"]
    project_folder_path = current_app.config["GEMINI_PROJECT_FOLDER"]

    app_instance.load_plant(project_folder_path, project_name)

    return "OK"


@app_productionwellperformance.route(
    "/app/productionwellperformance/get_well_list", methods=["POST"]
)
def get_well_list():
    """Get list of production wells for performance analysis."""
    well_unit_list = []
    for unit in app_instance.plant.units:
        if isinstance(unit, ProductionWellUnit):
            well_unit_list.append(unit.name)

    return jsonify(well_unit_list)


@app_productionwellperformance.route("/app/productionwellperformance/calculate", methods=["POST"])
def calculate():
    """Calculate VLP and IPR for production well performance analysis."""
    inputs = {"parameters": request.json["parameters"], "boundary": request.json["boundary"]}

    project_folder_path = app_instance.plant.project_path
    project_name = app_instance.plant.name
    well_name = app_instance.unit.name

    task = productionwellperformance_app_calculate_vlp_ipr.delay(
        project_folder_path, project_name, well_name, inputs
    )

    task_id = str(task.id)

    return task_id


@app_productionwellperformance.route("/app/productionwellperformance/get_results", methods=["POST"])
def get_results():
    """Get results from the background calculation task."""
    task_id = request.json["task_id"]
    task_result = celery.AsyncResult(task_id)

    result = {
        "task_id": task_id,
        "task_status": task_result.status,
        "task_result": task_result.result,
    }
    return result


@app_productionwellperformance.route(
    "/app/productionwellperformance/get_parameters", methods=["POST"]
)
def get_parameters():
    """Get parameters for the selected production well."""
    well_name = request.json["well_name"]
    app_instance.select_unit(well_name)

    res_par = app_instance.unit.from_units[0].parameters
    esp_par = app_instance.unit.to_units[0].parameters
    well_par = app_instance.unit.parameters

    return {"res_par": res_par, "well_par": well_par, "esp_par": esp_par}
