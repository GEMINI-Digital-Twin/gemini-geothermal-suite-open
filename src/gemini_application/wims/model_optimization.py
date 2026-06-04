"""CO2 corrosion model parameter optimization using SciPy minimize."""

from datetime import datetime

import numpy as np
import pandas as pd
import ruptures as rpt
from matplotlib import pyplot as plt
from scipy.optimize import minimize

# TODO: save optmized parameters and use them as initial guess


class OptCO2Corrosion:
    """Calibrate CO2 Corrosion Model parameters against measured data.

    Uses SciPy's minimize function for optimization.
    """

    def __init__(self, inputs, outputs, VLP, unit, co2_models, joint_corrosion_models_opt):
        """Initialize CO2 corrosion optimization model."""
        # Store references
        self.inputs = inputs
        self.outputs = outputs
        self.VLP = VLP
        self.logs = inputs["uploadedLogs"]
        self.unit = unit
        self.co2_models = co2_models
        self.corrosion_models = joint_corrosion_models_opt

        self.outputs["modelledCorrosionRateCalibrated"] = pd.DataFrame(
            range(1, len(self.corrosion_models) + 1),
            index=range(len(self.corrosion_models)),
            columns=["Joint No."],
        )
        self.outputs["modelledCorrosionRate"] = pd.DataFrame(
            range(1, len(self.corrosion_models) + 1),
            index=range(len(self.corrosion_models)),
            columns=["Joint No."],
        )
        # --- Build Real-Valued and Normalized Bounds --- #
        self.real_bounds = []
        self.xo_real = []
        for model in self.corrosion_models:
            corrosion_model_name = model.parameters["corrosion_model"]

            if corrosion_model_name == "DLD":
                # Suppose we have 1 parameter with real bound [0, 10]
                # self.real_bounds.append((0.0, 10.0))
                self.real_bounds.extend(
                    [
                        (0.0, 1000.0),
                        (0.0, 100000.0),
                        (0.0, 20),
                        (0.0, 100),
                    ]
                )
                self.xo_real.extend(
                    [
                        4.93,
                        1119,
                        0.58,
                        2.45,
                    ]
                )
            elif corrosion_model_name == "DLM":
                # Suppose 3 parameters with real bounds
                self.real_bounds.extend([(0.0, 100.0), (0.0, 10.0), (0.0, 5.0)])
            else:
                # Default => 1 parameter
                self.real_bounds.append((0.0, 1.0))

        # Normalized bounds are always 0..1 for each parameter
        self.normalized_bounds = [(0.0, 1.0)] * len(self.real_bounds)

    # ----------------------------------------------------------------------------------------------
    # Normalization / Denormalization
    # ----------------------------------------------------------------------------------------------
    def normalize_params(self, real_params):
        """Convert real-valued parameters to normalized [0,1]."""
        norm_params = []
        for x, (lo, hi) in zip(real_params, self.real_bounds):
            z = (x - lo) / (hi - lo)
            norm_params.append(z)
        return np.array(norm_params)

    def denormalize_params(self, norm_params):
        """Convert normalized parameters [0,1] to real-valued."""
        real_params = []
        for z, (lo, hi) in zip(norm_params, self.real_bounds):
            x = lo + z * (hi - lo)
            real_params.append(x)
        return np.array(real_params)

    # -------------------------------------------------------------------------
    # Main "multi-interval" modelled corrosion logic
    # -------------------------------------------------------------------------

    def get_corrosion_rate_from_models_segmented(self, calibrated_interval, init_run=False):
        """Compute modelled corrosion in multiple intervals.

        - Nominal (baseline) date -> 1st log date
        - 1st log date -> 2nd log date
        - 2nd log date -> 3rd log date
        - ...

        For each interval, we:

        1) Filter the flow/pressure/temp data to [start_date, end_date)
        2) Compute partial corrosion with a pairwise approach
        3) Convert the sum of partial corrosion to [mm/year] over that interval
        4) Store in a new column in `self.outputs['modelled_corrosion_rate']`
        """
        # Check well type

        # We'll store multiple columns, one per interval
        # Start with the "base" DataFrame

        unsorted_logs = list(
            zip(
                self.inputs["uploadedLogs"]["logName"],
                self.inputs["uploadedLogs"]["logDate"],
                self.inputs["uploadedLogs"]["logData"],
                self.outputs["processedLogs"],
            )
        )
        sorted_logs = sorted(
            unsorted_logs, key=lambda x: datetime.strptime(x[1], "%H-%M-%S %d-%m-%Y")
        )

        # 2) Build a sorted list of log dates
        #    plus a "nominal baseline date"
        #    (this could be well installation date or an artificial baseline).
        fmt = "%Y-%m-%d %H:%M:%S"  # The format of your date string
        nominal_baseline_date = datetime.strptime(self.inputs["start_time"], fmt)
        sorted_log_dates = []
        for log in sorted_logs:
            sorted_log_dates.append(datetime.strptime(log[1], "%H-%M-%S %d-%m-%Y"))

        # If no logs at all => just 1 interval from nominal_baseline_date -> now (or skip)
        if len(sorted_log_dates) == 0:
            print("No logs => single interval from nominal to 'end of data' assumed.")
            interval_label = f"Modelled Corrosion (Nominal->{datetime.now().strftime('%Y-%m-%d')})"
            self._compute_corrosion_for_interval(
                nominal_baseline_date, datetime.now(), interval_label
            )
            return

        # If we have logs => build the boundaries list
        boundaries = [nominal_baseline_date] + sorted_log_dates
        if calibrated_interval == "last":
            boundaries = ([nominal_baseline_date] + sorted_log_dates)[-2:]
        else:
            boundaries = [nominal_baseline_date] + sorted_log_dates
        # Example: if we have 2 logs => boundaries = [ nominal, log1, log2 ]

        # 3) For each adjacent pair in boundaries, compute partial modelled corrosion
        for i in range(len(boundaries) - 1):
            start_date = boundaries[i]
            end_date = boundaries[i + 1]

            # We'll build a label for the column
            if i == 0:
                # nominal -> log1
                if len(sorted_log_dates) == 1:
                    col_label = (
                        f"Corrosion rate [mm/year] (Nominal -> " f"{end_date.strftime('%Y-%m-%d')})"
                    )
                else:
                    col_label = (
                        f"Corrosion rate [mm/year] ({start_date.strftime('%Y-%m-%d')} -> "
                        f"{end_date.strftime('%Y-%m-%d')})"
                    )
            else:
                # log_i -> log_{i+1}
                col_label = (
                    f"Corrosion rate [mm/year] ({start_date.strftime('%Y-%m-%d')} -> "
                    f"{end_date.strftime('%Y-%m-%d')})"
                )

            self._compute_corrosion_for_interval(start_date, end_date, col_label, init_run)

    def _compute_corrosion_for_interval(
        self, start_date, end_date, column_label, init_run, output_switch="rate"
    ):
        """Filter flow/pressure/temp data and compute partial pairwise calculation.

        Filters data to [start_date, end_date), does partial pairwise
        calculation, and stores result in modelled_corrosion_rate.
        """
        # Check well type
        well_type = "productionwell"  # Default to production well
        if "production" in self.unit.name:
            well_type = "productionwell"
        elif "injection" in self.unit.name:
            well_type = "injectionwell"

        # 1) Filter your flow/pressure/temp data for that time range
        flow_df = pd.DataFrame(
            {"datetime": self.inputs["time"], "value": self.inputs["flow"]}
        ).copy()
        # Convert to datetime (assume the DataFrame datetimes are already in UTC)
        flow_df["datetime"] = pd.to_datetime(flow_df["datetime"])
        # Convert start_date and end_date to timezone-aware datetimes (UTC)
        start_date = pd.to_datetime(start_date).tz_localize("UTC")
        end_date = pd.to_datetime(end_date).tz_localize("UTC")

        try:
            flow_subset = flow_df[
                (flow_df["datetime"] >= start_date) & (flow_df["datetime"] < end_date)
            ].sort_values("datetime")
            pressure_df = pd.DataFrame(
                {"datetime": self.inputs["time"], "value": self.inputs["pressure"]}
            ).copy()
            pressure_df["datetime"] = pd.to_datetime(pressure_df["datetime"])
            pressure_subset = pressure_df[
                (pressure_df["datetime"] >= start_date) & (pressure_df["datetime"] < end_date)
            ].sort_values("datetime")

            temperature_df = pd.DataFrame(
                {"datetime": self.inputs["time"], "value": self.inputs["temperature"]}
            ).copy()
            temperature_df["datetime"] = pd.to_datetime(temperature_df["datetime"])
            temperature_subset = temperature_df[
                (temperature_df["datetime"] >= start_date) & (temperature_df["datetime"] < end_date)
            ].sort_values("datetime")

            # Try to coarsen the time series
            try:
                flow_subset, pressure_subset, temperature_subset = (
                    self.coarsen_timeseries_by_change_point(
                        flow_subset, pressure_subset, temperature_subset
                    )
                )
            except Exception:
                pass

            # Get the number of joints
            n_joints = len(self.unit.parameters[f"{well_type}_tally_table"])

            # Initialize the corrosion rate arrays
            corrosion_rates = np.zeros(n_joints)
            partial_corrosion = np.zeros(n_joints)

            # Get the time arrays
            # Note: removed unused variables flow_times
            # since they're not used in the calculations

            # Here for simplicity, we say i-th row in flow_subset aligns with
            # i-th row in pressure_subset, etc.
            n_time_points = len(flow_subset)

            # Initialize the well hydraulic model
            well_hydraulic_param = {
                "flow": flow_subset["value"].values,
                "pressure": pressure_subset["value"].values,
                "temperature": temperature_subset["value"].values,
                "n_time_points": n_time_points,
                "n_joints": n_joints,
                "water_chemistry_data": self.inputs.get("water_chemistry"),
                "monthly_production_data": self.inputs.get("monthly_production_data"),
                "monthly_dates": self.inputs.get("monthly_dates"),
                "direction": "down",  # Fixed undefined variable
            }
            self.VLP.update_parameters(well_hydraulic_param)

            # Loop through each joint
            for joint_idx in range(n_joints):
                section_temps = temperature_subset["value"].values
                section_pressures = pressure_subset["value"].values
                # Calculate the corrosion rate for this joint
                for sec_idx, (sec_temp_c, sec_pres_bar) in enumerate(
                    zip(section_temps, section_pressures)
                ):
                    # Get the CO2 partial pressure
                    co2_partial_pressure = self.co2_models[joint_idx].get_co2_partial_pressure(
                        sec_temp_c, sec_pres_bar, self.inputs.get("water_chemistry")
                    )
                    # Get the corrosion rate
                    corrosion_rate = self.corrosion_models[joint_idx].get_corrosion_rate(
                        sec_temp_c, sec_pres_bar, co2_partial_pressure
                    )
                    # Add the corrosion rate to the total
                    corrosion_rates[joint_idx] += corrosion_rate

                # Calculate the average corrosion rate for this joint
                corrosion_rates[joint_idx] /= n_time_points

                # Calculate the partial corrosion for this joint
                delta_time = end_date - start_date
                partial_corrosion[joint_idx] = (
                    corrosion_rates[joint_idx] * delta_time.total_seconds() / 31536000
                )

            # Store the results in the outputs
            try:
                # Create a DataFrame with the corrosion rates
                corrosion_df = pd.DataFrame(
                    {"Joint": range(1, n_joints + 1), column_label: corrosion_rates}
                )
                # Set the index to the joint number
                corrosion_df.set_index("Joint", inplace=True)
                # Store the corrosion rates in the outputs
                self.outputs["modelledCorrosionRate"][column_label] = corrosion_df[column_label]

                # Store the partial corrosion in the outputs
                if output_switch == "partial":
                    if "modelledCorrosionRateCalibrated" not in self.outputs:
                        self.outputs["modelledCorrosionRateCalibrated"] = pd.DataFrame()
                    self.outputs["modelledCorrosionRateCalibrated"][
                        column_label
                    ] = partial_corrosion

            except Exception as e:
                print(f"Error in corrosion computation: {e}")
                pass

        except Exception as e:
            print(f"Error in corrosion computation: {e}")
            pass

    def _compute_single_reading_corrosion(
        self, flow_row, press_row, temp_row, start_date, end_date, column_label
    ):
        """Calculate single partial calculation for single data point interval.

        If only one data point in interval, assume (end_date - start_date)
        for duration and do a single partial calculation.
        """
        n_joints = len(self.inputs["tally"]["Joint No."])
        partial_corrosion = np.zeros(n_joints)

        duration_hours = (end_date - start_date).total_seconds() / 3600.0
        if duration_hours <= 0:
            duration_hours = 1.0  # fallback

        flow_val = flow_row["value"] / 3600.0
        pres_pa = press_row["value"] * 1e5
        temp_k = temp_row["value"] + 273.15

        vlp_input = {
            "pressure": pres_pa,
            "temperature": temp_k,
            "flowrate": flow_val,
            "temperature_ambient": 15.0 + 273.15,
            "direction": "down",
        }
        self.VLP.calculate_output(vlp_input, [])
        vlp_output = self.VLP.get_output()
        section_pressures = [p / 1e5 for p in vlp_output["section_pressure_output"]]
        section_temps = [t - 273.15 for t in vlp_output["section_temperature_output"]]

        for i, (sec_temp_c, sec_pres_bar) in enumerate(zip(section_temps, section_pressures)):
            (rho_g, rho_l, gmf, eta_g, eta_l, cp_g, cp_l, K_g, K_l, sigma) = self.VLP.PVT.get_pvt(
                sec_temp_c, sec_pres_bar
            )

            co2_input = {
                "gas_pressure": 0.5,
                "co2_mol_fraction": 0.1882,
                "gas_water_ratio": 0.01,
                "temperature_sample": 20.0,
                "temperature_system": sec_temp_c,
                "gas_molecular_weight": 22.955,
                "gas_density": rho_g,
            }
            self.co2_models[i].calculate_output(co2_input, [])
            co2_pp = self.co2_models[i].get_output()["CO2 Partial Pressure [bar]"]

            corr_input = {
                "pressure": sec_pres_bar,
                "temperature": sec_temp_c,
                "co2_partial_pressure": co2_pp,
                "flow_rate": flow_val,
            }
            self.corrosion_models[i].calculate_output(corr_input, [])
            corrosion_rate = self.corrosion_models[i].get_output()["corrosion_rate"]

            partial_corrosion[i] += corrosion_rate * (duration_hours / 8760.0)

        # Scale to mm/year over that interval
        partial_corrosion *= 8760.0 / duration_hours

        self.outputs["modelled_corrosion_rate"][column_label] = partial_corrosion

    # ----------------------------------------------------------------------------------------------
    # Objective Function
    # ----------------------------------------------------------------------------------------------
    def objective_function(self, norm_param_vector, calibrated_interval=None, *args):
        """
        Objective function to be minimized during calibration.

        Sum of squared errors (SSE) between modelled and measured corrosion.
        """
        # print(norm_param_vector[:12])
        # 1) Denormalize
        real_params = self.denormalize_params(norm_param_vector)

        # 2) Unpack parameters into each corrosion model
        idx = 0
        for model in self.corrosion_models:
            corrosion_model_name = model.parameters["corrosion_model"]
            if corrosion_model_name == "DLD":
                p1 = real_params[idx]
                p2 = real_params[idx + 1]
                p3 = real_params[idx + 2]
                p4 = real_params[idx + 3]
                idx += 4
                model.parameters["A"] = p1
                model.parameters["B"] = p2
                model.parameters["C"] = p3
                model.parameters["D"] = p4
            elif corrosion_model_name == "DLM":
                p1 = real_params[idx]
                p2 = real_params[idx + 1]
                p3 = real_params[idx + 2]
                idx += 3
                model.parameters["A"] = p1
                model.parameters["B"] = p2
                model.parameters["C"] = p3
            else:
                p1 = real_params[idx]
                idx += 1
                model.parameters["A"] = p1

        # 3) Compute corrosion: single-section or all-sections
        self.get_corrosion_rate_from_models_segmented(calibrated_interval)

        # 4) Extract SSE from outputs
        modelled_df = self.outputs["modelledCorrosionRateCalibrated"]
        # print(modelled_df)
        measured_df = self.outputs["measuredCorrosionRate"]

        # 4) Build a list of columns to compare (skip 'Joint No.' or other metadata)
        #    We'll collect only columns that exist in BOTH modelled_df and measured_df
        #    in the same name.
        all_modelled_cols = [
            c for c in modelled_df.columns if c != "Joint No." and c in measured_df.columns
        ]

        # (6) Compute SSE across the chosen columns
        sse = 0.0
        for col in all_modelled_cols:
            modelled_vals = modelled_df[col].values
            measured_vals = measured_df[col].values
            errors = modelled_vals - measured_vals
            sse += np.sum(errors**2)

        print(sse)
        return sse

    def get_constraints(self):
        """Define constraints for optimization.

        Example method to define constraints for optimization.
        Returns None if not used.
        """
        return None

    # ----------------------------------------------------------------------------------------------
    # 5) Primary calibration routine: normalizes init guess & uses normalized bounds
    # ----------------------------------------------------------------------------------------------
    def calibrate_slsqp(self):
        """Calibrate parameters for all models in normalized space.

        Optimize parameters for all models at once, in normalized [0..1]
        space. Then denormalize the final solution, push it back to the
        model, and show final measured vs. modeled rates.
        """
        x0_real = self.xo_real

        # Normalize the initial guess so each param is in [0,1]
        x0_norm = self.normalize_params(x0_real)

        # Define constraints in normalized space, if needed (here: None)
        constraints = self.get_constraints()

        # Get un-calibrated result
        self.get_corrosion_rate_from_models_segmented(calibrated_interval="last", init_run=True)

        # Actually run the optimization in normalized [0..1] space
        result = minimize(
            fun=lambda p: self.objective_function(p, calibrated_interval="last"),
            x0=x0_norm,
            bounds=self.normalized_bounds,  # (0,1) for each parameter
            method="SLSQP",
            constraints=constraints,
            options={"maxiter": 2, "iprint": 6, "ftol": 1e-6, "disp": True, "eps": 1e-3},
        )

        # Check if optimization succeeded
        if result.success:
            print("Optimization succeeded!")
        else:
            print(f"Optimization failed: {result.message}")

        # ------------------------------------------------------------------------------------------
        # 6) Convert the final normalized params -> real space
        # ------------------------------------------------------------------------------------------
        # Note: removed unused variable best_params_real

        # Inspect the final columns for debugging
        # print(self.outputs['modelled_corrosion_rate'])
        # print(self.outputs['modelled_corrosion_rate_init'])
        # print(self.outputs['measured_corrosion_rate'])
        # fig = self.plot()
        print("Optimization complete")
        return result

    def calibrate_cobyla(self):
        """Calibrate parameters for all models in normalized space.

        Optimize parameters for all models at once, in normalized [0..1]
        space. Then denormalize the final solution, push it back to the
        model, and show final measured vs. modeled rates.
        """
        # Build a random initial guess in real space
        # x0_real = []
        # for (lo, hi) in self.real_bounds:
        #     # Draw a random float in [lo, hi]
        #     init_val = random.uniform(lo, hi)
        #     x0_real.append(init_val)
        # x0_real = np.array(x0_real)
        # 1) Build initial guess in REAL space as midpoints
        x0_real = []
        param_constraints = []
        # Note: removed unused variable n_params

        for i, (lo, hi) in enumerate(self.real_bounds):
            # Midpoint as initial guess

            def lower_bound_constraint_factory(index, lower):
                # Return a function that checks x[index] >= lower
                return lambda x: x[index] - lower  # must be >= 0

            def upper_bound_constraint_factory(index, upper):
                # Return a function that checks x[index] <= upper
                return lambda x: upper - x[index]  # must be >= 0

            param_constraints.append({"type": "ineq", "fun": lower_bound_constraint_factory(i, lo)})
            param_constraints.append({"type": "ineq", "fun": upper_bound_constraint_factory(i, hi)})

        x0_real = self.xo_real
        x0_norm = self.normalize_params(x0_real)

        # Get un-calibrated result
        self.get_corrosion_rate_from_models_segmented(calibrated_interval="last", init_run=True)
        print("Optimization started")
        result = minimize(
            fun=lambda p: self.objective_function(p, calibrated_interval="last"),
            x0=x0_norm,
            method="COBYLA",
            constraints=param_constraints,  # Our manually created inequalities
            options={
                "maxiter": 2000,
                "disp": True,
                "rhobeg": 10e-1,  # initial step size guess
                # you can also set 'tol' or others if you want
            },
        )

        # Check if optimization succeeded
        if result.success:
            print("Optimization succeeded!")
        else:
            print(f"Optimization stoped: {result.message}")

        # Note: removed unused variable best_params_real

        # Inspect the final columns for debugging
        # print(self.outputs['modelledCorrosionRate'])
        # print(self.outputs['modelledCorrosionRateCalibrated'])
        # print(self.outputs['measuredCorrosionRate'])
        print("Optimization complete")
        return result

    def coarsen_timeseries_by_change_point(
        self, df1, df2, df3, value_col="value", pen=3, plot=False
    ):
        """Coarsen a time series by detecting segments where the values do not change much.

        Parameters:
          df (pd.DataFrame): DataFrame with a DateTime index.
          value_col (str): The column name containing the values to analyze.
          pen (float or int): Penalty parameter for the PELT change-point
                             detection algorithm.
          plot (bool): If True, plot the original time series with detected
                      change points.

        Returns:
          pd.DataFrame: A DataFrame with columns ['start_date', 'end_date',
                       'mean_value'] for each segment.
        """
        # Fit the change-point detection algorithm (PELT) on the time series values
        algo = rpt.Pelt(model="l2").fit(df1[value_col].values)
        change_points = algo.predict(pen=pen)

        dfs = [df1, df2, df3]
        dfs_coarse = []

        for df in dfs:
            segments = []
            start = 0
            segments.append({"datetime": df.datetime.iloc[0], "value": df.value.iloc[0]})
            for cp in change_points:
                # Extract the segment from start index to the current change point
                segment = df.iloc[start:cp]
                mean_value = segment[value_col].mean()
                segments.append(
                    {"datetime": segment.datetime[(segment.index[-1])], "value": mean_value}
                )
                start = cp
            dfs_coarse.append(pd.DataFrame(segments))

        return dfs_coarse

    # def optimize(self):
    #     bounds = self.get_bounds()
    #     init_guess = self.get_init_guess()
    #     constraints = self.get_constraints()
    #     opt = minimize(self.objective_func,
    #                    x0=init_guess,
    #                    bounds=bounds,
    #                    method='SLSQP',
    #                    options={'maxiter': 100,
    #                             'ftol': 1e-6,
    #                             'iprint': 6,
    #                             'disp': True,
    #                             'eps': 0.01},
    #                    args=[],
    #                    constraints=constraints)
    #
    #     return opt.x * self.get_norms()

    def plot(self):
        """Plot optimization results."""
        plt.figure()
        x = self.outputs["modelledCorrosionRate"]["Joint No."].values

        for column in self.outputs["measured_corrosion_rate"].columns[1:]:
            y = self.outputs["measured_corrosion_rate"][column]
            y0 = self.outputs["modelledCorrosionRate"][column]
            y1 = self.outputs["modelledCorrosionRateCalibrated"][column]

            plt.plot(x, y, label=f"True response {column} ")
            plt.plot(x, y0, label=f"Un-optimized response {column} ")
            plt.plot(x, y1, label=f"Optimized response {column} ")

        plt.legend()
        plt.title("Corrosion rate plot")
        plt.xlabel("Joint number")
        plt.ylabel("Corrosion rate [mm/year]")
        plt.grid()
        plt.tight_layout()
        plt.show()
