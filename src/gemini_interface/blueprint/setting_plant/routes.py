"""
Plant Settings Routes.

=====================

This module handles plant configuration management and parameter handling
functionality including plant loading, parameter file processing, and configuration management.
"""

import json
import os

from flask import Blueprint, current_app, jsonify, request

from gemini_framework.framework.boot_plant import setup
from gemini_framework.framework.plant import Plant

# Create the plant settings blueprint
setting_plant = Blueprint("setting_plant", __name__)

plant = Plant()


# ================================================================
# API FUNCTION
# ================================================================
@setting_plant.route("/setting/plant/load_plant", methods=["POST"])
def load_plant():
    """Load plant configuration and setup plant instance."""
    global plant

    project_name = request.json["field_name"]
    plant = setup(current_app.config["GEMINI_PROJECT_FOLDER"], project_name)

    return "plant is loaded"


@setting_plant.route("/setting/plant/get_plant_parameters", methods=["GET"])
def get_plant_parameters():
    """Get plant parameters from the loaded plant instance."""
    return jsonify(plant.parameters)


@setting_plant.route("/setting/plant/save_plant_parameters", methods=["POST"])
def save_plant_parameters():
    """Save updated plant parameters for the current plant instance."""
    project_folder_path = os.path.join(plant.project_path, plant.name)

    plant_conf = request.json["parameters"]

    plant.update_parameters(plant_conf)

    with open(os.path.join(project_folder_path, "plant.conf"), "w") as jsonfile:
        jsonfile.write(json.dumps(plant_conf, indent=4, sort_keys=True))

    return "new parameters are saved"
