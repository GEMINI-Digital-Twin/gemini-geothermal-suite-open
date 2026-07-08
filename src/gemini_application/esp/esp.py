"""ESP application for pump performance analysis and pump curve generation."""

from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import pytz
from matplotlib import pyplot as plt
from sklearn.preprocessing import StandardScaler

from gemini_application.application_abstract import ApplicationAbstract
from gemini_model.pump.esp import ESP

tzobject = pytz.timezone("Europe/Amsterdam")


class ESPApp(ApplicationAbstract):
    """Class for application ESP calculation."""

    def __init__(self):
        """Initialize ESP application."""
        super().__init__()

        self.ESP = ESP()

    def init_parameters(self):
        """Initialize model parameters."""
        esp_unit = self.unit

        esp_param = dict()
        esp_param["no_stages"] = esp_unit.parameters["property"]["esp_no_stage"][0]
        esp_param["pump_name"] = esp_unit.parameters["property"]["esp_type"][0]
        esp_param["head_coeff"] = np.asarray(
            esp_unit.parameters["property"]["esp_head_coeff"][0].split(";"), dtype=np.float32
        )
        esp_param["power_coeff"] = np.asarray(
            esp_unit.parameters["property"]["esp_power_coeff"][0].split(";"), dtype=np.float32
        )
        esp_param["min_flow"] = esp_unit.parameters["property"]["esp_min_flow"][0]
        esp_param["max_flow"] = esp_unit.parameters["property"]["esp_max_flow"][0]
        esp_param["bep_flow"] = esp_unit.parameters["property"]["esp_bep_flow"][0]

        self.ESP.update_parameters(esp_param)

        self.outputs["esp_correction_factor"] = esp_unit.parameters["property"][
            "esp_correction_factor"
        ][0]

    def _read_series(self, tagname):
        """Read a measured/calculated series from the internal database."""
        start_time = datetime.strptime(self.inputs["start_time"], "%Y-%m-%d %H:%M:%S")
        start_time = (
            tzobject.localize(start_time).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        )

        end_time = datetime.strptime(self.inputs["end_time"], "%Y-%m-%d %H:%M:%S")
        end_time = (
            tzobject.localize(end_time).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        )

        timestep = 3600
        result, time = self.plant.database.read_internal_database(
            self.unit.plant.name,
            self.unit.name,
            tagname,
            start_time,
            end_time,
            timestep,
        )
        return np.array(result), np.array(time)

    def get_data(self):
        """Get ESP data."""
        self.outputs["flow_measured"], self.outputs["time"] = self._read_series("esp_flow.measured")
        self.outputs["frequency_measured"], _ = self._read_series("esp_frequency.measured")
        self.outputs["inlet_pressure_measured"], _ = self._read_series(
            "esp_inlet_pressure.measured"
        )
        self.outputs["esp_vlp_head_calculated"], _ = self._read_series("esp_vlp_head.calculated")
        self.outputs["esp_theoretical_head_calculated"], _ = self._read_series(
            "esp_theoretical_head.calculated"
        )
        self.outputs["esp_vlp_outlet_pressure_calculated"], _ = self._read_series(
            "esp_vlp_outlet_pressure.calculated"
        )
        self.outputs["esp_vlp_ipr_inlet_pressure_calculated"], _ = self._read_series(
            "esp_vlp_ipr_inlet_pressure.calculated"
        )
        self.outputs["esp_theoretical_outlet_pressure_calculated"], _ = self._read_series(
            "esp_theoretical_outlet_pressure.calculated"
        )

    def calibrate_esp_head_simple(self):
        """Calibrate ESP head using simple method."""
        start_time = datetime.strptime(self.inputs["calibration_start_time"], "%Y-%m-%d %H:%M:%S")
        start_time = tzobject.localize(start_time)
        start_time = start_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        end_time = datetime.strptime(self.inputs["calibration_end_time"], "%Y-%m-%d %H:%M:%S")
        end_time = tzobject.localize(end_time)
        end_time = end_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        timestep = 3600  # hardcoded 1 hour since flowrate is in m3/h

        database = self.plant.database

        esp_vlp_head, _ = database.read_internal_database(
            self.unit.plant.name,
            self.unit.name,
            "esp_vlp_head.calculated",
            start_time,
            end_time,
            timestep,
        )

        esp_theoretical_head, _ = database.read_internal_database(
            self.unit.plant.name,
            self.unit.name,
            "esp_theoretical_head.calculated",
            start_time,
            end_time,
            timestep,
        )

        x = []
        y = []
        for xi, yi in zip(esp_vlp_head, esp_theoretical_head):
            if xi is not None and yi is not None:
                x.append(xi)
                y.append(yi)
        x = np.array(x)
        y = np.array(y)

        if len(x) < 2:
            raise ValueError("Not enough valid data points for calibration.")

        # Linear regression: y = ax + b
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        a = np.sum((x - x_mean) * (y - y_mean)) / np.sum((x - x_mean) ** 2)
        b = y_mean - a * x_mean

        self.outputs["esp_correction_factor"] = f"{a};{b}"

    def calculate(self):
        """Calculate IPR, VLP, ESP."""
        xValues_arrays = []
        min_flow_array = []
        max_flow_array = []
        frequency_array = np.arange(
            self.inputs["min_frequency"], self.inputs["max_frequency"] + 10, 10
        )
        min_flow = self.ESP.parameters["min_flow"]
        max_flow = self.ESP.parameters["max_flow"]

        for freq in frequency_array:
            Xmin = 0
            Xmax = max_flow * 2
            min_flow_freq = min_flow * freq / 60
            min_flow_array.append(min_flow_freq)
            max_flow_freq = max_flow * freq / 60
            max_flow_array.append(max_flow_freq)

            # Flow rates scaled by frequency
            x_array = np.arange(Xmin * freq / 60, Xmax * freq / 60, 10 * freq / 60)
            xValues_arrays.append(x_array)

        self.outputs["xValues"] = xValues_arrays
        self.outputs["frequency"] = frequency_array
        self.outputs["min_flow_array"] = min_flow_array
        self.outputs["max_flow_array"] = max_flow_array

        self.get_data()
        self.calculate_pump_head_curve()

    def calculate_pump_head_curve(self):
        """Calculate ESP output."""
        try:
            pump_head_all = []
            pump_power_all = []
            pump_eff_all = []
            head_min_flow_freq = []
            head_max_flow_freq = []
            min_flow = self.ESP.parameters["min_flow"]
            max_flow = self.ESP.parameters["max_flow"]

            for freq_idx, freq in enumerate(self.outputs["frequency"]):
                u = dict()
                pump_head_freq = []
                pump_power_freq = []
                pump_eff_freq = []
                xValues_array = self.outputs["xValues"][freq_idx]

                for flow in xValues_array:
                    u["pump_freq"] = freq
                    u["pump_flow"] = flow * 60 / freq / 3600  # Convert flow to m^3/s

                    x = []
                    self.ESP.calculate_output(u, x)

                    # ASSERT
                    y = self.ESP.get_output()
                    pump_head_freq.append(y["pump_head"] / 1e5)  # Convert to bar
                    pump_power_freq.append(y["pump_power"])
                    pump_eff_freq.append(y["pump_eff"])

                pump_head_all.append(pump_head_freq)
                pump_power_all.append(pump_power_freq)
                pump_eff_all.append(pump_eff_freq)

                # Min flow
                u = dict()
                u["pump_freq"] = freq
                u["pump_flow"] = min_flow / 3600  # Convert flow to m^3/s

                x = []
                self.ESP.calculate_output(u, x)

                # ASSERT
                y = self.ESP.get_output()
                head_min_flow = y["pump_head"] / 1e5
                head_min_flow_freq.append(head_min_flow)

                # Max flow
                u = dict()
                u["pump_freq"] = freq
                u["pump_flow"] = max_flow / 3600  # Convert flow to m^3/s

                x = []
                self.ESP.calculate_output(u, x)

                # ASSERT
                y = self.ESP.get_output()
                head_max_flow = y["pump_head"] / 1e5
                head_max_flow_freq.append(head_max_flow)

        except Exception as e:
            print("ERROR:" + repr(e))
            pump_head_all = None
            pump_power_all = None
            pump_eff_all = None

        self.outputs["pump_head"] = pump_head_all
        self.outputs["pump_power"] = pump_power_all
        self.outputs["pump_eff"] = pump_eff_all
        self.outputs["pump_head_min_flow"] = head_min_flow_freq
        self.outputs["pump_head_max_flow"] = head_max_flow_freq

    def get_sensor_data_failure_prediction(self):
        """Get all sensor data required for failure prediction from database."""
        start_time = datetime.strptime(self.inputs["start_time"], "%Y-%m-%d %H:%M:%S")
        start_time = tzobject.localize(start_time)
        start_time = start_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        end_time = datetime.strptime(self.inputs["end_time"], "%Y-%m-%d %H:%M:%S")
        end_time = tzobject.localize(end_time)
        end_time = end_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        timestep = 3600  # 1 hour

        database = self.plant.database
        unit_name = self.unit.name
        plant_name = self.unit.plant.name

        well_unit = None
        if self.unit.from_units:
            well_unit = self.unit.from_units[0]

        sensor_data = {}

        time_array = None
        try:
            result, time_array = database.read_internal_database(
                plant_name, unit_name, "esp_flow.measured", start_time, end_time, timestep
            )
            sensor_data["Brine flow rate"] = result
        except Exception as e:
            print(f"Warning: Could not read esp_flow.measured: {e}")
            start_dt = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ")
            end_dt = datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%SZ")
            time_array = pd.date_range(start_dt, end_dt, freq=f"{timestep}S")

        data_length = len(time_array)

        tags_mapping = {
            "intake pressure ESP": ("esp_inlet_pressure", "measured"),
            "discharge pressure ESP": ("esp_outlet_pressure", "measured"),
            "ESP Motor temperature": ("esp_motor_temperature", "measured"),
            "Vibration (Vx)": ("esp_vibration_x", "measured"),
            "Vibration (Vy, Vz)": ("esp_vibration_y", "measured"),
        }

        for col_name, (tag_base, tag_type) in tags_mapping.items():
            tag = f"{tag_base}.{tag_type}"
            try:
                result, _ = database.read_internal_database(
                    plant_name, unit_name, tag, start_time, end_time, timestep
                )
                sensor_data[col_name] = result
            except Exception as e:
                print(f"Warning: Could not read {tag}: {e}")
                sensor_data[col_name] = [None] * data_length

        if well_unit:
            try:
                result, _ = database.read_internal_database(
                    plant_name,
                    well_unit.name,
                    "productionwell_wellhead_pressure.measured",
                    start_time,
                    end_time,
                    timestep,
                )
                sensor_data["wellhead pressure"] = result
            except Exception as e:
                print(f"Warning: Could not read wellhead pressure: {e}")
                sensor_data["wellhead pressure"] = [None] * data_length

            try:
                result, _ = database.read_internal_database(
                    plant_name,
                    well_unit.name,
                    "productionwell_wellhead_temperature.measured",
                    start_time,
                    end_time,
                    timestep,
                )
                sensor_data["wellhead temperature"] = result
            except Exception as e:
                print(f"Warning: Could not read wellhead temperature: {e}")
                sensor_data["wellhead temperature"] = [None] * data_length
        else:
            sensor_data["wellhead pressure"] = [None] * data_length
            sensor_data["wellhead temperature"] = [None] * data_length

        df = pd.DataFrame(sensor_data, index=pd.to_datetime(time_array))

        return df

    def filter_sensor_data(self, df):
        """Filter sensor data to remove unphysical values.

        This follows the same thresholds as used in the training pipeline.
        """
        df.loc[df["Brine flow rate"] > 450, "Brine flow rate"] = np.nan
        df.loc[df["Brine flow rate"] < 0, "Brine flow rate"] = np.nan
        df.loc[df["wellhead pressure"] > 40, "wellhead pressure"] = np.nan
        df.loc[df["wellhead pressure"] < 0, "wellhead pressure"] = np.nan
        df.loc[df["wellhead temperature"] > 120, "wellhead temperature"] = np.nan
        df.loc[df["wellhead temperature"] < -5, "wellhead temperature"] = np.nan
        df.loc[df["intake pressure ESP"] > 150, "intake pressure ESP"] = np.nan
        df.loc[df["intake pressure ESP"] < 0, "intake pressure ESP"] = np.nan
        df.loc[df["discharge pressure ESP"] > 150, "discharge pressure ESP"] = np.nan
        df.loc[df["discharge pressure ESP"] < 0, "discharge pressure ESP"] = np.nan
        df.loc[df["ESP Motor temperature"] > 200, "ESP Motor temperature"] = np.nan
        df.loc[df["ESP Motor temperature"] < 20, "ESP Motor temperature"] = np.nan
        df.loc[df["Vibration (Vx)"] > 3, "Vibration (Vx)"] = np.nan
        df.loc[df["Vibration (Vx)"] < 0, "Vibration (Vx)"] = np.nan
        df.loc[df["Vibration (Vy, Vz)"] > 3, "Vibration (Vy, Vz)"] = np.nan
        df.loc[df["Vibration (Vy, Vz)"] < 0, "Vibration (Vy, Vz)"] = np.nan

    def predict_failures(self, model_path=None, prediction_mode="forward"):
        """Predict failures using ML model based on sensor data.

        This function follows the exact preprocessing pipeline from training the model:
        1. Filter unphysical values
        2. Calculate Vibration from components
        3. Apply rolling window average (96 points = 4 days for 1-hour data)
        4. Extract 7 relevant features
        5. Scale features using StandardScaler
        6. Make predictions using HistGradientBoostingClassifier

        Args:
            model_path: Path to the ML model pickle file.
            prediction_mode: Mode of prediction:
                - "forward": Show 60-day window (30 days before + 30 days after selected time)
                - "historical": Analyze entire historical period
        """
        if model_path is None:
            current_dir = Path(__file__).resolve().parent
            model_path = current_dir / "ml_model" / "SavedModel_TestTrainVal_30.pkl"

        original_start_time = None
        original_end_time = None
        if prediction_mode == "forward":
            selected_time_str = self.inputs.get("selected_time", None)
            if selected_time_str:
                try:
                    selected_time = datetime.strptime(selected_time_str, "%Y-%m-%d %H:%M:%S")
                    selected_time = tzobject.localize(selected_time)
                    selected_time = pd.to_datetime(selected_time)
                    window_start = selected_time - pd.Timedelta(days=30)
                    window_end = selected_time + pd.Timedelta(days=30)
                    original_start_time = self.inputs.get("start_time", None)
                    original_end_time = self.inputs.get("end_time", None)
                    self.inputs["start_time"] = window_start.strftime("%Y-%m-%d %H:%M:%S")
                    self.inputs["end_time"] = window_end.strftime("%Y-%m-%d %H:%M:%S")
                    msg = (
                        f"Forward mode: Data window set to {self.inputs['start_time']} -> "
                        f"{self.inputs['end_time']} (60-day window around "
                        f"selected_time {selected_time_str})"
                    )
                    print(msg)
                except Exception as e:
                    print(f"Warning: Could not apply selected_time window for forward mode: {e}")

        # Step 1: Get sensor data from database
        try:
            df = self.get_sensor_data_failure_prediction()
            if original_end_time is not None:
                self.inputs["end_time"] = original_end_time
            if original_start_time is not None:
                self.inputs["start_time"] = original_start_time
        except Exception as e:
            if original_end_time is not None:
                self.inputs["end_time"] = original_end_time
            if original_start_time is not None:
                self.inputs["start_time"] = original_start_time
            print(f"Error getting sensor data: {e}")
            self.outputs["failure_predictions"] = None
            self.outputs["failure_times"] = None
            return

        if df.empty:
            print("No sensor data available for failure prediction")
            self.outputs["failure_predictions"] = None
            self.outputs["failure_times"] = None
            return

        # Step 2: Filter unphysical values
        self.filter_sensor_data(df)

        # Step 3: Calculate Vibration (Pythagorean theorem)
        df["Vibration"] = np.sqrt(df["Vibration (Vx)"] ** 2 + df["Vibration (Vy, Vz)"] ** 2)

        # Step 4: Average noisy sensor data (rolling window = 96 points)
        # For 1-hour data: 96 points = 96 hours = 4 days
        rolling_window = 96
        for col in df.columns:
            df[col] = df[col].rolling(window=rolling_window).mean()

        self._sensor_df_for_plot = df.copy()

        # Step 5: Specify relevant features (exact order as training)
        relevant = [
            "Vibration",
            "ESP Motor temperature",
            "wellhead temperature",
            "wellhead pressure",
            "Brine flow rate",
            "intake pressure ESP",
            "discharge pressure ESP",
        ]

        missing = [f for f in relevant if f not in df.columns]
        if missing:
            print(f"Warning: Missing required features: {missing}")
            for f in missing:
                df[f] = np.nan

        features_df = df[relevant].copy()
        num_features = features_df.count(axis=1)

        # Step 6: Scale features using StandardScaler
        scaler = None
        model = None

        scaler_path = model_path.parent / f"{model_path.stem}_scaler.pkl"
        if scaler_path.exists():
            try:
                scaler = joblib.load(scaler_path)
                print(f"Loaded scaler from training: {scaler_path}")
            except Exception as e:
                print(f"Warning: Could not load scaler from {scaler_path}: {e}")

        if scaler is None:
            try:
                model_data = joblib.load(model_path)
                if isinstance(model_data, dict) and "scaler" in model_data:
                    scaler = model_data["scaler"]
                    model = model_data.get("model", None)
            except Exception:
                pass

        if scaler is not None:
            features_scaled = pd.DataFrame(
                scaler.transform(features_df), index=features_df.index, columns=features_df.columns
            )
        else:
            scaler = StandardScaler()
            features_scaled = pd.DataFrame(
                scaler.fit_transform(features_df),
                index=features_df.index,
                columns=features_df.columns,
            )

        # Step 7: Load model and make predictions
        try:
            if model is None:
                model = joblib.load(model_path)
                if isinstance(model, dict) and "model" in model:
                    model = model["model"]
        except Exception as e:
            print(f"Error loading ML model: {e}")
            self.outputs["failure_predictions"] = None
            self.outputs["failure_times"] = None
            return

        try:
            predictions = model.predict_proba(features_scaled)[:, 1]

            if len(features_scaled.index) > 1:
                idx_diff = features_scaled.index[1] - features_scaled.index[0]
                time_diff = idx_diff.total_seconds() / 3600  # hours
                if time_diff <= 0.5:  # 15-minute or less data
                    smoothing_window = 480  # 120 hours (5 days) for 15-minute data
                else:  # 1-hour data
                    smoothing_window = 120  # 120 hours (5 days) for 1-hour data
            else:
                smoothing_window = 120  # default (5 days)

            predictions_series = pd.Series(predictions, index=features_scaled.index)
            predictions_smoothed = predictions_series.rolling(
                window=smoothing_window, min_periods=1
            ).mean()
            predictions = predictions_smoothed.values

            prediction_times = features_scaled.index
            if prediction_mode == "forward":
                selected_time = self.inputs.get("selected_time", None)
                if selected_time is None:
                    selected_time = self.inputs.get("end_time", None)
                if selected_time:
                    try:
                        current_time = datetime.strptime(selected_time, "%Y-%m-%d %H:%M:%S")
                        current_time = tzobject.localize(current_time)
                        current_time = pd.to_datetime(current_time)
                        self.outputs["selected_time"] = current_time
                    except Exception as e:
                        print(f"Warning: Could not parse selected_time for forward mode: {e}")

            num_features_values = num_features.values

            self.outputs["failure_predictions"] = predictions
            self.outputs["failure_times"] = prediction_times
            self.outputs["failure_probability"] = predictions
            self.outputs["num_features"] = num_features_values
            self.outputs["prediction_mode"] = prediction_mode

        except Exception as e:
            print(f"Error making predictions: {e}")
            self.outputs["failure_predictions"] = None
            self.outputs["failure_times"] = None

    def plot(self):
        """Plot pump curves and the measured data."""
        bar_to_meters = 10.1972  # 1 bar ≈ 10.1972 meters of water head

        def format_func(value, ti):
            date = pd.to_datetime(value)
            return date.strftime("%d %B %Y")

        time_measured = pd.to_datetime(self.outputs["time"])
        flow_measured = self.outputs["flow_measured"]
        esp_vlp_head_calculated = self.outputs["esp_vlp_head_calculated"]
        time_x = flow_measured

        pump_head_all = self.outputs["pump_head"]
        xValues = self.outputs["xValues"]
        frequency_array = self.outputs["frequency"]

        # Head calibration
        a, b = [float(x) for x in self.outputs["esp_correction_factor"].split(";")]
        head_corrected = np.array(
            [a * x + b if x is not None else None for x in esp_vlp_head_calculated]
        )
        head_corrected_m = head_corrected * bar_to_meters

        plt.figure()

        # Plot measured data with a color map representing time
        scatter = plt.scatter(time_x, head_corrected_m, c=time_measured.astype("int64"), cmap="jet")
        colorbar = plt.colorbar(scatter)
        colorbar.ax.yaxis.set_major_formatter(plt.FuncFormatter(format_func))

        # Iterate over each frequency and corresponding flow array
        for i, freq in enumerate(frequency_array):
            pump_head_meters = np.array(pump_head_all[i]) * bar_to_meters
            plt.plot(xValues[i], pump_head_meters, label=f"Frequency: {freq} Hz")

        head_min_flow_freq = np.array(self.outputs["pump_head_min_flow"]) * bar_to_meters
        head_max_flow_freq = np.array(self.outputs["pump_head_max_flow"]) * bar_to_meters
        min_flow_array = self.outputs["min_flow_array"]
        max_flow_array = self.outputs["max_flow_array"]
        plt.plot(min_flow_array, head_min_flow_freq, label="Min optimum rate", linestyle="--")
        plt.plot(max_flow_array, head_max_flow_freq, label="Max optimum rate", linestyle="--")
        plt.xlabel("Flow Rate (m³/h)")
        plt.ylabel("Pump Head (m)")
        plt.title("Pump Head vs Flow Rate")
        plt.legend()
        plt.xlim(left=0)
        plt.ylim(bottom=0)
        plt.xticks(ticks=range(0, int(max(xValues[i])) + 20, 20))
        plt.yticks(ticks=range(0, int(max(pump_head_meters)) + 100, 100))
        plt.grid(True)
        plt.show()

    def plot_features(self):
        """Plot key ESP sensor features over time."""
        time_measured = pd.to_datetime(self.outputs["time"])
        flow_measured = np.array(self.outputs["flow_measured"])
        frequency_measured = np.array(self.outputs["frequency_measured"])

        motor_temp_data = None
        motor_temp_times = None
        if hasattr(self, "_sensor_df_for_plot") and self._sensor_df_for_plot is not None:
            df_plot = self._sensor_df_for_plot
            if "ESP Motor temperature" in df_plot.columns:
                motor_temp_series = df_plot["ESP Motor temperature"]
                valid_mask = ~motor_temp_series.isna()
                if valid_mask.any():
                    motor_temp_data = motor_temp_series[valid_mask].values
                    motor_temp_times = motor_temp_series[valid_mask].index

        flow_valid_mask = (
            (flow_measured is not None) & ~np.isnan(flow_measured) & (flow_measured > 0)
        )
        flow_valid = flow_measured[flow_valid_mask]
        flow_times_valid = time_measured[flow_valid_mask]

        freq_valid_mask = (frequency_measured is not None) & ~np.isnan(frequency_measured)
        freq_valid = frequency_measured[freq_valid_mask]
        freq_times_valid = time_measured[freq_valid_mask]

        end_time_str = self.inputs.get("end_time", None)
        if end_time_str:
            current_time = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
            current_time = tzobject.localize(current_time)
            current_time = pd.to_datetime(current_time)
        else:
            current_time = time_measured[-1] if len(time_measured) > 0 else None

        fig, ax1 = plt.subplots(figsize=(16, 6))

        ax1.grid(True, which="major", linestyle=":", alpha=0.4)
        ax1.set_axisbelow(True)
        ax1.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax1.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax1.xaxis.get_major_locator()))

        if motor_temp_data is not None and len(motor_temp_data) > 0:
            ax1.scatter(
                motor_temp_times,
                motor_temp_data,
                color="#2E8B57",
                s=15,
                alpha=0.6,
                edgecolor="none",
                label="Motor Temperature",
                zorder=3,
            )
            ylabel = "Motor Temperature (°C)"
            ax1.set_ylabel(ylabel, fontsize=12, fontweight="bold", color="#2E8B57")
            ax1.set_ylim([20, 200])
            ax1.tick_params(axis="y", labelcolor="#2E8B57")

        if len(freq_valid) > 0:
            ax2 = ax1.twinx()
            ax2.scatter(
                freq_times_valid,
                freq_valid,
                color="#9370DB",
                s=15,
                alpha=0.6,
                edgecolor="none",
                label="Frequency",
                zorder=3,
            )
            ax2.set_ylabel("Frequency (Hz)", fontsize=12, fontweight="bold", color="#9370DB")
            ax2.set_ylim([0, 70])
            ax2.tick_params(axis="y", labelcolor="#9370DB")
            ax2.spines["right"].set_position(("outward", 60))

        if len(flow_valid) > 0:
            ax3 = ax1.twinx()
            ax3.scatter(
                flow_times_valid,
                flow_valid,
                color="#FF4FA3",
                s=12,
                alpha=0.6,
                edgecolor="none",
                label="Flowrate",
                zorder=3,
            )
            ax3.set_ylabel("Flowrate (m³/h)", fontsize=12, fontweight="bold", color="#FF4FA3")
            ax3.set_ylim([0, 450])
            ax3.tick_params(axis="y", labelcolor="#FF4FA3")
            ax3.spines["right"].set_position(("outward", 120))

        if current_time:
            ax1.axvline(
                x=current_time,
                color="black",
                linestyle="-",
                linewidth=2,
                alpha=0.7,
                zorder=4,
                label="Current Time",
            )

        handles, labels = ax1.get_legend_handles_labels()
        if len(freq_valid) > 0:
            handles2, labels2 = ax2.get_legend_handles_labels()
            handles.extend(handles2)
            labels.extend(labels2)
        if len(flow_valid) > 0:
            handles3, labels3 = ax3.get_legend_handles_labels()
            handles.extend(handles3)
            labels.extend(labels3)

        ax1.set_xlabel("Time", fontsize=12)
        title = "ESP Sensor Features - Motor Temperature, Frequency, and Flow Rate"
        ax1.set_title(title, fontsize=13, fontweight="bold", pad=15)
        fig.tight_layout()
        plt.show()

    def plot_failure_prediction(self):
        """Plot failure prediction probability over time.

        The plot shows:
        - Probability of failure occurring within the next 30 days from each timestamp
        - Horizontal bands for risk zones (High/Moderate/Low)
        - A dashed vertical line at the selected time in forward mode

        Modes:
            - "forward": x-axis is a 60-day window (30 days before and 30 days after
              the selected time), with a dashed line at the selected time.
            - "historical": shows the full available period.
        """
        failure_preds = self.outputs.get("failure_predictions")
        if "failure_predictions" not in self.outputs or failure_preds is None:
            print("No failure predictions available. Run predict_failures() first.")
            return

        failure_predictions = self.outputs["failure_predictions"]
        failure_times = self.outputs["failure_times"]

        if isinstance(failure_times, np.ndarray):
            failure_times = pd.to_datetime(failure_times)
        elif not isinstance(failure_times, pd.DatetimeIndex):
            failure_times = pd.to_datetime(failure_times)

        prediction_mode = self.outputs.get("prediction_mode", "forward")

        current_time = None
        if prediction_mode == "forward":
            current_time = self.outputs.get("selected_time", None)
            if current_time is None:
                end_time_str = self.inputs.get("end_time", None)
                if end_time_str:
                    try:
                        current_time = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
                        current_time = tzobject.localize(current_time)
                        current_time = pd.to_datetime(current_time)
                    except Exception:
                        current_time = failure_times[-1] if len(failure_times) > 0 else None
                else:
                    current_time = failure_times[-1] if len(failure_times) > 0 else None

        fig, ax = plt.subplots(figsize=(16, 6))

        ax.grid(True, which="major", linestyle=":", alpha=0.4)
        ax.set_axisbelow(True)
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))

        high_risk_threshold = 0.7
        moderate_risk_threshold = 0.3

        x_min = failure_times.min() if len(failure_times) > 0 else pd.Timestamp.now()
        x_max = failure_times.max() if len(failure_times) > 0 else pd.Timestamp.now()

        ax.axhspan(
            high_risk_threshold,
            1.0,
            xmin=0,
            xmax=1,
            color="red",
            alpha=0.15,
            zorder=1,
            edgecolor="none",
        )

        ax.axhspan(
            moderate_risk_threshold,
            high_risk_threshold,
            xmin=0,
            xmax=1,
            color="orange",
            alpha=0.1,
            zorder=1,
            edgecolor="none",
        )

        ax.axhspan(
            0.0,
            moderate_risk_threshold,
            xmin=0,
            xmax=1,
            color="yellow",
            alpha=0.08,
            zorder=1,
            edgecolor="none",
        )

        ax.axhline(
            y=high_risk_threshold,
            color="darkred",
            linestyle="--",
            linewidth=1.5,
            alpha=0.5,
            zorder=2,
            label=None,
        )
        ax.axhline(
            y=moderate_risk_threshold,
            color="darkorange",
            linestyle="--",
            linewidth=1.5,
            alpha=0.5,
            zorder=2,
            label=None,
        )

        ax.plot(
            failure_times,
            failure_predictions,
            color="#0047AB",
            linewidth=1.5,
            alpha=0.7,
            label="Failure Probability Prediction",
            zorder=3,
        )
        ax.scatter(
            failure_times,
            failure_predictions,
            color="#0047AB",
            s=15,
            alpha=0.8,
            edgecolors="none",
            zorder=4,
        )

        if current_time and prediction_mode == "forward":
            ax.axvline(
                x=current_time, color="black", linestyle="--", linewidth=2, alpha=0.9, zorder=6
            )

        ylabel = "Failure Probability\n(within next 30 days from each timestamp)"
        ax.set_ylabel(ylabel, fontsize=12, fontweight="bold")
        ax.set_ylim([0, 1])
        ax.set_xlabel("Time", fontsize=12)

        if prediction_mode == "forward" and current_time is not None and len(failure_times) > 0:
            x_min = current_time - pd.Timedelta(days=30)
            x_max = current_time + pd.Timedelta(days=30)
            if x_min < failure_times.min():
                x_min = failure_times.min()
            if x_max > failure_times.max():
                x_max = failure_times.max()
            ax.set_xlim([x_min, x_max])

        if prediction_mode == "forward":
            mode_title = (
                "Forward Prediction Mode (60-day window: "
                "30 days before + 30 days after selected time)"
            )
        else:
            mode_title = "Historical Analysis Mode"
        risk_desc = "Risk zones: High >70%, Moderate 30-70%, Low <30%"
        ax.set_title(
            f"ESP Failure Prediction ({mode_title})\n{risk_desc}",
            fontsize=13,
            fontweight="bold",
            pad=15,
        )
        fig.tight_layout()
        plt.show()

    def plot_comparison(self):
        """Plot the measured and calculated tags."""
        time_measured = pd.to_datetime(self.outputs["time"])
        flow_measured = self.outputs["flow_measured"]
        frequency_measured = self.outputs["frequency_measured"]
        esp_vlp_head_calculated = self.outputs["esp_vlp_head_calculated"]
        esp_theoretical_head_calculated = self.outputs["esp_theoretical_head_calculated"]
        esp_vlp_outlet_pressure_calculated = self.outputs["esp_vlp_outlet_pressure_calculated"]
        esp_vlp_ipr_inlet_pressure_calculated = self.outputs[
            "esp_vlp_ipr_inlet_pressure_calculated"
        ]
        intake_pressure_measured = self.outputs["inlet_pressure_measured"]
        esp_theoretical_outlet_pressure_calculated = self.outputs[
            "esp_theoretical_outlet_pressure_calculated"
        ]

        # Head calibration
        a, b = [float(x) for x in self.outputs["esp_correction_factor"][0].split(";")]
        head_corrected = np.array(
            [a * x + b if x is not None else None for x in esp_vlp_head_calculated]
        )

        fig, axes = plt.subplots(4, 2, figsize=(12, 12))
        fig.tight_layout(pad=4.0)

        axes[0, 0].plot(time_measured, flow_measured, label="Flow")
        axes[0, 0].legend()
        axes[0, 0].grid(True)
        axes[0, 0].set_title("Flow vs Time")

        axes[0, 1].plot(time_measured, frequency_measured, label="Frequency")
        axes[0, 1].legend()
        axes[0, 1].grid(True)
        axes[0, 1].set_title("Frequency vs Time")

        axes[1, 0].plot(time_measured, esp_vlp_head_calculated, label="Calculated Head via VLP")
        axes[1, 0].plot(time_measured, esp_theoretical_head_calculated, label="Theoretical Head")
        axes[1, 0].plot(
            time_measured,
            head_corrected,
            label=f"Calibrated VLP Head ({a:.2f}*x + {b:.2f})",
            linestyle="--",
        )
        axes[1, 0].legend()
        axes[1, 0].grid(True)
        axes[1, 0].set_title("Head vs Time")

        axes[1, 1].plot(
            time_measured,
            esp_vlp_head_calculated - esp_theoretical_head_calculated,
            label="differences",
        )
        axes[1, 1].legend()
        axes[1, 1].grid(True)
        axes[1, 1].set_title("Calculated head via VLP - Theoretical head vs Time")

        axes[2, 0].plot(
            time_measured,
            esp_vlp_outlet_pressure_calculated,
            label="Calculated Outlet Pressure via VLP",
        )
        axes[2, 0].plot(
            time_measured,
            esp_theoretical_outlet_pressure_calculated,
            label="Theoretical Outlet Pressure",
        )
        axes[2, 0].legend()
        axes[2, 0].grid(True)
        axes[2, 0].set_title("Outlet Pressure vs Time")

        axes[2, 1].plot(
            time_measured,
            esp_vlp_outlet_pressure_calculated - esp_theoretical_outlet_pressure_calculated,
            label="differences",
        )
        axes[2, 1].legend()
        axes[2, 1].grid(True)
        axes[2, 1].set_title(
            "Calculated Outlet Pressure via VLP - Theoretical Outlet Pressure vs Time"
        )

        axes[3, 0].plot(time_measured, intake_pressure_measured, label="Measured Inlet Pressure")
        axes[3, 0].plot(
            time_measured,
            esp_vlp_ipr_inlet_pressure_calculated,
            label="Calculated Inlet Pressure via VLP-IPR",
        )
        axes[3, 0].legend()
        axes[3, 0].grid(True)
        axes[3, 0].set_title("Inlet Pressure vs Time")

        axes[3, 1].plot(
            time_measured,
            intake_pressure_measured - esp_vlp_ipr_inlet_pressure_calculated,
            label="differences",
        )
        axes[3, 1].legend()
        axes[3, 1].grid(True)
        axes[3, 1].set_title(
            "Measured Inlet Pressure - Calculated Inlet Pressure via VLP-IPR vs Time"
        )

        plt.show()
