"""
App Report Generator Application Routes.

==============================

This module handles the generation of the report of the plant automatically.
"""

import calendar
import logging
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, send_file
from werkzeug.exceptions import BadRequest

from gemini_application.reportgenerator.reportgenerator import ReportGenerator

try:
    # If available in your environment
    from adh_sample_library_preview.SdsError import SdsError
except Exception:
    SdsError = None  # fallback if import path differs

logger = logging.getLogger(__name__)

app_reportgenerator = Blueprint("app_reportgenerator", __name__)


@app_reportgenerator.route("/app/reportgenerator/load_plant", methods=["POST"])
def load_plant():
    """Load the plant object."""
    global app_instance

    # ---- 1) Validate request JSON early ----
    if not request.is_json:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "bad_request",
                    "message": "Expected application/json request body.",
                }
            ),
            400,
        )

    payload = request.get_json(silent=True) or {}
    plant_name = payload.get("field_name")

    if not plant_name or not isinstance(plant_name, str) or not plant_name.strip():
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "bad_request",
                    "message": "Missing or invalid 'field_name' in JSON body.",
                }
            ),
            400,
        )
    # current_app.config["GEMINI_PROJECT_FOLDER"]
    project_folder = current_app.config.get("GEMINI_PROJECT_FOLDER")
    if not project_folder:
        # Misconfiguration on the server
        logger.error("GEMINI_PROJECT_FOLDER is not set in Flask config.")
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "server_misconfigured",
                    "message": "Server configuration missing GEMINI_PROJECT_FOLDER.",
                }
            ),
            500,
        )

    # ---- 2) Run and catch errors ----
    try:
        app_instance = ReportGenerator()
        app_instance.load_plant(project_folder, plant_name.strip())

        return jsonify({"status": "ok", "message": "Plant loaded successfully."}), 200

    # ---- 3) Known/expected errors ----
    except BadRequest as e:
        # If something in Flask parsing/validation throws this
        return jsonify({"status": "error", "error": "bad_request", "message": str(e)}), 400

    except Exception as e:
        # Special-case ADH auth error if it's the one you showed
        msg = str(e)

        if SdsError is not None and isinstance(e, SdsError):
            # Don't leak sensitive config; return a helpful, safe message
            logger.exception("ADH authentication/SDSError while loading plant.")
            return (
                jsonify(
                    {
                        "status": "error",
                        "error": "external_auth_failed",
                        "message": "Failed to authenticate to ADH."
                        " Check client id/secret/tenant and token endpoint configuration.",
                        "details": msg,  # optional: remove if you don't want raw upstream text
                    }
                ),
                502,
            )

        # Generic fallback
        logger.exception("Unhandled exception in load_plant().")
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "internal_error",
                    "message": "An unexpected error occurred while loading the plant.",
                    "details": msg,  # optional; remove in production
                }
            ),
            500,
        )


@app_reportgenerator.route("/app/reportgenerator/generate_report", methods=["POST"])
def generate_report():
    """Generate the report pdf object."""
    # Get inputs
    StartTime = request.json["StartTime"]
    EndTime = request.json["EndTime"]
    AuthorName = request.json["AuthorName"]
    ProjectName = request.json["ProjectName"]

    esp_plots_options = request.json["esp_plots_options"]

    injection_report = request.json["InjectionReport"]
    production_report = request.json["ProductionReport"]
    esp_q_pow_date_crossplot = request.json["ESP_Q_Pow_date_crossplot"]
    esp_freq_i_date_crossplot = request.json["ESP_freq_I_date_crossplot"]

    # User comments
    inj_report_comments = request.json["inj_report_comments"]
    prod_report_comments = request.json["prod_report_comments"]
    esp_report_comments = request.json["esp_report_comments"]
    # Initialize parameters
    parameters = dict()
    parameters["start_time"] = StartTime
    parameters["end_time"] = EndTime
    parameters["timestep"] = 3600
    parameters["author_name"] = AuthorName
    parameters["project_name"] = ProjectName
    parameters["project_path"] = current_app.config.get("GEMINI_PROJECT_FOLDER")

    # Convert to datetime objects
    start_dt = datetime.strptime(StartTime, "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.strptime(EndTime, "%Y-%m-%d %H:%M:%S")
    parameters["number_days"] = (end_dt - start_dt).days

    # Initialize app
    app_instance.init_parameters(**parameters)
    app_instance.initialize_pdf_object()

    # Get plant components
    inj_wells = app_instance.get_injection_wells()
    print(inj_wells)
    prod_wells = app_instance.get_production_wells()
    print(prod_wells)
    esps = app_instance.get_esps()
    print(esps)

    # ADD TITLE PAGE
    app_instance.add_title_page()
    print("CREATING STATS REPORT...")
    # CREATE TABLE WITH STATS
    app_instance.add_stats_table(inj_wells, prod_wells)
    # CREATE MAX VALUES PLOTS
    app_instance.add_stats_plot(inj_wells, prod_wells)

    if injection_report:
        print("CREATING INJECTION REPORT...")
        tagnames = [
            "injectionwell_injectivity_index.calculated",
            "injectionwell_wellhead_pressure.measured",
            "injectionwell_flow.measured",
            "injectionwell_wellhead_temperature.measured",
            "injectionwell_annulus_pressure.measured",
        ]
        app_instance.add_injection_report(inj_wells, tagnames)

        user_text_inj_report_title = "Injection report: User comments"
        user_text_inj_report = inj_report_comments
        app_instance.add_text_section_page(user_text_inj_report, user_text_inj_report_title)

    if production_report:
        print("CREATING PRODUCTION REPORT...")
        tagnames = [
            "productionwell_annulus_a_pressure.measured",
            "productionwell_annulus_b_pressure.measured",
            "productionwell_wellhead_pressure.measured",
            "productionwell_flow.measured",
            "productionwell_wellhead_temperature.measured",
        ]
        app_instance.add_production_report(prod_wells, tagnames)

        user_text_prod_report_title = "Production report: User comments"
        user_text_prod_report = prod_report_comments
        app_instance.add_text_section_page(user_text_prod_report, user_text_prod_report_title)

    # ESP plots
    print("CREATING ESP REPORT...")
    option_to_tagname_dict = {
        "esp_flow": "esp_flow.measured",
        "esp_frequency": "esp_frequency.measured",
        "esp_amperage": "esp_current.measured",
        "esp_voltage": "esp_voltage.measured",
        "esp_power_consumption": "esp_power_consumption.measured",
        "esp_motor_temperature": "esp_motor_temperature.measured",
        "esp_inlet_temperature": "esp_inlet_temperature.measured",
        "esp_outlet_temperature": "esp_outlet_temperature.measured",
        "esp_vibration_x": "esp_vibration_x.measured",
        "esp_vibration_y": "esp_vibration_y.measured",
        "esp_intake_pressure": "esp_inlet_pressure.measured",
        "esp_discharge_pressure": "esp_outlet_pressure.measured",
    }
    for option in esp_plots_options.keys():
        tagname = option_to_tagname_dict[option]
        esp_plots_options[option]["tagname"] = tagname

    app_instance.add_esp_report(esps, esp_plots_options)

    if esp_q_pow_date_crossplot:
        print("CREATING ESP CROSS PLOT...")
        tagnames = ["esp_flow.measured", "esp_current.measured", "datestamp"]
        app_instance.add_cross_plot(esps, tagnames, "ESP flow-ESP current-Date with skin lines")

    if esp_freq_i_date_crossplot:
        print("CREATING ESP CROSS PLOT...")
        tagnames = ["esp_frequency.measured", "esp_current.measured", "datestamp"]
        app_instance.add_cross_plot(
            esps, tagnames, "ESP frequency-ESP current-Date with skin lines"
        )

    user_text_esp_report_title = "ESP report: User comments"
    user_text_esp_report = esp_report_comments
    app_instance.add_text_section_page(user_text_esp_report, user_text_esp_report_title)

    # Create pdf
    app_instance.pdf_object.close()
    app_instance.pdf_buffer.seek(0)

    return send_file(
        app_instance.pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="report.pdf",
    )


@app_reportgenerator.route("/app/reportgenerator/generate_nlog_report", methods=["POST"])
def generate_nlog_report():
    """Generate the NLOG report excel object."""
    ProjectName = request.json["ProjectName"]
    NlogPeriod = request.json["NlogPeriod"]
    year, month = map(int, NlogPeriod.split("-"))

    # Start: last hour of the previous month (23:00:00)
    if month == 1:
        prev_year = year - 1
        prev_month = 12
    else:
        prev_year = year
        prev_month = month - 1

    last_day_prev_month = calendar.monthrange(prev_year, prev_month)[1]
    start_dt = datetime(prev_year, prev_month, last_day_prev_month, 23, 0, 0)

    # End: last hour of the given month (23:00:00)
    last_day_curr_month = calendar.monthrange(year, month)[1]
    end_dt = datetime(year, month, last_day_curr_month, 23, 0, 0)

    StartTime = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    EndTime = end_dt.strftime("%Y-%m-%d %H:%M:%S")

    LicenseHolder = request.json["LicenseHolder"]

    # Initialize parameters
    parameters = dict()
    parameters["start_time"] = StartTime
    parameters["end_time"] = EndTime
    parameters["timestep"] = 3600
    parameters["author_name"] = LicenseHolder
    parameters["project_name"] = ProjectName
    parameters["project_path"] = current_app.config.get("GEMINI_PROJECT_FOLDER")

    # Initialize app
    app_instance.init_parameters(**parameters)

    print("CREATING NLOG REPORT")
    prod_table_tagnames = {
        "water_prod_volume": {"tagname": "esp_flow.measured", "unit": "esp"},
        "water_prod_temp": {"tagname": "unknown", "unit": "unknown"},
        "prod_pressure_avg": {"tagname": "esp_inlet_pressure.measured", "unit": "esp"},
        "prod_pressure_min": {"tagname": "previous_tagname", "unit": "esp"},
        "well_pressure_avg": {
            "tagname": "productionwell_wellhead_pressure.measured",
            "unit": "production_well",
        },
        "aquifer_oil_vol_total": {"tagname": "unknown", "unit": "unknown"},
        "aquifer_gas_vol_total": {"tagname": "unknown", "unit": "unknown"},
        "aquifer_cond_vol_total": {"tagname": "unknown", "unit": "unknown"},
        "prod_inhibit_total": {"tagname": "unknown", "unit": "unknown"},
    }

    inj_table_tagnames = {
        "status": {"tagname": "unknown", "unit": "unknown"},
        "type": {"tagname": "unknown", "unit": "unknown"},
        "water_inj_volume": {
            "tagname": "injectionwell_flow.measured",
            "unit": "injection_well",
        },
        "inj_temperature_avg": {
            "tagname": "injectionwell_wellhead_temperature.measured",
            "unit": "injection_well",
        },
        "inj_pump_pressure_avg": {
            "tagname": "injectionpump_outlet_pressure.measured",
            "unit": "injection_pump",
        },
        "inj_pump_pressure_max": {"tagname": "previous_tagname", "unit": "unknown"},
        "inj_inhibit_total": {"tagname": "unknown", "unit": "unknown"},
    }

    hex_tagnames = {
        "status": {"tagname": "unknown", "unit": "unknown"},
        "type": {"tagname": "unknown", "unit": "unknown"},
        "hex_primary_flow": {
            "tagname": "hex_primary_flow.measured",
            "unit": "heat_exchanger",
        },
        "hex_primary_inlet_temperature": {
            "tagname": "hex_primary_inlet_temperature.measured",
            "unit": "heat_exchanger",
        },
        "hex_secondary_flow": {
            "tagname": "hex_secondary_flow.measured",
            "unit": "heat_exchanger",
        },
        "hex_secondary_inlet_temperature": {
            "tagname": "hex_secondary_inlet_temperature.measured",
            "unit": "heat_exchanger",
        },
        "hex_secondary_outlet_temperature": {
            "tagname": "hex_secondary_outlet_temperature.measured",
            "unit": "heat_exchanger",
        },
    }

    esp_tagnames = {
        "status": {"tagname": "unknown", "unit": "unknown"},
        "type": {"tagname": "unknown", "unit": "unknown"},
        "esp_current": {
            "tagname": "esp_current.measured",
            "unit": "esp",
        },
        "esp_voltage": {
            "tagname": "esp_voltage.measured",
            "unit": "esp",
        },
    }

    # Get plant components
    inj_wells = app_instance.get_injection_wells()
    prod_wells = app_instance.get_production_wells()
    esps = app_instance.get_esps()
    hexs = app_instance.get_hexs()

    nlog_object = app_instance.add_nlog_report(
        LicenseHolder,
        NlogPeriod,
        inj_wells,
        prod_wells,
        esps,
        hexs,
        prod_table_tagnames,
        inj_table_tagnames,
        esp_tagnames,
        hex_tagnames,
    )

    return send_file(
        nlog_object,
        mimetype="application/vnd.ms-excel.sheet.macroEnabled.12",
        as_attachment=True,
        download_name=f"{LicenseHolder}_{ProjectName}_{NlogPeriod}_NLOG.xlsm",
    )
