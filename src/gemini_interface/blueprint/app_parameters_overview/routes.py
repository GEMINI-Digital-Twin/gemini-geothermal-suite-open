"""
Parameters Overview Application Routes.

======================================

This module provides system parameter visualization and management functionality including
component listing, parameter retrieval, and system overview.
"""

import json
import os

from flask import Blueprint, current_app, jsonify, request

# Create the parameters overview application blueprint
app_parameters_overview = Blueprint("app_parameters_overview", __name__)


@app_parameters_overview.route("/app/parameters_overview/get_component_list", methods=["POST"])
def get_component_list():
    """Get list of components from the project."""
    data = request.get_json()
    project_name = data.get("field_name")
    project_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], project_name)

    component_list = []
    for file in os.listdir(project_folder_path):
        if file.endswith(".param"):
            component_list.append(file[0:-6])

    return jsonify(component_list)


@app_parameters_overview.route(
    "/app/parameters_overview/get_component_parameters", methods=["POST"]
)
def get_component_parameters():
    """Get parameters for a specific component."""
    # Get variable names
    project_name = request.json["field_name"]
    component_name = request.json["component_name"]

    project_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], project_name)

    # Load the component .param file
    with open(os.path.join(project_folder_path, f"{component_name}.param"), "r") as jsonfile:
        component_content = json.load(jsonfile)

    # Create a dictionary of parameters for the given component name
    parameters = {}
    for parameter in component_content["parameters"]["property"].keys():
        parameters[parameter] = component_content["parameters"]["property"][parameter]

    # Create a dictionary of tagnames for the given component name
    tagnames = {}
    if len(component_content["tagnames"]["calculated"]) > 0:
        for tagname in component_content["tagnames"]["calculated"].keys():
            if len(component_content["tagnames"]["calculated"][tagname]) > 0:
                tagnames[tagname] = {
                    "value": component_content["tagnames"]["calculated"][tagname],
                    "type": "calculated",
                }
            else:
                tagnames[tagname] = {"value": [""], "type": "calculated"}

    if len(component_content["tagnames"]["measured"]) > 0:
        for tagname in component_content["tagnames"]["measured"].keys():
            if len(component_content["tagnames"]["measured"][tagname]) > 0:
                tagnames[tagname] = {
                    "value": component_content["tagnames"]["measured"][tagname],
                    "type": "measured",
                }
            else:
                tagnames[tagname] = {"value": [""], "type": "measured"}

    parameters_timestamps = component_content["parameters"]["timestamps"]
    tagnames_timestamps = component_content["tagnames"]["timestamps"]

    return jsonify(
        {
            "parameters": parameters,
            "tagnames": tagnames,
            "parameters_timestamps": parameters_timestamps,
            "tagnames_timestamps": tagnames_timestamps,
        }
    )


def convert_trajectory_table(input_table):
    """Convert column-wise to row-wise table."""
    keys_list = list(input_table.keys())
    num_steps = int(len(input_table[keys_list[0]]))
    output_table = []

    for ii in range(num_steps):
        new_row = dict()
        for key in keys_list:
            new_row[key] = input_table[key][ii]
        output_table.append(new_row)

    return output_table


@app_parameters_overview.route(
    "/app/parameters_overview/update_parameters_tagnames", methods=["POST"]
)
def update_parameters_tagnames():
    """Update parameters and tagnames for a specific component."""
    project_name = request.json["field_name"]
    component_name = request.json["component_name"]
    updated_parameters = request.json["updated_parameters"]
    updated_injectionwell = request.json["updated_injectionwell"]
    updated_productionwell = request.json["updated_productionwell"]
    updated_tagnames = request.json["updated_tagnames"]

    # Load diagram json file
    project_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], project_name)
    with open(os.path.join(project_folder_path, f"{component_name}.param"), "r") as jsonfile:
        component_content = json.load(jsonfile)

    # Update tag values
    for tagname in updated_tagnames.keys():
        value = updated_tagnames[tagname][0]
        type = updated_tagnames[tagname][1]
        if value is not None:
            component_content["tagnames"][type][tagname] = value

    # Update parameter values
    for parameter in updated_parameters.keys():
        value = updated_parameters[parameter]
        component_content["parameters"][parameter] = value

    # If flag is true, update production well trajectory table
    if updated_productionwell["flag"]:
        trajectory_table_input = updated_productionwell["trajectory_table"]

        trajectory_table_output = convert_trajectory_table(trajectory_table_input)

        component_content["parameters"]["productionwell_trajectory_table"] = trajectory_table_output

    # If flag is true, update injection well trajectory table
    if updated_injectionwell["flag"]:
        trajectory_table_input = updated_injectionwell["trajectory_table"]

        trajectory_table_output = convert_trajectory_table(trajectory_table_input)

        component_content["parameters"]["injectionwell_trajectory_table"] = trajectory_table_output

    # Update the component .param with the updated parameter and tagname values
    component_content_json = json.dumps(component_content, indent=4, sort_keys=True)
    with open(os.path.join(project_folder_path, f"{component_name}.param"), "w") as jsonfile:
        jsonfile.write(component_content_json)

    return "Parameters and Tagnames updated succesfully"
