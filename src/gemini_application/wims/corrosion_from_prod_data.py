"""Utilities for corrosion rate estimation from production data."""

from datetime import datetime

import numpy as np
import pandas as pd
import ruptures as rpt

from gemini_application.wims.corrosion_from_logs import (
    WALL_THICKNESS_CHANGE_RATE_PREFIX,
    wall_thickness_change_col,
    wall_thickness_change_rate_col,
)

SECONDS_PER_YEAR = 365.25 * 24 * 3600


def _predecimate_aligned_series(dfs, value_col="value", bin_hours=24):
    """Bin aligned series by *bin_hours* for faster change-point detection.

    The number of bins follows from the series time span and native sampling
    interval; segment means are only computed when the data is finer than
    *bin_hours*.
    """
    # -- sort and check for trivial input ------------------------------------
    sorted_dfs = [df.sort_values("datetime").reset_index(drop=True) for df in dfs]
    df_ref = sorted_dfs[0]
    n = len(df_ref)
    if n <= 1:
        return sorted_dfs, np.arange(n + 1, dtype=int)

    # -- determine if binning is needed -------------------------------------
    datetimes = pd.to_datetime(df_ref["datetime"])
    median_delta_hours = datetimes.diff().dt.total_seconds().median() / 3600.0
    if median_delta_hours <= 0 or np.isnan(median_delta_hours):
        median_delta_hours = 1.0

    if median_delta_hours >= bin_hours:
        return sorted_dfs, np.arange(n + 1, dtype=int)

    # -- assign bin IDs and compute bin edges --------------------------------
    origin = datetimes.iloc[0]
    bin_ids = ((datetimes - origin).dt.total_seconds() / (bin_hours * 3600)).astype(int)

    bin_edges = [0]
    for bin_id in sorted(bin_ids.unique()):
        idx = np.where(bin_ids == bin_id)[0]
        bin_edges.append(int(idx[-1]) + 1)

    # -- compute bin means for each series ----------------------------------
    coarse_dfs = []
    for df in sorted_dfs:
        rows = []
        for i in range(len(bin_edges) - 1):
            segment = df.iloc[bin_edges[i] : bin_edges[i + 1]]
            rows.append(
                {
                    "datetime": segment["datetime"].iloc[-1],
                    "value": segment[value_col].mean(),
                }
            )
        coarse_dfs.append(pd.DataFrame(rows))

    return coarse_dfs, np.array(bin_edges, dtype=int)


def coarsen_timeseries_by_change_point(
    df1,
    df2,
    df3,
    value_col="value",
    pen=3,
    predecimate_bin_hours=24,
    plot=False,
):
    """Coarsen three aligned time series using change-point detection.

    When the native sampling interval is finer than *predecimate_bin_hours*,
    means are computed in fixed-duration bins first; PELT runs on that coarse
    flow series, then breakpoints are mapped back to the original resolution
    for segment averaging.
    """
    # -- predecimate and run PELT change-point detection ---------------------
    dfs = [df1, df2, df3]
    coarse_dfs, bin_edges = _predecimate_aligned_series(
        dfs, value_col=value_col, bin_hours=predecimate_bin_hours
    )

    algo = rpt.Pelt(model="l2").fit(coarse_dfs[0][value_col].values)
    change_points = algo.predict(pen=pen)

    # -- build segment means from original resolution ----------------------
    n_orig = len(df1)
    dfs_coarse = []

    for df in dfs:
        segments = []
        segments.append({"datetime": df.datetime.iloc[0], "value": df.value.iloc[0]})
        start = 0
        for cp in change_points:
            end = int(bin_edges[cp]) if cp < len(bin_edges) else n_orig
            segment = df.iloc[start:end]
            if segment.empty:
                continue
            mean_value = segment[value_col].mean()
            segments.append(
                {
                    "datetime": segment.datetime.iloc[-1],
                    "value": mean_value,
                }
            )
            start = end
        dfs_coarse.append(pd.DataFrame(segments))

    return dfs_coarse


def compute_corrosion_for_interval(
    inputs,
    outputs,
    vlp,
    co2_models,
    corrosion_models,
    start_date,
    end_date,
    column_label,
    output_switch="rate",
    esp_joint_start_idx=0,
):
    """Compute corrosion rate or partial corrosion for a specific interval.

    Parameters
    ----------
    esp_joint_start_idx : int
        First tally index at or below the ESP (production wells).
        ``corrosion_models`` and ``co2_models`` cover only joints from this
        index onward.  Joints above get zero corrosion.
    """
    # -- subset time series to the interval ---------------------------------
    flow_df = pd.DataFrame({"datetime": inputs["time"], "value": inputs["flow"]}).copy()
    flow_subset = flow_df[
        (flow_df["datetime"] >= start_date) & (flow_df["datetime"] < end_date)
    ].sort_values("datetime")

    pressure_df = pd.DataFrame({"datetime": inputs["time"], "value": inputs["pressure"]}).copy()
    pressure_subset = pressure_df[
        (pressure_df["datetime"] >= start_date) & (pressure_df["datetime"] < end_date)
    ].sort_values("datetime")

    temperature_df = pd.DataFrame(
        {"datetime": inputs["time"], "value": inputs["temperature"]}
    ).copy()
    temperature_subset = temperature_df[
        (temperature_df["datetime"] >= start_date) & (temperature_df["datetime"] < end_date)
    ].sort_values("datetime")

    if flow_subset.empty or pressure_subset.empty or temperature_subset.empty:
        print(f"No data for interval {start_date} to {end_date}")
        return

    # -- coarsen time series ------------------------------------------------
    n_total_joints = len(inputs["well_tally"])
    n_active_joints = n_total_joints - esp_joint_start_idx
    corrosion_rates = np.zeros(n_total_joints)
    partial_corrosion = np.zeros(n_total_joints)

    try:
        flow_subset, pressure_subset, temperature_subset = coarsen_timeseries_by_change_point(
            flow_subset, pressure_subset, temperature_subset
        )
    except Exception:
        pass

    flow_values = flow_subset["value"].values
    pressure_values = pressure_subset["value"].values
    temperature_values = temperature_subset["value"].values

    if len(flow_values) == 0 or len(pressure_values) == 0 or len(temperature_values) == 0:
        print(f"No data for interval {start_date} to {end_date}")
        return

    # -- update VLP parameters ----------------------------------------------
    n_time_points = len(flow_values)
    well_hydraulic_param = {
        "flow": flow_values,
        "pressure": pressure_values,
        "temperature": temperature_values,
        "n_time_points": n_time_points,
        "n_joints": n_active_joints,
        "water_chemistry_data": inputs.get("water_chemistry"),
        "monthly_production_data": inputs.get("monthly_production_data"),
        "monthly_dates": inputs.get("monthly_dates"),
        "direction": "down",
    }
    vlp.update_parameters(well_hydraulic_param)

    # -- compute corrosion per active joint ---------------------------------
    for active_idx in range(n_active_joints):
        for sec_temp_c, sec_pres_bar in zip(temperature_values, pressure_values):
            co2_partial_pressure = co2_models[active_idx].get_co2_partial_pressure(
                sec_temp_c, sec_pres_bar, inputs.get("water_chemistry")
            )
            corrosion_rate = corrosion_models[active_idx].get_corrosion_rate(
                sec_temp_c, sec_pres_bar, co2_partial_pressure
            )
            total_idx = esp_joint_start_idx + active_idx
            corrosion_rates[total_idx] += corrosion_rate

        corrosion_rates[total_idx] /= n_time_points
        delta_time = end_date - start_date
        partial_corrosion[total_idx] = (
            corrosion_rates[total_idx] * delta_time.total_seconds() / 31536000
        )

    # -- store results in outputs -------------------------------------------
    try:
        corrosion_df = pd.DataFrame({
            "Joint": range(1, n_total_joints + 1),
            column_label: corrosion_rates,
        })
        corrosion_df.set_index("Joint", inplace=True)
        outputs["modelledCorrosionRate"][column_label] = corrosion_df[column_label]

        if output_switch == "partial":
            if "modelledCorrosionRateCalibrated" not in outputs:
                outputs["modelledCorrosionRateCalibrated"] = pd.DataFrame()
            outputs["modelledCorrosionRateCalibrated"][column_label] = partial_corrosion
    except Exception:
        pass


def get_corrosion_rate_from_models_segmented(
    inputs,
    outputs,
    corrosion_models,
    co2_models,
    vlp,
    calibrated_interval=None,
):
    """Compute modelled corrosion rates over baseline/log-derived intervals."""
    # -- initialise output DataFrame ----------------------------------------
    n_total_joints = len(inputs["well_tally"])
    esp_joint_start_idx = inputs.get("esp_joint_start_idx", 0)

    outputs["modelledCorrosionRate"] = pd.DataFrame(
        range(1, n_total_joints + 1),
        index=range(n_total_joints),
        columns=["Joint No."],
    )

    # -- sort logs by date and build interval boundaries --------------------
    unsorted_logs = list(
        zip(
            inputs["uploadedLogs"]["name"],
            inputs["uploadedLogs"]["date"],
            inputs["uploadedLogs"]["data"],
            outputs["processedLogs"],
        )
    )
    sorted_logs = sorted(unsorted_logs, key=lambda x: datetime.strptime(x[1], "%H-%M-%S %d-%m-%Y"))

    baseline_date = datetime.strptime(inputs["start_time"], "%Y-%m-%d %H:%M:%S")
    sorted_log_dates = [datetime.strptime(log[1], "%H-%M-%S %d-%m-%Y") for log in sorted_logs]

    if len(sorted_log_dates) == 0:
        print("No logs => single interval from baseline to 'end of data' assumed.")
        interval_label = (
            f"Modelled Corrosion "
            f"({baseline_date.strftime('%Y-%m-%d')}->{datetime.now().strftime('%Y-%m-%d')})"
        )
        compute_corrosion_for_interval(
            inputs,
            outputs,
            vlp,
            co2_models,
            corrosion_models,
            baseline_date,
            datetime.now(),
            interval_label,
            esp_joint_start_idx=esp_joint_start_idx,
        )
        return

    boundaries = [baseline_date] + sorted_log_dates
    if calibrated_interval == "last":
        boundaries = boundaries[-2:]

    # -- compute corrosion for each interval --------------------------------
    for i in range(len(boundaries) - 1):
        start_date = boundaries[i]
        end_date = boundaries[i + 1]

        if i == 0 and len(sorted_log_dates) == 1:
            end_label = end_date.strftime("%Y-%m-%d")
            col_label = f"{WALL_THICKNESS_CHANGE_RATE_PREFIX} (Nominal -> {end_label})"
        else:
            col_label = wall_thickness_change_rate_col(
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
            )

        compute_corrosion_for_interval(
            inputs,
            outputs,
            vlp,
            co2_models,
            corrosion_models,
            start_date,
            end_date,
            col_label,
            esp_joint_start_idx=esp_joint_start_idx,
        )


def build_prod_corrosion_context(
    well_tally, inputs, vlp, co2_models, esp_joint_start_idx=0, verbose=True,
    boundaries=None,
):
    """Precompute the parameter-independent inputs for prod-data corrosion.

    Runs the expensive, calibration-invariant work once -- the VLP
    pressure-drop solve, PVT, and CO2 partial-pressure model -- per
    interval/time-step/joint, and caches the resulting per-joint pressure,
    temperature, and CO2 partial pressure together with step durations and
    flow.  :func:`corrosion_rates_from_context` (and the single-joint variant
    used during calibration) can then re-run only the corrosion correlation,
    which is the sole part that depends on the calibrated parameters.

    Parameters
    ----------
    esp_joint_start_idx : int
        First tally index at or below the ESP.  Joints above receive ``NaN``
        corrosion; the ESP joint uses the measured inlet P/T directly and the
        VLP covers only the joints below it (see
        :func:`get_corrosion_rate_from_prod_data`).
    verbose : bool
        When True, print interval/zero-flow diagnostics (preserves the legacy
        behaviour of the public entry point).
    boundaries : list of datetime-like or None
        Explicit interval boundaries (>= 2, ascending).  When provided they are
        used directly instead of being derived from the log-date metadata -- the
        prediction path passes ``[latest_log_date, now]`` to build a single
        forward window.

    Returns
    -------
    dict
        Context with ``joint_labels``, ``n_total_joints``, ``n_active_joints``,
        ``esp_joint_start_idx``, ``degenerate`` (bool), and ``intervals`` -- a
        list of per-interval dicts holding the cached arrays.
    """
    # -- initialise joint bookkeeping ---------------------------------------
    n_total_joints = len(well_tally)
    n_active_joints = n_total_joints - esp_joint_start_idx
    joint_labels = [e.get("Joint", str(i + 1)) for i, e in enumerate(well_tally)]

    context = {
        "joint_labels": joint_labels,
        "n_total_joints": n_total_joints,
        "n_active_joints": n_active_joints,
        "esp_joint_start_idx": esp_joint_start_idx,
        "degenerate": False,
        "intervals": [],
        "interval_by_col": {},
    }

    # -- build time-series DataFrame ----------------------------------------
    times = pd.to_datetime(inputs["time"])
    prod_df = pd.DataFrame({
        "datetime": times,
        "flow": inputs["flow"],
        "pressure": inputs["pressure"],
        "temperature": inputs["temperature"],
    }).sort_values("datetime").reset_index(drop=True)

    if prod_df.empty:
        context["degenerate"] = True
        return context

    # -- use explicit boundaries when given (prediction window) -------------
    if boundaries is not None:
        log_boundaries = [pd.Timestamp(b) for b in boundaries]
        if len(log_boundaries) < 2 or log_boundaries[0] == log_boundaries[-1]:
            context["degenerate"] = True
            return context
    else:
        # -- otherwise extract log boundaries from metadata -----------------
        logs_metadata = inputs.get("logs_metadata") or {}
        baseline_date = None
        other_dates = []
        for entry in logs_metadata.values():
            if not isinstance(entry, dict) or not entry.get("date"):
                continue
            dt = pd.Timestamp(entry["date"])
            if entry.get("is_baseline"):
                baseline_date = dt
            else:
                other_dates.append(dt)

        if baseline_date is not None and other_dates:
            log_boundaries = [baseline_date] + sorted(other_dates)
        elif len(other_dates) >= 2:
            log_boundaries = sorted(other_dates)
        else:
            data_start = prod_df["datetime"].iloc[0]
            data_end = prod_df["datetime"].iloc[-1]
            if data_start == data_end:
                context["degenerate"] = True
                return context
            log_boundaries = [data_start, data_end]

    # -- precompute hydraulics/PVT/CO2 per interval -------------------------
    has_esp = esp_joint_start_idx > 0
    n_vlp_joints = n_active_joints - 1 if has_esp else n_active_joints

    for interval_idx in range(len(log_boundaries) - 1):
        interval_start = log_boundaries[interval_idx]
        interval_end = log_boundaries[interval_idx + 1]

        mask = (prod_df["datetime"] >= interval_start) & (prod_df["datetime"] < interval_end)
        interval_data = prod_df.loc[mask].reset_index(drop=True)

        n_steps = len(interval_data)
        if n_steps == 0:
            if verbose:
                print(f"No data for interval {interval_start} to {interval_end}")
            continue

        # -- compute step durations (non-uniform after coarsening) ----------
        step_times = interval_data["datetime"].values
        step_ends = np.append(step_times[1:], interval_end)
        step_durations_yr = np.array([
            (pd.Timestamp(end) - pd.Timestamp(start)).total_seconds() / SECONDS_PER_YEAR
            for start, end in zip(step_times, step_ends)
        ])

        # -- run VLP -> per-joint P/T -> PVT -> CO2 for each live step -------
        eff_flow_m3s = []
        eff_durations_yr = []
        eff_pres_bar = []
        eff_temp_c = []
        eff_co2_pp = []

        for step_idx in range(n_steps):
            inlet_flow_m3s = interval_data.at[step_idx, "flow"] / 3600.0
            inlet_pres_bar = interval_data.at[step_idx, "pressure"]
            inlet_temp_c = interval_data.at[step_idx, "temperature"]

            # -- skip missing (NaN/inf) or near-zero-flow readings ---------
            # Database gaps come back as NaN; feeding them to the VLP makes
            # mg = gmf * NaN -> NaN, so ``mg == 0`` is False and the wrong
            # (two-phase) flow model is selected.  Treat them like no-flow.
            if (
                not np.isfinite(inlet_flow_m3s)
                or not np.isfinite(inlet_pres_bar)
                or not np.isfinite(inlet_temp_c)
                or inlet_flow_m3s < 1.0 / 3600.0
            ):
                if verbose:
                    print(
                        f"  [SKIP] step={step_idx} no/invalid flow | "
                        f"flow={inlet_flow_m3s * 3600.0:.2f} m3/h, "
                        f"P={inlet_pres_bar:.2f} bar, T={inlet_temp_c:.2f} C | "
                        f"dur={step_durations_yr[step_idx]*SECONDS_PER_YEAR/86400:.1f} days"
                    )
                continue

            inlet_pres_pa = inlet_pres_bar * 1e5
            inlet_temp_k = inlet_temp_c + 273.15

            # -- build per-joint P/T arrays --------------------------------
            if has_esp:
                # ESP joint (active_idx 0): use measured P/T directly.
                # Joints below ESP: compute via VLP.
                joint_pres_bar = [inlet_pres_bar]
                joint_temp_c = [inlet_temp_c]

                if n_vlp_joints > 0:
                    vlp_input = {
                        "pressure": inlet_pres_pa,
                        "temperature": inlet_temp_k,
                        "flowrate": inlet_flow_m3s,
                        "temperature_ambient": 15.0 + 273.15,
                        "direction": "down",
                    }
                    vlp.calculate_output(vlp_input, [])
                    vlp_output = vlp.get_output()
                    joint_pres_bar += [p / 1e5 for p in vlp_output["section_pressure_output"]]
                    joint_temp_c += [t - 273.15 for t in vlp_output["section_temperature_output"]]
            else:
                # Injection well: VLP covers all joints from the wellhead.
                vlp_input = {
                    "pressure": inlet_pres_pa,
                    "temperature": inlet_temp_k,
                    "flowrate": inlet_flow_m3s,
                    "temperature_ambient": 15.0 + 273.15,
                    "direction": "down",
                }
                vlp.calculate_output(vlp_input, [])
                vlp_output = vlp.get_output()
                joint_pres_bar = [p / 1e5 for p in vlp_output["section_pressure_output"]]
                joint_temp_c = [t - 273.15 for t in vlp_output["section_temperature_output"]]

            # -- per-joint PVT -> CO2 partial pressure ---------------------
            step_co2_pp = np.empty(n_active_joints)
            for active_idx in range(n_active_joints):
                rho_g, *_ = vlp.PVT.get_pvt(
                    joint_temp_c[active_idx], joint_pres_bar[active_idx]
                )

                co2_input = {
                    "gas_pressure": 0.5,
                    "co2_mol_fraction": 0.1882,
                    "gas_water_ratio": 0.01,
                    "temperature_sample": 20.0,
                    "temperature_system": joint_temp_c[active_idx],
                    "gas_molecular_weight": 22.955,
                    "gas_density": rho_g,
                }
                co2_models[active_idx].calculate_output(co2_input, [])
                step_co2_pp[active_idx] = co2_models[active_idx].get_output()[
                    "CO2 Partial Pressure [bar]"
                ]

            eff_flow_m3s.append(inlet_flow_m3s)
            eff_durations_yr.append(step_durations_yr[step_idx])
            eff_pres_bar.append(np.asarray(joint_pres_bar, dtype=float))
            eff_temp_c.append(np.asarray(joint_temp_c, dtype=float))
            eff_co2_pp.append(step_co2_pp)

        # -- stack cached arrays as (n_active_joints, n_eff_steps) ----------
        if eff_pres_bar:
            pres_bar = np.stack(eff_pres_bar, axis=1)
            temp_c = np.stack(eff_temp_c, axis=1)
            co2_pp = np.stack(eff_co2_pp, axis=1)
        else:
            pres_bar = np.zeros((n_active_joints, 0))
            temp_c = np.zeros((n_active_joints, 0))
            co2_pp = np.zeros((n_active_joints, 0))

        total_duration_yr = (
            interval_end - interval_start
        ).total_seconds() / SECONDS_PER_YEAR

        date_fmt = "%Y-%m-%d"
        start_str = interval_start.strftime(date_fmt)
        end_str = interval_end.strftime(date_fmt)

        context["intervals"].append({
            "rate_col": wall_thickness_change_rate_col(start_str, end_str),
            "corroded_col": wall_thickness_change_col(start_str, end_str),
            "start": start_str,
            "end": end_str,
            "total_duration_yr": total_duration_yr,
            "n_eff_steps": len(eff_flow_m3s),
            "flow_m3s": np.asarray(eff_flow_m3s, dtype=float),
            "step_durations_yr": np.asarray(eff_durations_yr, dtype=float),
            "pres_bar": pres_bar,
            "temp_c": temp_c,
            "co2_pp": co2_pp,
        })

    # -- index intervals by their rate-column name (convenience lookup) -----
    context["interval_by_col"] = {iv["rate_col"]: iv for iv in context["intervals"]}

    return context


def corroded_mm_for_interval(interval, active_idx, corrosion_model):
    """Integrate one joint's corrosion model over one cached interval.

    Returns the corroded thickness [mm] for ``active_idx`` over ``interval`` by
    summing ``rate * step_duration`` across the interval's effective steps.  This
    is the shared inner loop used by the full-table, single-joint, and
    single-(joint, interval) entry points.
    """
    pres_bar = interval["pres_bar"]
    temp_c = interval["temp_c"]
    co2_pp = interval["co2_pp"]
    flow_m3s = interval["flow_m3s"]
    step_durations_yr = interval["step_durations_yr"]

    corroded = 0.0
    for step_idx in range(interval["n_eff_steps"]):
        corr_input = {
            "pressure": pres_bar[active_idx, step_idx],
            "temperature": temp_c[active_idx, step_idx],
            "co2_partial_pressure": co2_pp[active_idx, step_idx],
            "flow_rate": flow_m3s[step_idx],
        }
        corrosion_model.calculate_output(corr_input, [])
        corroded += corrosion_model.get_output()["corrosion_rate"] * step_durations_yr[step_idx]
    return corroded


def corrosion_rates_from_context(context, corrosion_models, verbose=False):
    """Apply corrosion models to a precomputed context -> result DataFrame.

    Re-runs only the (cheap) corrosion correlation over the cached per-joint
    pressure/temperature/CO2 arrays, reproducing the output of
    :func:`get_corrosion_rate_from_prod_data` for the current model parameters.
    """
    # -- initialise result DataFrame ----------------------------------------
    n_total_joints = context["n_total_joints"]
    esp_joint_start_idx = context["esp_joint_start_idx"]
    n_active_joints = context["n_active_joints"]

    result_df = pd.DataFrame(
        context["joint_labels"],
        index=range(n_total_joints),
        columns=["Joint No."],
    )

    if context["degenerate"]:
        result_df[WALL_THICKNESS_CHANGE_RATE_PREFIX] = np.nan
        return result_df

    # -- compute corrosion for each cached interval -------------------------
    for interval in context["intervals"]:
        total_duration_yr = interval["total_duration_yr"]

        corroded_mm = np.full(n_total_joints, np.nan)
        corroded_mm[esp_joint_start_idx:] = 0.0

        for active_idx in range(n_active_joints):
            total_idx = esp_joint_start_idx + active_idx
            model = corrosion_models[active_idx]
            corroded_mm[total_idx] = corroded_mm_for_interval(interval, active_idx, model)

        # -- derive average rate from total corroded thickness --------------
        if total_duration_yr > 0:
            avg_rate = corroded_mm / total_duration_yr
        else:
            avg_rate = np.where(np.isnan(corroded_mm), np.nan, 0.0)

        result_df[interval["rate_col"]] = avg_rate
        result_df[interval["corroded_col"]] = corroded_mm

    return result_df


def corrosion_rate_for_joint_interval(context, total_idx, interval, corrosion_model):
    """Average modelled rate [mm/year] for one joint over one specific interval.

    Single-(joint, interval) entry point used by the per-interval calibration:
    it evaluates only the requested interval's cached arrays, so each SLSQP step
    touches the minimum amount of work.  Returns ``None`` when the joint is out
    of range, otherwise ``corroded_mm / interval_duration_yr`` (0.0 for a
    zero-duration interval).
    """
    if context["degenerate"]:
        return None
    active_idx = total_idx - context["esp_joint_start_idx"]
    if active_idx < 0 or active_idx >= context["n_active_joints"]:
        return None

    corroded = corroded_mm_for_interval(interval, active_idx, corrosion_model)
    total_duration_yr = interval["total_duration_yr"]
    return corroded / total_duration_yr if total_duration_yr > 0 else 0.0


def corrosion_rates_for_joint_from_context(context, total_idx, corrosion_model):
    """Return ``{rate_col: avg_rate_mm_yr}`` for a single joint over all intervals.

    Convenience multi-interval variant of
    :func:`corrosion_rate_for_joint_interval`; builds no DataFrame.
    """
    rates = {}
    if context["degenerate"]:
        return rates

    esp_joint_start_idx = context["esp_joint_start_idx"]
    active_idx = total_idx - esp_joint_start_idx
    if active_idx < 0 or active_idx >= context["n_active_joints"]:
        return rates

    for interval in context["intervals"]:
        rates[interval["rate_col"]] = corrosion_rate_for_joint_interval(
            context, total_idx, interval, corrosion_model
        )
    return rates


def get_corrosion_rate_from_prod_data(
    well_tally, inputs, corrosion_models, co2_models, vlp, esp_joint_start_idx=0
):
    """Compute corrosion rate from production data using VLP per-joint P/T.

    Splits the production window into intervals defined by log dates from
    ``inputs["logs_metadata"]``.  For each time step within an interval the
    VLP model is run to obtain pressure and temperature at every joint depth,
    then CO2 partial pressure and corrosion rate are computed per joint.

    Thin wrapper over :func:`build_prod_corrosion_context` +
    :func:`corrosion_rates_from_context`; the split lets the calibration loop
    reuse the precomputed (parameter-independent) hydraulics/PVT/CO2 context.

    Parameters
    ----------
    esp_joint_start_idx : int
        First tally index at or below the ESP.  Joints ``0..esp_joint_start_idx-1``
        are above the ESP and receive ``NaN`` corrosion.  The ESP joint
        (``active_idx == 0``) uses the measured inlet P/T directly; the VLP
        geometry and outputs cover only the joints *below* the ESP.
        ``corrosion_models`` / ``co2_models`` correspond to all active joints
        (ESP joint + those below).  Use 0 (default) for injection wells where
        the full tally is active and VLP covers all joints.

    Returns a DataFrame with ``'Joint No.'`` and, for each interval, both a
    ``'Corrosion rate [mm/year] (date1 -> date2)'`` column and a
    ``'Corroded [mm] (date1 -> date2)'`` column.
    """
    context = build_prod_corrosion_context(
        well_tally,
        inputs,
        vlp,
        co2_models,
        esp_joint_start_idx=esp_joint_start_idx,
    )
    return corrosion_rates_from_context(context, corrosion_models, verbose=True)


def compute_single_reading_corrosion(
    inputs,
    outputs,
    vlp,
    co2_models,
    corrosion_models,
    flow_row,
    press_row,
    temp_row,
    start_date,
    end_date,
    column_label,
    esp_joint_start_idx=0,
):
    """Compute corrosion for a single reading interval.

    Parameters
    ----------
    esp_joint_start_idx : int
        First tally index at or below the ESP (production wells).
        The ESP joint uses measured P/T directly; VLP covers only joints
        below.  Joints above the ESP get zero corrosion.
    """
    # -- convert inlet readings to VLP units --------------------------------
    n_total_joints = len(inputs["well_tally"])
    n_active_joints = n_total_joints - esp_joint_start_idx
    has_esp = esp_joint_start_idx > 0
    partial_corrosion = np.zeros(n_total_joints)

    duration_hours = (end_date - start_date).total_seconds() / 3600.0
    if duration_hours <= 0:
        duration_hours = 1.0

    flow_val = flow_row["value"] / 3600.0
    pres_bar = press_row["value"]
    temp_c = temp_row["value"]
    pres_pa = pres_bar * 1e5
    temp_k = temp_c + 273.15

    # -- build per-joint P/T arrays -----------------------------------------
    if has_esp:
        n_vlp_joints = n_active_joints - 1
        joint_pres_bar = [pres_bar]
        joint_temp_c = [temp_c]
        if n_vlp_joints > 0:
            vlp_input = {
                "pressure": pres_pa,
                "temperature": temp_k,
                "flowrate": flow_val,
                "temperature_ambient": 15.0 + 273.15,
                "direction": "down",
            }
            vlp.calculate_output(vlp_input, [])
            vlp_output = vlp.get_output()
            joint_pres_bar += [p / 1e5 for p in vlp_output["section_pressure_output"]]
            joint_temp_c += [t - 273.15 for t in vlp_output["section_temperature_output"]]
    else:
        vlp_input = {
            "pressure": pres_pa,
            "temperature": temp_k,
            "flowrate": flow_val,
            "temperature_ambient": 15.0 + 273.15,
            "direction": "down",
        }
        vlp.calculate_output(vlp_input, [])
        vlp_output = vlp.get_output()
        joint_pres_bar = [p / 1e5 for p in vlp_output["section_pressure_output"]]
        joint_temp_c = [t - 273.15 for t in vlp_output["section_temperature_output"]]

    # -- compute corrosion per active joint via PVT -> CO2 -> corrosion -----
    for active_idx in range(n_active_joints):
        sec_temp_c = joint_temp_c[active_idx]
        sec_pres_bar = joint_pres_bar[active_idx]

        (rho_g, _rho_l, _gmf, _eta_g, _eta_l, _cp_g, _cp_l, _k_g, _k_l, _sigma) = vlp.PVT.get_pvt(
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
        co2_models[active_idx].calculate_output(co2_input, [])
        co2_pp = co2_models[active_idx].get_output()["CO2 Partial Pressure [bar]"]

        corr_input = {
            "pressure": sec_pres_bar,
            "temperature": sec_temp_c,
            "co2_partial_pressure": co2_pp,
            "flow_rate": flow_val,
        }
        corrosion_models[active_idx].calculate_output(corr_input, [])
        corrosion_rate = corrosion_models[active_idx].get_output()["corrosion_rate"]

        total_idx = esp_joint_start_idx + active_idx
        partial_corrosion[total_idx] += corrosion_rate * (duration_hours / 8760.0)

    # -- convert partial corrosion to rate and store ------------------------
    partial_corrosion *= 8760.0 / duration_hours
    outputs["modelled_corrosion_rate"][column_label] = partial_corrosion
