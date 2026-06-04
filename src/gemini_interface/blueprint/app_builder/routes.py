"""
App Builder Application Routes.

==============================

This module handles application diagram building and configuration management including diagram
saving/loading and template component management.
"""

import json
import os
import tempfile

import pandas as pd
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user
from git import Repo

# Create the app builder blueprint
app_builder = Blueprint("app_builder", __name__)

ALLOWED_EXTENSIONS = set(["csv"])


def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ================================================================
# API FUNCTION
# ================================================================


@app_builder.route("/app/builder/save_diagram", methods=["POST"])
def save_diagram():
    """Save the application diagram to the project."""
    diagram = request.json["diagram"]
    project_name = request.json["field_name"]
    commit_message = request.json["commit_message"]

    project_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], project_name)

    diagram_json = json.dumps(diagram, indent=4, sort_keys=True)
    with open(os.path.join(project_folder_path, "diagram.json"), "w") as jsonfile:
        jsonfile.write(diagram_json)

    for file in os.listdir(project_folder_path):
        if file.endswith(".param"):
            os.remove(os.path.join(project_folder_path, file))

    for component in diagram["cells"]:
        if (component["type"] == "devs.Link") or (component["type"] == "standard.Circle"):
            continue

        component_name = component["properties"]["name"]
        with open(os.path.join(project_folder_path, component_name + ".param"), "w") as jsonfile:
            jsonfile.write(json.dumps(component["properties"], indent=4, sort_keys=True))

    repo = Repo.init(project_folder_path)
    repo.config_writer().set_value("user", "name", current_user.name).release()
    repo.config_writer().set_value("user", "email", current_user.email).release()

    for file in repo.untracked_files:
        repo.index.add(os.path.join(project_folder_path, file))

    diffs = repo.index.diff(None)
    for diff in diffs:
        if not diff.change_type == "D":
            repo.index.add(diff.a_path)
        else:
            repo.index.remove(diff.a_path)

    repo.index.commit(commit_message)

    return jsonify("diagram is saved")


@app_builder.route("/app/builder/load_diagram", methods=["POST"])
def load_diagram():
    """Load the application diagram from the project."""
    project_name = request.json["field_name"]
    project_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], project_name)

    # SYNC DIAGRAM
    diagram = dict()
    if os.path.exists(os.path.join(project_folder_path, "diagram.json")):
        with open(os.path.join(project_folder_path, "diagram.json"), "r") as jsonfile:
            diagram = json.load(jsonfile)

    for component in diagram["cells"]:
        if (component["type"] == "devs.Link") or (component["type"] == "standard.Circle"):
            continue

        component_name = component["properties"]["name"]

        with open(os.path.join(project_folder_path, component_name + ".param"), "r") as jsonfile:
            component_content = json.load(jsonfile)

        component["properties"] = component_content

    # Update the diagram.json with the given component names
    diagram_json = json.dumps(diagram, indent=4, sort_keys=True)
    with open(os.path.join(project_folder_path, "diagram.json"), "w") as jsonfile:
        jsonfile.write(diagram_json)

    return jsonify(diagram)


@app_builder.route("/app/builder/upload_well_trajectory", methods=["POST"])
def upload_well_trajectory():
    """Upload and process well trajectory CSV file."""
    file = request.files.get("file")

    if file is None:
        return jsonify("ERROR : No file selected!")
    if file and allowed_file(file.filename):
        tmp_dir = tempfile.TemporaryDirectory()
        filename = os.path.join(tmp_dir.name, "welltrajectory.csv")
        file.save(filename)

        df = pd.read_csv(filename, sep=";")

        table = []
        for ii in range(0, len(df)):
            rowdata = {
                "DT_RowId": ii,
                "TVD": float(df["TVD"][ii]),
                "MD": float(df["MD"][ii]),
                "ID": df["ID"][ii],
                "material": df["material"][ii],
                "roughness": df["roughness"][ii],
            }

            table.append(rowdata)

        return {"data": table}


@app_builder.route("/app/builder/upload_well_tally", methods=["POST"])
def upload_well_tally():
    """Upload and process well tally CSV/TXT file."""
    file = request.files.get("file")

    if file is None:
        return jsonify("ERROR : No file selected!")
    if file and allowed_file(file.filename):
        tmp_dir = tempfile.TemporaryDirectory()
        ext = file.filename.rsplit(".", 1)[1].lower() if "." in file.filename else "csv"
        save_path = os.path.join(tmp_dir.name, f"welltally.{ext}")
        file.save(save_path)

        try:
            df = pd.read_csv(save_path, sep=None, engine="python")
        except Exception:
            df = pd.read_csv(save_path, sep=";")

        # Normalize column names (strip whitespace, handle case)
        df.columns = df.columns.str.strip()

        # Map common tally column names
        col_map = {
            "TopMD": "TopMD",
            "Top MD": "TopMD",
            "BottomMD": "BottomMD",
            "Bottom MD": "BottomMD",
            "TopTVD": "TopTVD",
            "Top TVD": "TopTVD",
            "BottomTVD": "BottomTVD",
            "Bottom TVD": "BottomTVD",
            "ID": "ID",
            "Roughness": "Roughness",
            "OD": "OD",
        }
        rename = {}
        for c in df.columns:
            if c in col_map:
                rename[c] = col_map[c]
        df = df.rename(columns=rename)

        required = ["TopMD", "BottomMD", "TopTVD", "BottomTVD", "ID", "Roughness"]
        for r in required:
            if r not in df.columns:
                return (
                    jsonify(
                        {"error": f"Missing required column: {r}. Expected columns: {required}"}
                    ),
                    400,
                )

        table = []
        for ii in range(len(df)):
            rowdata = {
                "DT_RowId": ii,
                "TopMD": float(df["TopMD"].iloc[ii]),
                "BottomMD": float(df["BottomMD"].iloc[ii]),
                "TopTVD": float(df["TopTVD"].iloc[ii]),
                "BottomTVD": float(df["BottomTVD"].iloc[ii]),
                "ID": float(df["ID"].iloc[ii]),
                "Roughness": float(df["Roughness"].iloc[ii]),
            }
            if "OD" in df.columns:
                rowdata["OD"] = float(df["OD"].iloc[ii])
            else:
                rowdata["OD"] = None
            table.append(rowdata)

        return {"data": table}

    return jsonify("ERROR : Only .csv files are allowed for well tally!"), 400


@app_builder.route("/app/builder/get_template_component", methods=["POST"])
def get_template_component():
    """Get template component properties for the app builder."""
    component = request.json["component"]
    template_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], "_template")

    component_file = "template_" + component + ".param"

    with open(os.path.join(template_folder_path, component_file), "r") as jsonfile:
        properties = json.load(jsonfile)

    return properties


@app_builder.route("/app/builder/log_status", methods=["POST"])
def log_status():
    """Get log status for the project."""
    project_name = request.json["field_name"]
    project_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], project_name)

    repo = Repo.init(project_folder_path)

    ii = 0
    table = []
    for commit in repo.iter_commits():
        rowdata = {
            "DT_RowId": ii,
            "date_modified": commit.committed_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "message": commit.message,
            "author": commit.author.name,
        }

        table.append(rowdata)
        ii = ii + 1

    print(table)
    return {"data": table}


@app_builder.route("/app/builder/load_template", methods=["GET"])
def load_template():
    """Load the application diagram from the template."""
    project_folder_path = os.path.join(
        current_app.config["GEMINI_PROJECT_FOLDER"], "geothermal_example"
    )

    diagram = dict()
    if os.path.exists(os.path.join(project_folder_path, "diagram.json")):
        with open(os.path.join(project_folder_path, "diagram.json"), "r") as jsonfile:
            diagram = json.load(jsonfile)

    return jsonify(diagram)
