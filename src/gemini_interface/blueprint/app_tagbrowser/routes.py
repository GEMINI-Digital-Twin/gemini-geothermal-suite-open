"""
Tag Browser Application Routes.

===============================

This module provides data tag management and system component browsing functionality including
database connectivity, tag listing, and data visualization.
"""

import json
import os
import tempfile
from datetime import datetime, timezone

import pytz
from celery import Celery
from flask import Blueprint, current_app, jsonify, request

from gemini_application.module.offlinesimulation import OfflineModuleSimulation
from gemini_framework.database.connector.avevadb_driver import AvevaDriver
from gemini_framework.database.connector.influxdb_driver import InfluxdbDriver
from gemini_interface.blueprint.celerytasks import import_raw_data, offline_simulation

# Create the tag browser application blueprint
app_tagbrowser = Blueprint("app_tagbrowser", __name__)

# Global database driver instance
db_driver = None
app_instance = OfflineModuleSimulation()

# Initialize Celery for background task processing
celery = Celery(
    "gemini-celery-app",
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379"),
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379"),
)


# Allowed file extensions for plant configuration uploads
ALLOWED_EXTENSIONS = set(["csv"])


def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ================================================================
# API FUNCTION
# ================================================================
@app_tagbrowser.route("/app/tagbrowser/load_plant", methods=["POST"])
def load_plant():
    """Load plant configuration and setup plant instance."""
    project_name = request.json["field_name"]
    project_folder_path = current_app.config["GEMINI_PROJECT_FOLDER"]

    app_instance.load_plant(project_folder_path, project_name)

    selected_database = app_instance.plant.parameters["database"]["external_database"]

    return selected_database


@app_tagbrowser.route("/app/tagbrowser/connect_database", methods=["POST"])
def connect_database():
    """Connect to the specified database for tag browsing."""
    global db_driver

    project_name = request.json["field_name"]
    database_name = request.json["database_name"]

    project_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], project_name)
    with open(os.path.join(project_folder_path, "plant.conf"), "r") as jsonfile:
        plant_conf = json.load(jsonfile)

    if database_name == "geminidb":
        db_driver = InfluxdbDriver()
        db_conf = {
            "url": os.getenv("INFLUXDB_URL"),
            "org": os.getenv("INFLUXDB_ORG"),
            "username": os.getenv("INFLUXDB_USERNAME"),
            "password": os.getenv("INFLUXDB_PASSWORD"),
            "bucket": os.getenv("INFLUXDB_BUCKET"),
        }
        db_driver.update_parameters(db_conf)

    if database_name == "avevadb":
        db_driver = AvevaDriver()

        db_conf = plant_conf["database"][database_name]
        db_driver.update_parameters(db_conf)

    db_driver.connect()

    return database_name + " is connected"


@app_tagbrowser.route("/app/tagbrowser/get_unitnames", methods=["POST"])
def get_unitnames():
    """Get list of unit names from the project."""
    project_name = request.json["field_name"]
    project_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], project_name)

    component_list = []
    for file in os.listdir(project_folder_path):
        if file.endswith(".param"):
            component_list.append(file[0:-6])

    return sorted(component_list)


@app_tagbrowser.route("/app/tagbrowser/get_tagnames", methods=["POST"])
def get_tagnames():
    """Get list of tag names for a specific unit."""
    project_name = request.json["field_name"]
    unit_name = request.json["unit_name"]

    if isinstance(db_driver, AvevaDriver):
        tagname, tag_desc = db_driver.get_tagnames("")
        tagnames = []
        for ii in range(len(tagname)):
            tagnames.append(tagname[ii] + " - " + tag_desc[ii])
    if isinstance(db_driver, InfluxdbDriver):
        project_folder_path = os.path.join(
            current_app.config["GEMINI_PROJECT_FOLDER"], project_name
        )
        with open(os.path.join(project_folder_path, unit_name + ".param"), "r") as jsonfile:
            component_param = json.load(jsonfile)

        tagnames = []
        for tagname in component_param["tagnames"]["measured"].keys():
            tagnames.append(tagname + ".measured")
        for tagname in component_param["tagnames"]["calculated"].keys():
            tagnames.append(tagname + ".calculated")

    return {"tagnames": sorted(tagnames)}


@app_tagbrowser.route("/app/tagbrowser/plot_tagnames", methods=["POST"])
def plot_tagnames():
    """Plot tag data for visualization."""
    unitname = request.json["unitname"]
    project_name = request.json["field_name"]

    start_time = request.json["starttime"]
    end_time = request.json["endtime"]
    timestep = request.json["timestep"]

    tzobject = pytz.timezone("Europe/Amsterdam")

    start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    start_time = tzobject.localize(start_time)
    start_time = start_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    end_time = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    end_time = tzobject.localize(end_time)
    end_time = end_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if isinstance(db_driver, AvevaDriver):
        tagname_desc = request.json["tagname"]
        index = tagname_desc.find("-")
        tagname = tagname_desc[0 : index - 1]
        result, times_utc = db_driver.read_data(tagname, start_time, end_time, timestep)

    if isinstance(db_driver, InfluxdbDriver):
        tagname = request.json["tagname"]
        result, times_utc = db_driver.read_data(
            project_name, unitname, tagname, start_time, end_time, timestep
        )

    times_local = []
    for time_utc in times_utc:
        time_local = (
            datetime.fromisoformat(time_utc).astimezone(tzobject).strftime("%Y-%m-%d %H:%M:%S")
        )
        times_local.append(time_local)

    return {"x": times_local, "y": result}


@app_tagbrowser.route("/app/tagbrowser/manual_import_raw_data", methods=["GET"])
def manual_import_raw_data():
    """Import raw data from external database."""
    project_folder_path = app_instance.plant.project_path
    project_name = app_instance.plant.name

    task = import_raw_data.delay(project_folder_path, project_name)

    task_id = str(task.id)

    return task_id


@app_tagbrowser.route("/app/tagbrowser/run_offline_sim", methods=["POST"])
def run_offline_sim():
    """Run offline simulation."""
    start_date = request.json["start_date"]
    end_date = request.json["end_date"]

    start_date_iso = change_to_iso(start_date)
    end_date_iso = change_to_iso(end_date)

    project_folder_path = app_instance.plant.project_path
    project_name = app_instance.plant.name

    task = offline_simulation.delay(project_folder_path, project_name, start_date_iso, end_date_iso)

    task_id = str(task.id)

    return task_id


@app_tagbrowser.route("/app/tagbrowser/status_offline_sim", methods=["POST"])
def status_offline_sim():
    """Check the status of a background calculation task."""
    task_id = request.json["task_id"]
    task_result = celery.AsyncResult(task_id)

    result = {
        "task_id": task_id,
        "task_status": task_result.status,
        "task_result": task_result.result,
    }
    return result


def change_to_iso(str_time):
    """Change date string to ISO format."""
    tzobject = pytz.timezone("Europe/Amsterdam")

    iso_time = datetime.strptime(str_time, "%Y-%m-%d %H:%M:%S")
    iso_time = tzobject.localize(iso_time)
    iso_time = iso_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return iso_time


@app_tagbrowser.route("/app/tagbrowser/upload_data_csv", methods=["POST"])
def upload_data_csv():
    """Upload CSV data to the plant instance."""
    file = request.files.get("file")

    if file is None:
        return jsonify("ERROR : No file selected!")
    if file and allowed_file(file.filename):
        tmp_dir = tempfile.TemporaryDirectory()
        filename = os.path.join(tmp_dir.name, "data.csv")
        file.save(filename)

        app_instance.plant.database.external_db_driver.update_parameters({"url": filename})
        app_instance.plant.database.external_db_driver.connect()

        app_instance.plant.database.import_raw_data()

        return jsonify("CSV data is uploaded")
    return jsonify("ERROR : file type should be csv!")


@app_tagbrowser.route("/app/tagbrowser/status_unit_tagnames", methods=["POST"])
def status_unit_tagnames():
    """Get status of tag names for a specific unit."""
    unitname = request.json["unitname"]

    app_instance.select_unit(unitname)

    start_time = change_to_iso(app_instance.plant.parameters["database"]["start_time"])
    status = {}

    categories = ["measured", "calculated"]
    for category in categories:
        for key, value in app_instance.unit.tags[category].items():
            tagname = key + "." + category
            _, timestamp = app_instance.plant.database.internal_db_driver.get_last_data(
                app_instance.plant.name, app_instance.unit.name, tagname
            )
            status[tagname] = timestamp[0] if timestamp else start_time

    current_time = datetime.now().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {"status": status, "start_time": start_time, "current_time": current_time}


@app_tagbrowser.route("/app/tagbrowser/save_esp_database", methods=["POST"])
def save_esp_database():
    """Save updated esp database."""
    esp_table = request.json["tabledata"]

    json_str = json.dumps(esp_table, indent=4)
    with open(os.path.join(current_app.static_folder, "database", "pumpdatabase.json"), "w") as f:
        f.write(json_str)

    return "ESP database is saved."
