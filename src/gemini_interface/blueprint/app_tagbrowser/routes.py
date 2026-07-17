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

from gemini_application.tagbrowser.datamanager import DataManager
from gemini_framework.database.connector.avevadb_driver import AvevaDriver

# Create the tag browser application blueprint
app_tagbrowser = Blueprint("app_tagbrowser", __name__)

# Global database driver instance
app_instance = DataManager()

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


@app_tagbrowser.route("/app/tagbrowser/get_unitnames", methods=["POST"])
def get_unitnames():
    """Get list of unit names from the project."""
    unitname_list = []
    for unit in app_instance.plant.units:
        unitname_list.append(unit.name)

    return sorted(unitname_list)


@app_tagbrowser.route("/app/tagbrowser/get_tagnames", methods=["POST"])
def get_tagnames():
    """Get list of tag names for a specific unit."""
    unit_name = request.json["unit_name"]
    database = request.json["database"]
    tagnames = []

    if database == "avevadb":
        for db in app_instance.plant.databases["measured"]:
            if isinstance(db.external_db_driver, AvevaDriver):
                tagname, tag_desc = db.external_db_driver.get_tagnames("")
                for ii in range(len(tagname)):
                    tagnames.append(tagname[ii] + " - " + tag_desc[ii])
    if database == "geminidb":
        for unit in app_instance.plant.units:
            if unit.name == unit_name:
                categories = ["measured", "calculated"]
                for category in categories:
                    for tagname in unit.tags[category].keys():
                        tagnames.append(tagname + "." + category)

    return {"tagnames": sorted(tagnames)}


@app_tagbrowser.route("/app/tagbrowser/plot_tagnames", methods=["POST"])
def plot_tagnames():
    """Plot tag data for visualization."""
    unitname = request.json["unitname"]
    database = request.json["database"]

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

    plant_name = app_instance.plant.name

    result = []
    times_utc = []
    times_local = []

    if database == "avevadb":
        tagname_desc = request.json["tagname"]
        index = tagname_desc.find("-")
        tagname = tagname_desc[0 : index - 1]

        for db in app_instance.plant.databases["measured"]:
            if isinstance(db.external_db_driver, AvevaDriver):
                result, times_utc = db.external_db_driver.read_data(
                    tagname, start_time, end_time, timestep
                )

    if database == "geminidb":
        tagname = request.json["tagname"]
        db = app_instance.plant.databases["measured"][0]
        result, times_utc = db.internal_db_driver.read_data(
            plant_name, unitname, tagname, start_time, end_time, timestep
        )

    for time_utc in times_utc:
        time_local = (
            datetime.fromisoformat(time_utc).astimezone(tzobject).strftime("%Y-%m-%d %H:%M:%S")
        )
        times_local.append(time_local)

    return {"x": times_local, "y": result}


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
    current_time = datetime.now().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    status = {}

    categories = ["measured", "calculated"]
    for category in categories:
        for key, value in app_instance.unit.tags[category].items():
            tagname = key + "." + category
            _, last_timestamp = app_instance.plant.database.internal_db_driver.get_last_data(
                app_instance.plant.name, app_instance.unit.name, tagname
            )
            _, first_timestamp = app_instance.plant.database.internal_db_driver.get_first_data(
                app_instance.plant.name, app_instance.unit.name, tagname
            )
            status[tagname] = {
                "first_timestamp": first_timestamp[0] if first_timestamp else None,
                "last_timestamp": last_timestamp[0] if last_timestamp else None,
            }

    return {"status": status, "start_time": start_time, "current_time": current_time}


@app_tagbrowser.route("/app/tagbrowser/save_esp_database", methods=["POST"])
def save_esp_database():
    """Save updated esp database."""
    esp_table = request.json["tabledata"]

    json_str = json.dumps(esp_table, indent=4)
    with open(os.path.join(current_app.static_folder, "database", "pumpdatabase.json"), "w") as f:
        f.write(json_str)

    return "ESP database is saved."
