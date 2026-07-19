"""
App Report Generator Application Routes.

==============================

This module handles the generation of the report of the plant automatically.
"""

import calendar
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

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

NLOG_SECTION_FILE_PAIRS = (
    ("tagnames_section1A_default.json", "tagnames_section1A.json"),
    ("tagnames_section1B_default.json", "tagnames_section1B.json"),
    ("tagnames_section2_default.json", "tagnames_section2.json"),
)


def ensure_nlog_default_files(project_root: Path, project_name: str) -> Path:
    """Ensure NLOG default section files exist for a project."""
    report_folder = project_root / project_name / "report_generator"
    report_folder.mkdir(parents=True, exist_ok=True)

    template_folder = project_root / "_template" / "report_generator"

    for filename, _ in NLOG_SECTION_FILE_PAIRS:
        target_file = report_folder / filename
        if target_file.exists():
            continue

        source_file = template_folder / filename
        if not source_file.exists():
            raise FileNotFoundError(f"Default template file missing: {source_file}")

        shutil.copy2(source_file, target_file)

    return report_folder


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
    inj_well_crossplot_options = request.json["inj_well_crossplot_options"]

    injection_report = request.json["InjectionReport"]
    production_report = request.json["ProductionReport"]
    p_q_date_crossplot = request.json["P_Q_date_crossplot"]
    p_q_t_crossplot = request.json["P_Q_T_crossplot"]
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

    if p_q_date_crossplot:
        print("CREATING INJECTION CROSS PLOT...")
        tagnames = [
            "injectionwell_wellhead_pressure.measured",
            "injectionwell_flow.measured",
            "datestamp",
        ]

        # Function below creates generic cross-plot without skin lines
        # app_instance.add_cross_plot(inj_wells, tagnames, 'Pressure-Flow-Date')

        inj_well_crossplot_options["starttime"] = StartTime
        inj_well_crossplot_options["endtime"] = EndTime
        inj_well_crossplot_options["plot_type"] = "Pressure-Flow-Date"

        app_instance.add_cross_plot_with_skin_lines(inj_wells, tagnames, inj_well_crossplot_options)

    if p_q_t_crossplot:
        print("CREATING INJECTION CROSS PLOT...")
        tagnames = [
            "injectionwell_wellhead_pressure.measured",
            "injectionwell_flow.measured",
            "injectionwell_wellhead_temperature.measured",
        ]

        # Function below creates generic cross-plot without skin lines
        # app_instance.add_cross_plot(inj_wells, tagnames, 'Pressure-Flow-Temperature')

        inj_well_crossplot_options["starttime"] = StartTime
        inj_well_crossplot_options["endtime"] = EndTime
        inj_well_crossplot_options["plot_type"] = "Pressure-Flow-Date"

        app_instance.add_cross_plot_with_skin_lines(inj_wells, tagnames, inj_well_crossplot_options)

    if esp_q_pow_date_crossplot:
        print("CREATING ESP CROSS PLOT...")
        tagnames = ["esp_flow.measured", "esp_current.measured", "datestamp"]
        app_instance.add_cross_plot(esps, tagnames, "ESP flow-ESP current-Date")

    if esp_freq_i_date_crossplot:
        print("CREATING ESP CROSS PLOT...")
        tagnames = ["esp_frequency.measured", "esp_current.measured", "datestamp"]
        app_instance.add_cross_plot(esps, tagnames, "ESP frequency-ESP current-Date")

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
    project_root = current_app.config.get("GEMINI_PROJECT_FOLDER", "")
    project_path = Path(project_root).expanduser().resolve()
    ensure_nlog_default_files(project_path, ProjectName)

    NlogPeriod = request.json["NlogPeriod"]
    rows_section1A = request.json["rows_section1A"]
    rows_section1B = request.json["rows_section1B"]
    rows_section2 = request.json["rows_section2"]
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

    # Get plant components
    inj_wells = app_instance.get_injection_wells()
    prod_wells = app_instance.get_production_wells()
    esps = app_instance.get_esps()
    hexs = app_instance.get_hexs()
    injection_pumps = app_instance.get_injection_pumps()
    data_section1A = app_instance.calculate_nlog_1A(rows_section1A, prod_wells, esps)
    data_section1B = app_instance.calculate_nlog_1B(
        rows_section1B, inj_wells, hexs, injection_pumps
    )
    data_section2 = app_instance.calculate_nlog_2(rows_section2)

    nlog_object = app_instance.add_nlog_report(
        LicenseHolder,
        NlogPeriod,
        data_section1A,
        data_section1B,
        data_section2,
    )

    return send_file(
        nlog_object,
        mimetype="application/vnd.ms-excel.sheet.macroEnabled.12",
        as_attachment=True,
        download_name=f"{LicenseHolder}_{ProjectName}_{NlogPeriod}_NLOG.xlsm",
    )


@app_reportgenerator.route("/app/reportgenerator/get_nlog_tagnames", methods=["POST"])
def get_nlog_tagnames():
    """Return NLOG tagname settings for all report sections."""
    # Resolve project path and report_generator folder
    ProjectName = request.json["ProjectName"]
    project_root = current_app.config.get("GEMINI_PROJECT_FOLDER", "")
    project_path = Path(project_root).expanduser().resolve()
    folder = ensure_nlog_default_files(project_path, ProjectName)

    # Get plant components (lists of names)
    inj_wells = app_instance.get_injection_wells()
    prod_wells = app_instance.get_production_wells()
    esps = app_instance.get_esps()
    hexs = app_instance.get_hexs()
    booster_pumps = app_instance.get_booster_pumps()
    injection_pumps = app_instance.get_injection_pumps()
    aquifers = app_instance.get_aquifers()
    # Build section dataframes
    section1a_df, section1b_df, section2_df = app_instance.get_nlog_tagnames_df(
        folder=folder,
        inj_wells=inj_wells,
        prod_wells=prod_wells,
        esps=esps,
        hexs=hexs,
        booster_pumps=booster_pumps,
        injection_pumps=injection_pumps,
        aquifers=aquifers,
    )

    # Convert to records for JS
    section1a_dict = section1a_df.to_dict(orient="records")
    section1b_dict = section1b_df.to_dict(orient="records")
    section2_dict = section2_df.to_dict(orient="records")

    return jsonify(
        {
            "section1A": section1a_dict,
            "section1B": section1b_dict,
            "section2": section2_dict,
        }
    )


@app_reportgenerator.route("/app/reportgenerator/get_unit_tagnames", methods=["POST"])
def get_unit_tagnames():
    """Retrieve all available tagnames for a given unit in format 'tagname.category'."""
    data = request.get_json(silent=True) or {}
    unit_name = data.get("unit_name", "").strip()

    if not unit_name or not hasattr(app_instance, "plant"):
        return jsonify({"tagnames": []}), 200

    try:
        unit = None

        # Try direct lookup if units_by_name exists
        if hasattr(app_instance.plant, "units_by_name"):
            unit = app_instance.plant.units_by_name.get(unit_name)

        # Otherwise, search through units list
        if not unit and hasattr(app_instance.plant, "units"):
            for u in app_instance.plant.units:
                if hasattr(u, "name") and u.name == unit_name:
                    unit = u
                    break

        if not unit:
            return jsonify({"tagnames": []}), 200

        # Collect all tagnames in format "tagname.category"
        all_tags = []
        if hasattr(unit, "tags"):
            for category in ["measured", "filtered", "calculated"]:
                category_tags = unit.tags.get(category, {})
                for tag_key in category_tags.keys():
                    all_tags.append(f"{tag_key}.{category}")

        return jsonify({"tagnames": all_tags}), 200
    except Exception as e:
        logger.error(f"Error getting unit tagnames for {unit_name}: {e}")
        return jsonify({"tagnames": []}), 200


@app_reportgenerator.route("/app/reportgenerator/get_all_units", methods=["GET"])
def get_all_units():
    """Return sorted list of all available unit names."""
    if not hasattr(app_instance, "plant"):
        return jsonify({"units": []}), 200

    try:
        units = []
        if hasattr(app_instance.plant, "units"):
            units = [u.name for u in app_instance.plant.units if hasattr(u, "name") and u.name]

        return jsonify({"units": sorted(units)}), 200
    except Exception as e:
        logger.error(f"Error getting all units: {e}")
        return jsonify({"units": []}), 200


@app_reportgenerator.route("/app/reportgenerator/validate_nlog_tagnames", methods=["POST"])
def validate_nlog_tagnames():
    """Validate tagnames against available unit tagnames; return warnings organized by section."""
    data = request.get_json(silent=True) or {}
    rows_section1A = data.get("rows_section1A", [])
    rows_section1B = data.get("rows_section1B", [])
    rows_section2 = data.get("rows_section2", [])

    warnings_section1A = []
    warnings_section1B = []
    warnings_section2 = []

    if not hasattr(app_instance, "plant"):
        return jsonify({"warnings": [], "warnings_by_section": {}}), 200

    try:
        # Helper function to get unit by name
        def get_unit_by_name(unit_name):
            # Try direct lookup if units_by_name exists
            if hasattr(app_instance.plant, "units_by_name"):
                unit = app_instance.plant.units_by_name.get(unit_name)
                if unit:
                    return unit

            # Otherwise, search through units list
            if hasattr(app_instance.plant, "units"):
                for u in app_instance.plant.units:
                    if hasattr(u, "name") and u.name == unit_name:
                        return u

            return None

        # Helper function to validate tagname in format "tagname.category"
        def validate_tagname_format(tagname, unit):
            """Validate tagname in format 'tagname.category' against available tags."""
            if "." not in tagname:
                return False

            parts = tagname.rsplit(".", 1)
            if len(parts) != 2:
                return False

            tag_key, category = parts
            category = category.strip().lower()

            if not hasattr(unit, "tags"):
                return False

            # Check if category exists and tagname key is in that category
            category_tags = unit.tags.get(category, {})
            return tag_key in category_tags

        # Helper function to validate and collect warnings
        def is_row_enabled(row):
            value = row.get("enabled", True)
            if isinstance(value, str):
                return value.strip().lower() not in {"false", "0", "no", "off"}
            return value is not False

        def validate_rows(rows, section_name, warnings_list):
            for row in rows:
                if not is_row_enabled(row):
                    continue

                unit_name = row.get("component_name", "").strip()
                tagname = row.get("tagname", "").strip()
                parameter = row.get("parameter", "")
                param_label = (
                    PARAM_DISPLAY_LABELS.get(parameter, parameter) if parameter else parameter
                )

                # Check unit first (even if tagname is also empty)
                if not unit_name:
                    # Unit is empty
                    warnings_list.append(
                        f"Parameter: {param_label} | Unit: EMPTY | Status: Unit not selected"
                    )
                    continue

                if not tagname:
                    # Tagname is empty
                    warnings_list.append(
                        f"Parameter: {param_label} | Unit: {unit_name} | "
                        "Status: Tagname not selected"
                    )
                    continue

                # Both are present, validate them
                unit = get_unit_by_name(unit_name)
                if not unit:
                    warnings_list.append(
                        f"Parameter: {param_label} | Unit: {unit_name} | "
                        f"Tagname: {tagname} — Unit not found"
                    )
                    continue

                # Validate tagname in format "tagname.category"
                if not validate_tagname_format(tagname, unit):
                    warnings_list.append(
                        f"Parameter: {param_label} | Unit: {unit_name} | "
                        f"Tagname: {tagname} — Tagname not found or incorrect"
                    )

        validate_rows(rows_section1A, "Production well (1A)", warnings_section1A)
        validate_rows(rows_section1B, "Injection well (1B)", warnings_section1B)
        validate_rows(rows_section2, "Plant (2)", warnings_section2)

        # Combine all warnings for backward compatibility
        all_warnings = warnings_section1A + warnings_section1B + warnings_section2

        return (
            jsonify(
                {
                    "warnings": all_warnings,
                    "warnings_by_section": {
                        "production_well": warnings_section1A,
                        "injection_well": warnings_section1B,
                        "plant": warnings_section2,
                    },
                }
            ),
            200,
        )
    except Exception as e:
        logger.error(f"Error validating NLOG tagnames: {e}")
        return jsonify({"warnings": [], "warnings_by_section": {}}), 200


# Mapping for parameter display labels (mirrored from JS for backend validation)
PARAM_DISPLAY_LABELS = {
    "prod_vol_water": "Produced water volume",
    "prod_temp_avg_weighted": "Average produced temperature (weighted)",
    "prod_pres_avg": "Production pressure (average)",
    "prod_pres_min": "Production pressure (minimum)",
    "prod_wh_pres": "Wellhead pressure",
    "prod_oil_vol": "Produced oil volume",
    "prod_gas_vol": "Produced gas volume",
    "prod_condens_vol": "Produced condensate volume",
    "prod_inhibit_vol": "Produced inhibitor volume",
    "inj_vol_water": "Injected water volume",
    "inj_temp_avg_weighted": "Average injection temperature (weighted)",
    "inj_pres_avg": "Injection pressure (average)",
    "inj_pres_max": "Injection pressure (maximum)",
    "inj_inhibit_vol": "Injected inhibitor volume",
    "tot_heat_MJ": "Total heat [MJ]",
    "tot_heat_MJ_inlet_temp": "Heat exchanger inlet temperature",
    "tot_heat_MJ_outlet_temp": "Heat exchanger outlet temperature",
    "tot_heat_MJ_flow": "Heat exchanger flow",
    "tot_oper_hours": "Total operating hours",
    "tot_oper_hours_flow": "Total operating hours (flow-weighted)",
    "tot_el_cons_KWh": "Total electric consumption [kWh]",
    "tot_el_cons_KWh_power": "Electric consumption – cumulative energy meter [kWh]",
    "tot_el_cons_KWh_voltage": "Electric consumption – voltage",
    "tot_el_cons_KWh_current": "Electric consumption – current",
}


def save_section_json(folder: Path, filename: str, rows: list):
    """Save rows to the JSON file in ``folder / filename``.

    Create the file if it does not exist and overwrite existing content.
    """
    file_path = folder / filename
    file_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def delete_nlog_section_json_files(folder: Path, include_defaults: bool = False):
    """Delete saved NLOG section files, optionally including project default files."""
    for default_name, target_name in NLOG_SECTION_FILE_PAIRS:
        for filename in ((default_name, target_name) if include_defaults else (target_name,)):
            file_path = folder / filename
            if file_path.exists():
                file_path.unlink()


@app_reportgenerator.route("/app/reportgenerator/reset_nlog_settings", methods=["POST"])
def reset_nlog_settings():
    """Reset NLOG tagname settings to the default files."""
    data = request.get_json(force=True)

    project_name = data.get("ProjectName")
    if not project_name:
        return jsonify({"status": "error", "message": "Missing ProjectName."}), 400

    project_root = current_app.config.get("GEMINI_PROJECT_FOLDER", "")
    project_path = Path(project_root).expanduser().resolve()
    folder = project_path / project_name / "report_generator"
    folder.mkdir(parents=True, exist_ok=True)

    # Remove project defaults first so fresh template defaults are copied and normalized.
    delete_nlog_section_json_files(folder, include_defaults=True)
    folder = ensure_nlog_default_files(project_path, project_name)

    # Remove saved files so get_nlog_tagnames_df recreates them from the fresh defaults.
    delete_nlog_section_json_files(folder, include_defaults=False)

    inj_wells = app_instance.get_injection_wells()
    prod_wells = app_instance.get_production_wells()
    esps = app_instance.get_esps()
    hexs = app_instance.get_hexs()
    booster_pumps = app_instance.get_booster_pumps()
    injection_pumps = app_instance.get_injection_pumps()
    aquifers = app_instance.get_aquifers()
    app_instance.get_nlog_tagnames_df(
        folder=folder,
        inj_wells=inj_wells,
        prod_wells=prod_wells,
        esps=esps,
        hexs=hexs,
        booster_pumps=booster_pumps,
        injection_pumps=injection_pumps,
        aquifers=aquifers,
    )

    return jsonify({"status": "ok"})


@app_reportgenerator.route("/app/reportgenerator/save_nlog_settings", methods=["POST"])
def save_nlog_settings():
    """Save NLOG tagname settings for all report sections."""
    data = request.get_json(force=True)

    project_name = data.get("ProjectName")
    project_root = current_app.config.get("GEMINI_PROJECT_FOLDER", "")
    project_path = Path(project_root).expanduser().resolve()

    folder = project_path / project_name / "report_generator"
    folder.mkdir(parents=True, exist_ok=True)

    rows_section1A = data.get("rows_section1A", [])
    rows_section1B = data.get("rows_section1B", [])
    rows_section2 = data.get("rows_section2", [])

    # Save the three files
    save_section_json(folder, "tagnames_section1A.json", rows_section1A)
    save_section_json(folder, "tagnames_section1B.json", rows_section1B)
    save_section_json(folder, "tagnames_section2.json", rows_section2)

    return jsonify({"status": "ok"})
