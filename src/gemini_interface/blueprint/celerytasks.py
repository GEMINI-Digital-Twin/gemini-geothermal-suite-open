"""Celery Tasks Module."""

import os
import sys

sys.path.append(os.path.join(os.getcwd(), "src"))
from celery import Celery

from gemini_application.chatpopup.chatpopup import ChatPopup
from gemini_application.esp.esp import ESPApp
from gemini_application.productionwell.productionwell_performance import ProductionWellPerformance

celery = Celery(
    "gemini-celery-app",
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379"),
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379"),
)


@celery.task(name="productionwellperformance_app_calculate_vlp_ipr")
def productionwellperformance_app_calculate_vlp_ipr(
    project_folder_path, project_name, well_name, inputs
):
    """Calculate VLP and IPR for production well performance analysis."""
    app_instance = ProductionWellPerformance()

    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(well_name)

    app_instance.init_parameters(inputs["parameters"])
    app_instance.set_input(inputs["boundary"])
    app_instance.calculate()
    app_instance.get_solution()

    # preparing output
    inputs = app_instance.get_input()
    outputs = app_instance.get_output()

    if outputs["sol_flow"]:
        results = {
            "bottomhole_pressure_from_reservoir": outputs["pbh_res"].tolist(),
            "bottomhole_pressure_from_well": outputs["pbh_well"].tolist(),
            "intake_pressure": outputs["intake_pressure"].tolist(),
            "discharge_pressure": outputs["discharge_pressure"].tolist(),
            "flow": inputs["flow"].tolist(),
            "reservoir_pressure": inputs["reservoir_pressure"].tolist(),
            "sol_flow": outputs["sol_flow"].tolist(),
            "sol_pbh": outputs["sol_pbh"].tolist(),
            "sol_esp_head": outputs["sol_esp_head"].tolist(),
            "sol_esp_power": outputs["sol_esp_power"].tolist(),
            "sol_esp_eff": outputs["sol_esp_eff"].tolist(),
            "sol_intake_pressure": outputs["sol_intake_pressure"].tolist(),
            "sol_discharge_pressure": outputs["sol_discharge_pressure"].tolist(),
        }
    else:
        results = {
            "bottomhole_pressure_from_reservoir": outputs["pbh_res"].tolist(),
            "bottomhole_pressure_from_well": outputs["pbh_well"].tolist(),
            "intake_pressure": outputs["intake_pressure"].tolist(),
            "discharge_pressure": outputs["discharge_pressure"].tolist(),
            "flow": inputs["flow"].tolist(),
            "reservoir_pressure": inputs["reservoir_pressure"].tolist(),
            "sol_flow": None,
            "sol_pbh": None,
            "sol_esp_head": None,
            "sol_esp_power": None,
            "sol_esp_eff": None,
            "sol_intake_pressure": None,
            "sol_discharge_pressure": None,
        }

    return results


@celery.task(name="wellintegrity_app_process_caliper_logs")
def wellintegrity_app_process_caliper_logs(project_folder_path, project_name, well_name, inputs):
    """Process caliper logs for well integrity monitoring."""
    import json
    import os

    import pandas as pd

    from gemini_application.wims.co2_corrosion import CO2CorrosionApplication

    app_instance = CO2CorrosionApplication()

    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(well_name)

    selected_logs = inputs["selected_logs"]

    # Create processed logs folder
    project_data_folder = os.path.join(project_folder_path, project_name + "/wims_data")
    well_data_folder = os.path.join(project_data_folder, well_name)
    processed_folder = os.path.join(well_data_folder, "processed_logs")

    if not os.path.exists(processed_folder):
        os.makedirs(processed_folder)

    # Process each log individually to avoid DataFrame joining issues
    processed_logs_dict = {}

    for log_name in selected_logs:
        # Set input for single log
        task_inputs = {"selectedLogs": [log_name]}  # Process one log at a time
        app_instance.set_input(task_inputs)

        # Initialize parameters and set input
        app_instance.init_parameters()

        # Get data and process caliper logs
        app_instance.get_data()
        app_instance.process_caliper_logs()

        # Get the processed results for this single log
        outputs = app_instance.get_output()
        processed_logs_data = outputs["processedLogs"]

        if hasattr(processed_logs_data, "__len__") and len(processed_logs_data) > 0:
            item = processed_logs_data[0]  # Should be the first (and only) item

            # Helper function to recursively convert DataFrames to list of
            # dicts and None to empty string
            def make_json_serializable(data):
                if isinstance(data, pd.DataFrame):
                    return make_json_serializable(data.to_dict(orient="records"))
                elif isinstance(data, list):
                    return [make_json_serializable(item) for item in data]
                elif isinstance(data, dict):
                    return {k: make_json_serializable(v) for k, v in data.items()}
                elif data is None:
                    return ""
                else:
                    return data

            # Convert DataFrame to list of records
            if isinstance(item, pd.DataFrame):
                processed_data = make_json_serializable(item)
            else:
                processed_data = make_json_serializable(item)

            processed_logs_dict[log_name] = processed_data

            # Save processed result to file
            processed_file_name = log_name.replace(".las", "_processed.json")
            processed_file_path = os.path.join(processed_folder, processed_file_name)

            with open(processed_file_path, "w") as f:
                json.dump(processed_data, f, indent=2)

        else:
            processed_logs_dict[log_name] = []

    results = {"processed_logs": selected_logs, "results": {"processedLogs": processed_logs_dict}}

    return results


@celery.task(name="esp_app_get_pumphead_data")
def esp_app_get_pumphead_data(project_folder_path, project_name, esp_name, inputs):
    """Calculate pump head curve for ESP analysis."""
    app_instance = ESPApp()

    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(esp_name)

    app_instance.init_parameters()
    app_instance.set_input(inputs["boundary"])

    app_instance.calculate()
    app_instance.get_data()
    app_instance.calculate_pump_head_curve()

    inputs = app_instance.get_input()
    outputs = app_instance.get_output()

    results = {
        "starttime": inputs["start_time"],
        "endtime": inputs["end_time"],
        "realTime_time": outputs["time"].tolist(),
        "realTime_flow": outputs["flow_measured"].tolist(),
        "xValues": [x.tolist() for x in outputs["xValues"]],
        "frequency": outputs["frequency"].tolist(),
        "pump_head": [h for h in outputs["pump_head"]],
        "esp_vlp_head_calculated": outputs["esp_vlp_head_calculated"].tolist(),
        "frequency_measured": outputs["frequency_measured"].tolist(),
        "esp_theoretical_head_calculated": outputs["esp_theoretical_head_calculated"].tolist(),
        "esp_vlp_outlet_pressure_calculated": outputs[
            "esp_vlp_outlet_pressure_calculated"
        ].tolist(),
        "esp_vlp_ipr_inlet_pressure_calculated": outputs[
            "esp_vlp_ipr_inlet_pressure_calculated"
        ].tolist(),
        "inlet_pressure_measured": outputs["inlet_pressure_measured"].tolist(),
        "esp_theoretical_outlet_pressure_calculated": outputs[
            "esp_theoretical_outlet_pressure_calculated"
        ].tolist(),
    }

    return results


@celery.task(name="esp_app_calibrate_pumphead_data")
def esp_app_calibrate_pumphead_data(project_folder_path, project_name, esp_name, inputs):
    """Calibrate ESP pump head data."""
    app_instance = ESPApp()

    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(esp_name)
    app_instance.init_parameters()
    app_instance.set_input(inputs["boundary"])

    app_instance.calibrate_esp_head_simple()

    inputs = app_instance.get_input()
    outputs = app_instance.get_output()
    a, b = map(float, outputs["esp_correction_factor"].split(";"))

    results = {"esp_correction_factor": [a, b]}

    return results


def _clean_for_json(value):
    """Convert NaN/Inf values to None for JSON serialization.

    Needed for ML model predictions which can contain NaN/Inf values.
    """
    import numpy as np

    if isinstance(value, (list, np.ndarray)):
        return [
            None if (isinstance(x, float) and (np.isnan(x) or np.isinf(x))) else x for x in value
        ]
    elif isinstance(value, (float, np.floating)):
        return None if (np.isnan(value) or np.isinf(value)) else value
    return value


@celery.task(name="esp_app_predict_failure")
def esp_app_predict_failure(project_folder_path, project_name, esp_name, inputs):
    """Predict ESP failures using ML model."""
    import numpy as np
    import pandas as pd

    app_instance = ESPApp()
    app_instance.load_plant(project_folder_path, project_name)
    app_instance.select_unit(esp_name)
    app_instance.init_parameters()
    app_instance.set_input(inputs["boundary"])

    prediction_mode = inputs["boundary"].get("prediction_mode", "forward")
    app_instance.predict_failures(prediction_mode=prediction_mode)

    outputs = app_instance.get_output()

    failure_times = outputs["failure_times"]
    timestamps = None
    if failure_times is not None:
        if isinstance(failure_times, pd.DatetimeIndex):
            timestamps = failure_times.strftime("%Y-%m-%dT%H:%M:%SZ").tolist()
        else:
            timestamps = [pd.to_datetime(t).strftime("%Y-%m-%dT%H:%M:%SZ") for t in failure_times]

    predictions = outputs["failure_predictions"]
    if isinstance(predictions, np.ndarray):
        predictions = predictions.tolist()

    results = {
        "prediction_mode": prediction_mode,
        "prediction_timestamps": timestamps,
        "prediction_probabilities": _clean_for_json(predictions),
        "selected_time": inputs["boundary"].get("selected_time"),
    }

    has_sensor_df = hasattr(app_instance, "_sensor_df_for_plot")
    if has_sensor_df and app_instance._sensor_df_for_plot is not None:
        df = app_instance._sensor_df_for_plot
        sensor_timestamps = df.index.strftime("%Y-%m-%dT%H:%M:%SZ").tolist()
        results["prediction_diagnostic_timestamps"] = sensor_timestamps
        results["prediction_feature_timestamps"] = sensor_timestamps
        results["prediction_preprocessed_sensors"] = {
            col: _clean_for_json(df[col].tolist() if col in df.columns else [])
            for col in [
                "Vibration",
                "ESP Motor temperature",
                "wellhead temperature",
                "wellhead pressure",
                "Brine flow rate",
                "intake pressure ESP",
                "discharge pressure ESP",
            ]
        }

    return results


@celery.task(name="rag_generate_response")
def rag_generate_response(parameters, user_message):
    """Generate AI-powered responses using RAG."""
    print("Celery task called, user_message = ", user_message)
    try:
        app_instance = ChatPopup()

        app_instance.init_parameters(parameters)

        # Takes several minutes to process, ~10 minutes
        response = app_instance.process_prompt(user_message)

        return response
    except Exception as e:
        print(f"ERROR: Exception in rag_generate_response: {e}")
        import traceback

        print(traceback.format_exc())
        raise
