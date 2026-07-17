"""Per-joint CO2 corrosion parameter calibration using SciPy minimize.

The modelled corrosion rate comes from the production-data path
(:func:`build_prod_corrosion_context` + the corrosion correlation) and the
measured target from caliper logs
(:func:`get_measured_corrosion_rate_from_logs`).  Because each joint's modelled
rate depends only on its own parameters and its own precomputed
pressure/temperature/CO2, and each log-to-log interval is independent, the
total sum-of-squared-errors is fully separable: the calibration solves one
small SLSQP problem per (joint, interval) over a shared, precomputed context
instead of one large coupled optimization.  A well with three logs therefore
yields a distinct parameter set for the log1->log2 and log2->log3 intervals.
"""

import json
import os
from datetime import datetime

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from scipy.optimize import minimize

from gemini_application.wims.corrosion_from_logs import (
    WALL_THICKNESS_CHANGE_RATE_PREFIX,
    get_measured_corrosion_rate_from_logs,
)
from gemini_application.wims.corrosion_from_prod_data import (
    build_prod_corrosion_context,
    corroded_mm_for_interval,
    corrosion_rate_for_joint_interval,
    corrosion_rates_from_context,
)

# Real-valued bounds and initial guess for the DLD parameters (A, B, C, D).
# Bounds are intentionally wide and signed (negatives allowed): the calibration
# prioritises matching the measured rate over physical plausibility, so the
# optimizer is free to move each coefficient either side of its nominal value.
# Ranges are still kept inside numerically safe limits (the reaction term is
# 10 ** (A - B/T + C*log10(f)), which overflows for very large exponents); the
# objective penalises any parameter set that yields a non-finite rate.
DLD_PARAM_NAMES = ["A", "B", "C", "D"]
DLD_REAL_BOUNDS = [(-100.0, 100.0), (-1.0e5, 1.0e5), (-50.0, 50.0), (-1000.0, 1000.0)]
DLD_X0 = [4.93, 1119.0, 0.58, 2.45]

# Per-joint sign multiplier E in {-1, +1} applied in front of the rate
# (modelled = E * dld_rate).  The DLD model can only produce a non-negative
# corrosion rate (metal loss), so E lets the modelled rate match measured values
# that are negative (a survey-to-survey tool/calibration difference where the
# later log reads a smaller bore).  E is the direction of the measured change, so
# it is *derived* per joint from the sign of the measured rate (not optimized);
# the DLD coefficients then calibrate the magnitude and stay meaningful.
SIGN_POS = 1.0
SIGN_NEG = -1.0

# Penalty returned when a parameter combination makes the model blow up
# (e.g. underflow in the reaction-controlled term -> division by zero).
_OBJECTIVE_PENALTY = 1e12


class OptCO2Corrosion:
    """Calibrate per-joint CO2 corrosion parameters against log-measured rates."""

    def __init__(
        self,
        inputs,
        outputs,
        corrosion_models,
        co2_models,
        vlp,
        esp_joint_start_idx=None,
        param_store_path=None,
    ):
        """Initialise the optimizer and precompute everything reusable.

        The expensive, parameter-independent work (VLP/PVT/CO2) and the measured
        target are computed once here; the per-joint solves reuse them.
        """
        # -- store references -----------------------------------------------
        self.inputs = inputs
        self.outputs = outputs
        self.corrosion_models = corrosion_models
        self.co2_models = co2_models
        self.vlp = vlp
        self.param_store_path = param_store_path

        if esp_joint_start_idx is None:
            esp_joint_start_idx = inputs.get("esp_joint_start_idx", 0)
        self.esp_joint_start_idx = esp_joint_start_idx

        # -- joint bookkeeping ----------------------------------------------
        self.well_tally = inputs["well_tally"]
        self.n_total_joints = len(self.well_tally)
        self.n_active_joints = self.n_total_joints - esp_joint_start_idx

        # -- precompute parameter-independent prod-data context -------------
        self.context = build_prod_corrosion_context(
            self.well_tally,
            inputs,
            vlp,
            co2_models,
            esp_joint_start_idx=esp_joint_start_idx,
            verbose=False,
        )

        # -- compute the log-measured calibration target once ---------------
        self.measured_df = self._compute_measured_target()

        # -- bounds / warm-start (DLD: A, B, C, D) --------------------------
        # The optimizer fits the 4 DLD coefficients to the measured *magnitude*
        # of each (joint, interval); the sign multiplier E (in {-1, +1}) is
        # derived per (joint, interval), not solved.
        self.param_names = DLD_PARAM_NAMES
        self.real_bounds = list(DLD_REAL_BOUNDS)
        self.normalized_bounds = [(0.0, 1.0)] * len(self.real_bounds)

        # -- per-(joint, interval) state, keyed by (total_idx, rate_col) ----
        self.interval_by_col = self.context.get("interval_by_col", {})
        self.pair_signs = {}  # measured direction E in {-1, +1}
        self.pair_params = {}  # calibrated [A, B, C, D] written by calibrate()
        self.warm_pairs = self._load_warm_pairs()

        # -- resolve common rate columns + per-(joint, interval) targets ----
        self._build_calibration_targets()

    # ----------------------------------------------------------------------
    # Setup helpers
    # ----------------------------------------------------------------------
    def _compute_measured_target(self):
        """Compute the measured corrosion rate from caliper logs (once)."""
        return get_measured_corrosion_rate_from_logs(
            well_tally=self.well_tally,
            logs_metadata=self.inputs.get("logs_metadata", {}),
            selected_log_names=self.inputs.get("selectedLogs", []),
            processed_logs=self.outputs.get("processedLogs", []),
            start_time=self.inputs["start_time"],
        )

    def _load_warm_pairs(self):
        """Return persisted ``{(total_idx, rate_col): [A, B, C, D]}`` warm starts.

        Reads the per-interval store written by :meth:`_save_params`.  Returns an
        empty dict (every pair falls back to the DLD defaults) when no compatible
        store exists -- the store is compatible when it targets the same ESP
        offset and a matching number of active joints per interval.
        """
        warm = {}
        path = self.param_store_path
        if not path or not os.path.exists(path):
            return warm

        # -- read and validate the stored parameters ------------------------
        try:
            with open(path, "r", encoding="utf-8") as f:
                stored = json.load(f)
        except (OSError, json.JSONDecodeError):
            return warm

        intervals = stored.get("intervals")
        if (
            not isinstance(intervals, list)
            or stored.get("esp_joint_start_idx") != self.esp_joint_start_idx
        ):
            return warm

        # -- map each stored interval's per-joint params by rate_col --------
        for interval in intervals:
            if not isinstance(interval, dict):
                continue
            rate_col = interval.get("rate_col")
            params = interval.get("params")
            if not rate_col or not isinstance(params, list) or len(params) != self.n_active_joints:
                continue
            for i in range(self.n_active_joints):
                entry = params[i] if isinstance(params[i], dict) else {}
                warm[(self.esp_joint_start_idx + i, rate_col)] = [
                    float(entry.get(name, DLD_X0[j])) for j, name in enumerate(self.param_names)
                ]
        return warm

    def _build_calibration_targets(self):
        """Find the rate columns shared by modelled context and measured logs.

        Stores ``self.common_cols`` (ordered rate-column names present in both)
        and ``self.joint_targets`` -- ``{total_idx: {col: measured_value}}`` for
        joints that have at least one finite measured value.
        """
        # -- collect modelled (context) rate columns ------------------------
        context_cols = [interval["rate_col"] for interval in self.context["intervals"]]

        measured = self.measured_df
        if measured is None or "Joint No." not in measured.columns:
            self.common_cols = []
            self.joint_targets = {}
            return

        # -- intersect with measured rate columns ---------------------------
        measured_rate_cols = [
            c
            for c in measured.columns
            if c != "Joint No." and c.startswith(WALL_THICKNESS_CHANGE_RATE_PREFIX)
        ]
        self.common_cols = [c for c in context_cols if c in measured_rate_cols]

        # -- cache finite per-joint measured values over common columns -----
        joint_targets = {}
        for active_idx in range(self.n_active_joints):
            total_idx = self.esp_joint_start_idx + active_idx
            if total_idx >= len(measured):
                continue
            targets = {}
            for col in self.common_cols:
                value = measured[col].iloc[total_idx]
                if pd.notna(value):
                    targets[col] = float(value)
            if targets:
                joint_targets[total_idx] = targets
        self.joint_targets = joint_targets

        # -- per-(joint, interval) sign E in {-1, +1} from the measured -----
        # direction.  E is the direction of the bore change for that interval
        # (positive = corrosion/metal loss, negative = bore shrank); the DLD
        # coefficients then calibrate the magnitude of that single interval.
        self.pair_signs = {
            (total_idx, col): (SIGN_NEG if value < 0 else SIGN_POS)
            for total_idx, targets in joint_targets.items()
            for col, value in targets.items()
        }

    # ----------------------------------------------------------------------
    # Normalisation / denormalisation
    # ----------------------------------------------------------------------
    def normalize_params(self, real_params):
        """Convert real-valued parameters to normalized [0, 1]."""
        norm = []
        for x, (lo, hi) in zip(real_params, self.real_bounds):
            norm.append((x - lo) / (hi - lo) if hi > lo else 0.0)
        return np.array(norm)

    def denormalize_params(self, norm_params):
        """Convert normalized parameters [0, 1] to real-valued."""
        real = []
        for z, (lo, hi) in zip(norm_params, self.real_bounds):
            real.append(lo + z * (hi - lo))
        return np.array(real)

    # ----------------------------------------------------------------------
    # Per-joint parameter handling
    # ----------------------------------------------------------------------
    def _set_joint_params(self, total_idx, real_params):
        """Write A, B, C, D into the corrosion model for one joint."""
        active_idx = total_idx - self.esp_joint_start_idx
        model = self.corrosion_models[active_idx]
        model.update_parameters(
            {name: float(value) for name, value in zip(self.param_names, real_params)}
        )

    def _pair_modelled_rate(self, total_idx, rate_col, model):
        """Signed modelled rate for one (joint, interval): ``E * dld_rate``.

        ``E`` in {-1, +1} is the measured direction for that pair (defaults to
        +1 when unknown).  Returns ``None`` when the interval/joint is unknown or
        the model yields a non-finite rate.
        """
        interval = self.interval_by_col.get(rate_col)
        if interval is None:
            return None
        rate = corrosion_rate_for_joint_interval(self.context, total_idx, interval, model)
        if rate is None or not np.isfinite(rate):
            return None
        sign = self.pair_signs.get((total_idx, rate_col), SIGN_POS)
        return sign * rate

    def _pair_sse(self, total_idx, rate_col):
        """Squared error for one (joint, interval) at the model's current params."""
        active_idx = total_idx - self.esp_joint_start_idx
        model = self.corrosion_models[active_idx]
        modelled = self._pair_modelled_rate(total_idx, rate_col, model)
        if modelled is None:
            return 0.0
        error = modelled - self.joint_targets[total_idx][rate_col]
        return error * error

    # ----------------------------------------------------------------------
    # Per-joint calibration (separable problem)
    # ----------------------------------------------------------------------
    def _calibrate_pair(self, total_idx, rate_col, maxiter=100):
        """Run SLSQP for one (joint, interval) from several starts; keep the best.

        Multiple starting points -- the nominal literature DLD defaults plus any
        persisted warm-start guess for this exact (joint, interval) -- make the
        solve robust to a degenerate initial guess.  A large ``B`` saved from a
        previously collapsed run drives the reaction term
        ``10 ** (A - B/T + C*log10(f))`` to underflow, so the modelled rate (and
        its gradient) is ~0 and SLSQP "converges" after a single step without
        moving.  Always starting from the nominal defaults (a healthy, non-zero
        rate) lets the optimizer escape that flat region.  The objective
        penalises any parameter set that yields a non-finite rate, so the wide,
        signed bounds cannot be exploited by driving the model into NaN/inf.

        The modelled rate carries the pair sign E (``modelled = E * dld_rate``),
        so the 4 coefficients calibrate the *magnitude* of this single interval
        and the fit can match a negative measured value the DLD model cannot.
        Stores the winning ``[A, B, C, D]`` in ``self.pair_params``.
        """
        active_idx = total_idx - self.esp_joint_start_idx
        model = self.corrosion_models[active_idx]
        measured_value = self.joint_targets[total_idx][rate_col]

        # -- objective: single-interval SSE; blow-up / non-finite -> penalty
        def objective(norm_params):
            self._set_joint_params(total_idx, self.denormalize_params(norm_params))
            try:
                modelled = self._pair_modelled_rate(total_idx, rate_col, model)
            except (ZeroDivisionError, ValueError, OverflowError, FloatingPointError):
                return _OBJECTIVE_PENALTY
            if modelled is None:
                return _OBJECTIVE_PENALTY
            error = modelled - measured_value
            return error * error

        # -- candidate starts: nominal defaults + this pair's warm-start ----
        starts = [list(DLD_X0)]
        warm = self.warm_pairs.get((total_idx, rate_col))
        if warm is not None and not np.allclose(warm, DLD_X0):
            starts.append(list(warm))

        # -- solve from each start, keep the lowest-SSE result --------------
        best = None
        for start_real in starts:
            result = minimize(
                fun=objective,
                x0=self.normalize_params(start_real),
                bounds=self.normalized_bounds,
                method="SLSQP",
                options={"maxiter": maxiter, "ftol": 1e-9},
            )
            if best is None or result.fun < best.fun:
                best = result

        # -- write the winning parameters back + record them ----------------
        best_real = self.denormalize_params(best.x)
        self._set_joint_params(total_idx, best_real)
        self.pair_params[(total_idx, rate_col)] = list(best_real)
        return best

    # ----------------------------------------------------------------------
    # Top-level calibration routine
    # ----------------------------------------------------------------------
    def _interval_label(self, rate_col):
        """Short interval label ('(d1 -> d2)') derived from a rate-column name."""
        return rate_col.replace(WALL_THICKNESS_CHANGE_RATE_PREFIX + " ", "").strip()

    def calibrate(self, maxiter=100, progress_callback=None):
        """Calibrate per-(joint, interval) parameters against log-measured rates.

        Solves one independent 4-variable problem for every (joint, interval)
        pair that has a measured rate -- so a well with three logs yields a
        separate parameter set for the log1->log2 and log2->log3 intervals.
        Stores the uncalibrated and calibrated modelled rates and the measured
        target in ``outputs``, persists the per-interval parameters, and returns
        a summary dict.

        Parameters
        ----------
        maxiter : int, optional
            Maximum SLSQP iterations per (joint, interval) pair.
        progress_callback : callable or None
            Optional ``fn(completed, total, per_joint)`` invoked after each pair
            is solved.  ``per_joint`` is the growing list of per-(joint,
            interval) records (so callers can render live progress).  Exceptions
            raised by the callback are swallowed so progress reporting never
            breaks the calibration.

        Returns
        -------
        dict
            Summary dict that includes ``"per_joint"`` -- one record per
            (joint, interval) with ``interval``/``rate_col`` tags, params
            (A,B,C,D,E), and before/after SSE -- used for the final error
            plot and coefficient table.
        """
        # -- guard: nothing to calibrate ------------------------------------
        if self.context["degenerate"] or not self.common_cols or not self.joint_targets:
            message = (
                "Corrosion calibration skipped: no overlapping measured/modelled "
                "intervals (need processed logs and production data)."
            )
            print(message)
            self.outputs["measuredCorrosionRateFromLogs"] = self.measured_df
            return {"status": "skipped", "message": message, "n_joints": 0, "per_joint": []}

        # -- store the uncalibrated modelled result (nominal DLD defaults) --
        self._apply_nominal_params()
        uncalibrated_table = corrosion_rates_from_context(self.context, self.corrosion_models)
        self.outputs["modelledCorrosionRate"] = self._apply_signs_to_table(uncalibrated_table)

        # -- build the ordered list of (joint, interval) pairs to solve -----
        pairs = [
            (total_idx, rate_col)
            for total_idx in sorted(self.joint_targets.keys())
            for rate_col in self.common_cols
            if rate_col in self.joint_targets[total_idx]
        ]
        n_pairs = len(pairs)

        # -- solve each (joint, interval) independently (SSE is separable) --
        sse_before = 0.0
        sse_after = 0.0
        per_joint = []
        for completed, (total_idx, rate_col) in enumerate(pairs, start=1):
            # "before" = nominal literature DLD (stable, healthy baseline; never
            # a previous run's persisted/collapsed parameters)
            self._set_joint_params(total_idx, list(DLD_X0))
            pair_sse_before = self._pair_sse(total_idx, rate_col)

            result = self._calibrate_pair(total_idx, rate_col, maxiter=maxiter)
            pair_sse_after = float(result.fun)

            sse_before += pair_sse_before
            sse_after += pair_sse_after

            # -- read the calibrated A, B, C, D + the sign E for this pair --
            params = self.pair_params[(total_idx, rate_col)]
            calibrated_params = {
                name: float(value) for name, value in zip(self.param_names, params)
            }
            calibrated_params["E"] = float(self.pair_signs.get((total_idx, rate_col), SIGN_POS))

            # -- record + report per-(joint, interval) error / convergence -
            per_joint.append(
                {
                    "joint": int(total_idx),
                    "joint_label": str(self.context["joint_labels"][total_idx]),
                    "interval": self._interval_label(rate_col),
                    "rate_col": rate_col,
                    "sse_before": float(pair_sse_before),
                    "sse_after": float(pair_sse_after),
                    "params": calibrated_params,
                    "iterations": int(getattr(result, "nit", 0)),
                    "n_func_evals": int(getattr(result, "nfev", 0)),
                    "converged": bool(getattr(result, "success", False)),
                    "message": str(getattr(result, "message", "")),
                }
            )
            if progress_callback is not None:
                try:
                    progress_callback(completed, n_pairs, per_joint)
                except Exception:
                    pass

        # -- store calibrated results (per-interval params + sign) ----------
        calibrated_table = self._build_calibrated_table()
        self.outputs["modelledCorrosionRateCalibrated"] = self._apply_signs_to_table(
            calibrated_table
        )
        self.outputs["measuredCorrosionRateFromLogs"] = self.measured_df

        # -- persist optimized per-interval parameters for reuse next run ---
        self._save_params()

        n_joints = len({total_idx for total_idx, _ in pairs})
        summary = {
            "status": "ok",
            "n_joints": n_joints,
            "n_intervals": len(self.common_cols),
            "n_pairs": n_pairs,
            "sse_before": sse_before,
            "sse_after": sse_after,
            "per_joint": per_joint,
        }
        print(
            f"Corrosion calibration complete: {n_pairs} (joint, interval) pairs "
            f"across {n_joints} joints, SSE {sse_before:.4g} -> {sse_after:.4g}."
        )
        return summary

    def _apply_nominal_params(self):
        """Reset all active joints to the nominal literature DLD parameters.

        This is the *uncalibrated* baseline reported to the user (before vs
        after).  It deliberately ignores any persisted warm-start so the
        baseline is stable and never reflects a previous run's (possibly
        collapsed) parameters.
        """
        for active_idx in range(self.n_active_joints):
            total_idx = self.esp_joint_start_idx + active_idx
            self._set_joint_params(total_idx, list(DLD_X0))

    def _apply_signs_to_table(self, df):
        """Flip each (joint, interval) cell whose sign E is -1.

        The sign is per (joint, interval): a negative-E pair (the bore shrank
        over that interval) gets its rate and matching corroded value flipped so
        the modelled table carries the measured direction.  Pairs with E = +1
        are left untouched.
        """
        # -- nothing to flip without negative signs -------------------------
        if df is None or not self.pair_signs:
            return df

        # -- flip the rate + corroded columns of each negative-E pair -------
        for (total_idx, rate_col), sign in self.pair_signs.items():
            if sign >= 0 or total_idx not in df.index:
                continue
            interval = self.interval_by_col.get(rate_col)
            corroded_col = interval["corroded_col"] if interval else None
            for col in (rate_col, corroded_col):
                if col and col in df.columns and pd.notna(df.at[total_idx, col]):
                    df.at[total_idx, col] = -float(df.at[total_idx, col])
        return df

    def _build_calibrated_table(self):
        """Build the calibrated rate/corroded table column-by-column.

        Each interval column uses that interval's own per-joint calibrated
        parameters (falling back to the nominal DLD defaults for joints that had
        no measured value for the interval).  Signs are applied separately by
        :meth:`_apply_signs_to_table`, so this returns unsigned magnitudes.
        """
        n_total_joints = self.context["n_total_joints"]
        esp_start = self.esp_joint_start_idx

        result_df = pd.DataFrame(
            self.context["joint_labels"],
            index=range(n_total_joints),
            columns=["Joint No."],
        )

        # -- one column pair per interval, each with its own joint params ---
        for interval in self.context["intervals"]:
            rate_col = interval["rate_col"]
            total_duration_yr = interval["total_duration_yr"]

            corroded_mm = np.full(n_total_joints, np.nan)
            corroded_mm[esp_start:] = 0.0

            for active_idx in range(self.n_active_joints):
                total_idx = esp_start + active_idx
                model = self.corrosion_models[active_idx]
                params = self.pair_params.get((total_idx, rate_col), list(DLD_X0))
                self._set_joint_params(total_idx, params)
                corroded_mm[total_idx] = corroded_mm_for_interval(interval, active_idx, model)

            if total_duration_yr > 0:
                avg_rate = corroded_mm / total_duration_yr
            else:
                avg_rate = np.where(np.isnan(corroded_mm), np.nan, 0.0)

            result_df[rate_col] = avg_rate
            result_df[interval["corroded_col"]] = corroded_mm

        return result_df

    # ----------------------------------------------------------------------
    # Persistence
    # ----------------------------------------------------------------------
    def _save_params(self):
        """Write optimized per-interval, per-joint parameters to JSON (atomic).

        The store keeps one entry per interval (in chronological order) so that
        prediction can pick the *latest* interval's parameters.  Each per-joint
        entry holds the calibrated ``A, B, C, D`` plus the derived sign ``E`` so
        the prediction can carry the direction forward.  Joints without a
        calibrated value for an interval fall back to the DLD defaults / E=+1.
        """
        path = self.param_store_path
        if not path:
            return

        # -- gather per-interval, per-joint A, B, C, D, E -------------------
        intervals_payload = []
        for interval in self.context["intervals"]:
            rate_col = interval["rate_col"]
            params_list = []
            for active_idx in range(self.n_active_joints):
                total_idx = self.esp_joint_start_idx + active_idx
                pair = self.pair_params.get((total_idx, rate_col))
                if pair is not None:
                    entry = {name: float(value) for name, value in zip(self.param_names, pair)}
                else:
                    entry = {name: float(DLD_X0[j]) for j, name in enumerate(self.param_names)}
                entry["E"] = float(self.pair_signs.get((total_idx, rate_col), SIGN_POS))
                params_list.append(entry)

            intervals_payload.append(
                {
                    "rate_col": rate_col,
                    "start": interval.get("start"),
                    "end": interval.get("end"),
                    "total_duration_yr": interval["total_duration_yr"],
                    "params": params_list,
                }
            )

        payload = {
            "corrosion_model": "DLD",
            "esp_joint_start_idx": self.esp_joint_start_idx,
            # local timestamp of this calibration (surfaced as "last optimized")
            "optimized_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "intervals": intervals_payload,
        }

        # -- atomic write (tmp + replace) -----------------------------------
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, path)
        except OSError as exc:
            print(f"Could not persist corrosion parameters to {path}: {exc}")

    # ----------------------------------------------------------------------
    # Plotting
    # ----------------------------------------------------------------------
    def plot(self):
        """Plot measured vs modelled (uncalibrated and calibrated) corrosion."""
        measured = self.outputs.get("measuredCorrosionRateFromLogs")
        modelled = self.outputs.get("modelledCorrosionRate")
        calibrated = self.outputs.get("modelledCorrosionRateCalibrated")
        if measured is None or modelled is None or calibrated is None:
            print("Nothing to plot: run calibrate() first.")
            return None

        # -- one line trio per shared interval column -----------------------
        plt.figure()
        x = modelled["Joint No."].values
        for column in self.common_cols:
            if column in measured.columns:
                plt.plot(x, measured[column], label=f"Measured {column}")
            if column in modelled.columns:
                plt.plot(x, modelled[column], label=f"Un-calibrated {column}")
            if column in calibrated.columns:
                plt.plot(x, calibrated[column], label=f"Calibrated {column}")

        plt.legend()
        plt.title("Corrosion rate plot")
        plt.xlabel("Joint number")
        plt.ylabel(WALL_THICKNESS_CHANGE_RATE_PREFIX)
        plt.grid()
        plt.tight_layout()
        plt.show()
