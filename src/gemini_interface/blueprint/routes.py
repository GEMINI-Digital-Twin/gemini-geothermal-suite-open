"""
Main Application Routes.

=======================

This module contains the main Flask blueprint for the Gemini application.
It handles the primary navigation routes, template rendering, and serves
as the central hub for the web interface.
"""

import os

from flask import Blueprint, current_app, render_template, send_from_directory
from flask_login import current_user, login_required

# Create the main blueprint instance
main = Blueprint("main", __name__)


@main.route("/")
@login_required
def index():
    """Navigate to the main application dashboard."""
    return render_template("index.html")


@main.route("/app/diagram")
@login_required
def app_diagram():
    """Navigate to the application diagram builder interface."""
    return render_template("app_diagram.html")


@main.route("/app/esp")
@login_required
def app_esp():
    """ESP application interface."""
    return render_template("app_esp.html")


@main.route("/app/tagbrowser")
@login_required
def app_tagbrowser():
    """Tag browser application interface."""
    return render_template("app_tagbrowser.html")


@main.route("/app/productionwellperformance")
@login_required
def app_productionwellperformance():
    """Production well performance application interface."""
    return render_template("app_productionwell_performance.html")


@main.route("/app/injectionwellmonitoring")
@login_required
def app_injectionwellmonitoring():
    """Injection well monitoring application interface."""
    return render_template("app_injectionwell_monitoring.html")


@main.route("/app/well_schematics")
@login_required
def app_well_schematics():
    """Well schematics application interface."""
    return render_template("app_well_schematics.html")


@main.route("/app/wellintegrity_monitoring")
@login_required
def app_wellintegrity_monitoring():
    """Well integrity monitoring application interface."""
    return render_template("app_wellintegrity_monitoring.html")


@main.route("/app/parameters_overview")
@login_required
def app_parameters_overview():
    """Parameters overview application interface."""
    return render_template("app_parameters_overview.html")


@main.route("/app/reportgenerator")
@login_required
def app_reportgenerator():
    """Report generator application interface."""
    return render_template("app_report_generator.html")


# ================================================================


@main.route("/profile")
@login_required
def profile():
    """User profile page."""
    return render_template("profile.html", name=current_user.name)


# ===================================================================


@main.route("/documentation")
def documentation():
    """Documentation page."""
    return render_template("documentation.html")


@main.route("/documentation/sphinx/", defaults={"filename": "index.html"})
@main.route("/documentation/sphinx/<path:filename>")
def docshtml(filename):
    """Serve documentation files."""
    return send_from_directory(
        os.path.join(current_app.config["GEMINI_DOCUMENTATION_FOLDER"], "build", "html"), filename
    )


@main.route("/report")
@login_required
def report():
    """Report management interface."""
    return render_template("report.html")


@main.route("/app/timeseriesviewer")
@login_required
def timeseriesviewer():
    """Time series viewer application interface."""
    return render_template("timeseries.html")


# ====================================================================
@main.route("/setting/plant")
@login_required
def setting_plant():
    """Plant configuration interface."""
    return render_template("setting_plant.html")
