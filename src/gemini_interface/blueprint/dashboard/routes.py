"""
Dashboard Application Routes.

=============================

This module provides dashboard functionality for plant parameter visualization and
system overview including configuration management and monitoring capabilities.
"""

import json
import os

from flask import Blueprint, current_app, request

# Create the dashboard blueprint
dashboard = Blueprint("dashboard", __name__)


# ================================================================
# API FUNCTION
# ================================================================


@dashboard.route("/dashboard/get_url", methods=["POST"])
def get_plant_parameters():
    """Get plant parameters and configuration for dashboard display."""
    project_name = request.json["field_name"]
    project_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], project_name)

    with open(os.path.join(project_folder_path, "plant.conf"), "r") as jsonfile:
        plant_conf = json.load(jsonfile)

    url = plant_conf["dashboard"]["url"]

    return url
