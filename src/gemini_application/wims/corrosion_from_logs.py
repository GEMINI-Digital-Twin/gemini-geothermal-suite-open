"""Utilities for processing caliper logs and deriving measured corrosion outputs."""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

logger = logging.getLogger(__name__)

# -- wall-thickness change column labels (tables / API / UI) ---------------
WALL_THICKNESS_CHANGE_RATE_PREFIX = "Wall thickness change rate [mm/year]"
WALL_THICKNESS_CHANGE_PREFIX = "Wall thickness change [mm]"
PREDICTED_WALL_THICKNESS_CHANGE_RATE_PREFIX = "Predicted wall thickness change rate [mm/year]"
ANNUAL_WALL_THICKNESS_CHANGE_RATE_COL = "Annual wall thickness change rate [mm/year]"


def wall_thickness_change_rate_col(start_str, end_str):
    """Interval column label for wall thickness change rate [mm/year]."""
    return f"{WALL_THICKNESS_CHANGE_RATE_PREFIX} ({start_str} -> {end_str})"


def wall_thickness_change_col(start_str, end_str):
    """Interval column label for signed wall thickness change [mm]."""
    return f"{WALL_THICKNESS_CHANGE_PREFIX} ({start_str} -> {end_str})"


def add_corrosion_columns(df):
    """Add corrosion-related output columns to a DataFrame."""
    df["Max. Penetration [%]"] = None
    df["Max. Wall Loss [%]"] = None
    df["Max. Penetration Depth [m]"] = None
    df["Min. Penetration Depth [m]"] = None
    df["Top Depth [m]"] = None
    df["Bottom Depth [m]"] = None
    df["Length [m]"] = None
    df["Nominal IR [inch]"] = None
    df["Nominal OR [inch]"] = None
    df["Max. Radius [inch]"] = None
    df["Min. Radius [inch]"] = None
    df["Mean. Radius [inch]"] = None
    df["Remaining wall thickness [inch]"] = None
    df["Ovality [%]"] = None
    df["Match Error [%]"] = None
    return df


# ---------------------------------------------------------------------------
# Joint detection helpers
# ---------------------------------------------------------------------------


def _get_log_metadata(uploaded_logs, key, log_idx, default=None):
    """Safely get per-log metadata from uploaded_logs parallel lists."""
    values = uploaded_logs.get(key)
    if values and isinstance(values, list) and log_idx < len(values):
        return values[log_idx]
    return default


def _estimate_depth_step(depths):
    """Estimate the sampling interval from an array of depth values."""
    if len(depths) < 2:
        return 1.0
    diffs = np.abs(np.diff(depths))
    diffs = diffs[diffs > 0]
    if len(diffs) == 0:
        return 1.0
    return float(np.median(diffs))


def _robust_sigma(values):
    """Estimate signal noise using MAD, falling back to standard deviation."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return 0.0

    median = np.median(values)
    mad = np.median(np.abs(values - median))
    sigma = 1.4826 * mad
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = np.std(values)
    if not np.isfinite(sigma):
        return 0.0
    return float(sigma)


def _odd_window_samples(window_m, depth_step, n_samples, min_samples=3):
    """Convert metres to an odd rolling-window sample count."""
    if n_samples <= 0:
        return 0
    if depth_step <= 0:
        depth_step = 1.0

    window = max(int(round(window_m / depth_step)), min_samples)
    window = min(window, n_samples)
    if window % 2 == 0:
        window = window - 1 if window == n_samples else window + 1
    return max(min(window, n_samples), 1)


def _rolling_median(values, window):
    """Return a centered rolling median with edge values filled."""
    return (
        pd.Series(values)
        .rolling(window=window, center=True, min_periods=1)
        .median()
        .values
    )


def _compute_spike_exclusion_zone(joint_radii, depth_step,
                                   min_exclusion_m=0.02,
                                   max_exclusion_fraction=0.01,
                                   sigma_factor=2.0):
    """Compute adaptive exclusion distances at top/bottom of a joint.

    Analyses the per-row mean radius signal to find where the connection
    spike influence ends by detecting where the signal returns to baseline
    levels.  This prevents false-positive corrosion readings near couplings.

    Parameters
    ----------
    joint_radii : DataFrame
        Radii values for a single joint (rows=depth, cols=fingers).
    depth_step : float
        Sampling interval in metres.
    min_exclusion_m : float
        Minimum exclusion distance on each side (metres).
    max_exclusion_fraction : float
        Maximum exclusion as a fraction of joint length (e.g. 0.10 = 10%).
    sigma_factor : float
        Number of MAD-based sigma above baseline to consider as spike
        influence.

    Returns
    -------
    tuple[float, float]
        (top_exclusion_m, bottom_exclusion_m) in metres.
    """
    n_rows = len(joint_radii)
    if n_rows < 5:
        return (min_exclusion_m, min_exclusion_m)

    depths = joint_radii.index.values.astype(float)
    joint_length = depths[-1] - depths[0]
    if joint_length <= 0:
        return (min_exclusion_m, min_exclusion_m)

    max_exclusion_m = max_exclusion_fraction * joint_length

    row_means = joint_radii.mean(axis=1).values.astype(float)

    inner_start = int(n_rows * 0.20)
    inner_end = int(n_rows * 0.80)
    if inner_end - inner_start < 3:
        inner_start = max(0, n_rows // 2 - 1)
        inner_end = min(n_rows, n_rows // 2 + 2)

    inner_values = row_means[inner_start:inner_end]
    baseline = float(np.median(inner_values))
    mad = float(np.median(np.abs(inner_values - baseline)))
    sigma = 1.4826 * mad
    if sigma <= 0:
        sigma = float(np.std(inner_values))
    if sigma <= 0:
        return (min_exclusion_m, min_exclusion_m)

    consecutive_required = 2

    # Walk inward from top to find where signal returns to baseline
    top_exclusion_samples = 0
    count_ok = 0
    for i in range(n_rows):
        if abs(row_means[i] - baseline) <= sigma_factor * sigma:
            count_ok += 1
            if count_ok >= consecutive_required:
                top_exclusion_samples = max(0, i - consecutive_required + 1)
                break
        else:
            count_ok = 0
    else:
        top_exclusion_samples = 0

    # Walk inward from bottom to find where signal returns to baseline
    bot_exclusion_samples = 0
    count_ok = 0
    for i in range(n_rows - 1, -1, -1):
        if abs(row_means[i] - baseline) <= sigma_factor * sigma:
            count_ok += 1
            if count_ok >= consecutive_required:
                bot_exclusion_samples = max(0, (n_rows - 1 - i) - consecutive_required + 1)
                break
        else:
            count_ok = 0
    else:
        bot_exclusion_samples = 0

    # Add a small buffer of 2 samples
    top_exclusion_samples += 2
    bot_exclusion_samples += 2

    top_exclusion_m = float(top_exclusion_samples * depth_step)
    bot_exclusion_m = float(bot_exclusion_samples * depth_step)

    top_exclusion_m = max(min_exclusion_m, min(top_exclusion_m, max_exclusion_m))
    bot_exclusion_m = max(min_exclusion_m, min(bot_exclusion_m, max_exclusion_m))

    # Safety: ensure we don't exclude the entire joint
    if (top_exclusion_m + bot_exclusion_m) >= joint_length * 0.8:
        return (min_exclusion_m, min_exclusion_m)

    return (top_exclusion_m, bot_exclusion_m)


def _aligned_summary_values(caliper_df, col, target_index):
    """Return a numeric summary curve aligned to the average curve index."""
    if not col or col not in caliper_df.columns:
        return None

    series = (
        pd.to_numeric(caliper_df[col], errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
    )
    series = series[~series.index.duplicated(keep="first")]
    aligned = series.reindex(target_index)
    if aligned.notna().sum() < 5:
        return None

    try:
        aligned = aligned.interpolate(method="index", limit_direction="both")
    except ValueError:
        aligned = aligned.interpolate(limit_direction="both")
    aligned = aligned.ffill().bfill()

    values = aligned.values.astype(float)
    if np.isfinite(values).sum() < 5:
        return None
    return values


def _merge_marker_candidates(candidates, merge_distance_m):
    """Merge near-duplicate candidates without relocating the strongest one."""
    if not candidates:
        return []

    candidates = sorted(candidates, key=lambda c: c["depth"])
    merged = []
    group = [candidates[0]]

    for candidate in candidates[1:]:
        if candidate["depth"] - group[-1]["depth"] <= merge_distance_m:
            group.append(candidate)
            continue

        merged.append(_merge_candidate_group(group))
        group = [candidate]

    merged.append(_merge_candidate_group(group))
    return merged


def _candidate_family(candidate):
    """Normalize raw candidate kind into its detector family."""
    kind = candidate.get("kind", "")
    if "spike" in kind:
        return "spike"
    if "gradient" in kind:
        return "gradient"
    if "step" in kind:
        return "step"
    return kind or "marker"


def _merge_candidate_group(group):
    """Merge a group while preserving the strongest candidate depth."""
    best = max(group, key=lambda c: c["score"]).copy()
    families = sorted({_candidate_family(candidate) for candidate in group})
    best["kind"] = "+".join(families)
    best["score"] = float(max(candidate["score"] for candidate in group))

    component_depths = {}
    component_scores = {}
    for family in families:
        family_candidates = [
            candidate
            for candidate in group
            if _candidate_family(candidate) == family
        ]
        family_best = max(family_candidates, key=lambda c: c["score"])
        component_depths[family] = family_best["depth"]
        component_scores[family] = family_best["score"]

    best["component_depths"] = component_depths
    best["component_scores"] = component_scores
    return best


def detect_joints_from_ccl(caliper_df, joint_length=12.0, return_candidates=False):
    """Detect joint boundaries from a CCL (Casing Collar Locator) column.

    Finds peaks in the absolute CCL signal that correspond to collar/coupling
    positions, then returns depth intervals between consecutive peaks.  Each
    peak position is used as the separation point between two joints.

    Parameters
    ----------
    caliper_df : DataFrame
        Caliper log data with depth index.
    joint_length : float
        Expected joint length in metres (default 12 m).  Used to set the
        minimum distance between consecutive collar peaks (half the joint
        length to allow for some variation).
    return_candidates : bool
        If True, return (boundaries, candidates, depths, signal_values) tuple.
    """
    ccl_cols = [
        c
        for c in caliper_df.columns
        if re.search(r"CCL", c, re.IGNORECASE)
    ]
    if not ccl_cols:
        raise ValueError(
            "No CCL column found in caliper log data. "
            f"Available columns: {list(caliper_df.columns[:20])}"
        )

    ccl_signal = caliper_df[ccl_cols[0]].dropna()
    if len(ccl_signal) < 3:
        if return_candidates:
            return [], [], [], []
        return []

    depths = ccl_signal.index.values.astype(float)
    values = np.abs(ccl_signal.values.astype(float))

    depth_step = _estimate_depth_step(depths)
    min_distance = max(int(joint_length * 0.5 / depth_step), 3)

    prominence = max(np.std(values) * 1.5, np.median(values) * 0.5)
    if prominence <= 0:
        prominence = 1.0

    peaks, _ = find_peaks(values, distance=min_distance, prominence=prominence)

    if len(peaks) < 2:
        if return_candidates:
            candidates = [
                {"idx": int(p), "depth": float(depths[p]), "kind": "ccl_peak",
                 "score": float(values[p])}
                for p in peaks
            ]
            return [], candidates, depths.tolist(), values.tolist()
        return []

    candidates = [
        {"idx": int(p), "depth": float(depths[p]), "kind": "ccl_peak",
         "score": float(values[p])}
        for p in peaks
    ]

    joint_boundaries = []
    for i in range(len(peaks) - 1):
        joint_boundaries.append((depths[peaks[i]], depths[peaks[i + 1]]))

    if return_candidates:
        return joint_boundaries, candidates, depths.tolist(), values.tolist()

    return joint_boundaries


def detect_joints_from_log_markers(
    caliper_df,
    max_col,
    min_col,
    avg_col,
    joint_length=12.0,
    min_joint_length=1.0,
    min_marker_score=100.0,
    min_gradient_score=10.0,
    return_candidates=False,
):
    """Detect joint boundaries from caliper average-column markers.

    The average caliper curve contains two useful marker types:

    * short collar/coupling spikes in the high-pass average curve;
    * sharp casing-size changes in the smoothed first derivative.

    The detector builds both candidate sets, merges detections that point to
    the same physical boundary, and validates the resulting spacing.  Normal
    joints are expected around ``joint_length`` metres, but short accessories
    down to ``min_joint_length`` metres are allowed when the marker is strong.

    Parameters
    ----------
    caliper_df : DataFrame
        Caliper log data with depth index.
    max_col, min_col, avg_col : str
        Column names for the max, min, and average summary curves.  The
        average curve drives candidate detection; max/min confirm and refine
        sustained size-change steps when available.
    joint_length : float
        Expected joint length in metres (default 12 m).  Used as the normal
        spacing prior during candidate validation.
    min_joint_length : float
        Shortest expected accessory/sub-joint interval in metres.  Boundaries
        closer than roughly 60% of this are treated as duplicate detections.
    min_marker_score : float
        Minimum spike score kept after raw peak detection.
    min_gradient_score : float
        Minimum gradient score kept after raw gradient detection.
    """
    if avg_col not in caliper_df.columns:
        raise ValueError(
            f"Average column '{avg_col}' not found in caliper data. "
            f"Available: {list(caliper_df.columns[:20])}"
        )

    avg_series = (
        pd.to_numeric(caliper_df[avg_col], errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if len(avg_series) < 5:
        if return_candidates:
            return [], [], [], []
        return []

    depths = avg_series.index.values.astype(float)
    avg_values = avg_series.values.astype(float)
    depth_step = _estimate_depth_step(depths)
    min_joint_length = max(float(min_joint_length), depth_step)
    joint_length = max(float(joint_length), min_joint_length)

    summary_values = {"avg": avg_values}
    max_values = _aligned_summary_values(caliper_df, max_col, avg_series.index)
    min_values = _aligned_summary_values(caliper_df, min_col, avg_series.index)
    if max_values is not None:
        summary_values["max"] = max_values
    if min_values is not None:
        summary_values["min"] = min_values

    min_distance_m = max(min_joint_length * 0.15, 0.10)
    min_distance = max(int(round(min_distance_m / depth_step)), 1)
    spike_candidates = []
    gradient_candidates = []

    # High-pass collar/coupling spikes.  The baseline window is intentionally
    # wider than a collar but shorter than broad log drift.
    baseline_window_m = max(joint_length * 0.75, min_joint_length * 4.0)
    baseline_window = _odd_window_samples(
        baseline_window_m, depth_step, len(avg_values), min_samples=3
    )
    baseline = _rolling_median(avg_values, baseline_window)
    spike_signal = avg_values - baseline
    abs_spike_signal = np.abs(spike_signal)

    spike_noise = _robust_sigma(np.diff(spike_signal))
    if spike_noise <= 0:
        spike_noise = _robust_sigma(abs_spike_signal)
    if spike_noise > 0:
        spike_threshold = max(spike_noise * 5.0, 1e-6)
    else:
        spike_threshold = max(
            np.nanpercentile(abs_spike_signal, 95) * 0.3,
            1e-6,
        )
    max_spike_width_m = min(
        1.5,
        max(joint_length * 0.2, min_joint_length * 1.5),
    )
    max_spike_width = max(int(round(max_spike_width_m / depth_step)), 1)

    spike_peaks, spike_properties = find_peaks(
        abs_spike_signal,
        distance=min_distance,
        height=spike_threshold,
        prominence=spike_threshold,
        width=(None, max_spike_width),
    )
    spike_prominences = spike_properties.get(
        "prominences",
        np.zeros(len(spike_peaks)),
    )
    for peak_idx, prominence in zip(spike_peaks, spike_prominences):
        spike_candidates.append(
            {
                "idx": int(peak_idx),
                "depth": float(depths[peak_idx]),
                "score": float(prominence / max(spike_noise, 1e-12)),
                "kind": "spike",
            }
        )

    for edge_idx in (0, len(abs_spike_signal) - 1):
        edge_value = abs_spike_signal[edge_idx]
        if edge_value >= spike_threshold:
            spike_candidates.append(
                {
                    "idx": int(edge_idx),
                    "depth": float(depths[edge_idx]),
                    "score": float(edge_value / max(spike_noise, 1e-12)),
                    "kind": "edge_spike",
                }
            )

    # Casing-size or large-ID changes.  A short median smooth suppresses
    # finger noise while preserving sharp steps.
    smooth_window_m = min(
        max(depth_step * 5.0, 0.25),
        max(min_joint_length * 0.5, 0.25),
    )
    smooth_window = _odd_window_samples(
        smooth_window_m,
        depth_step,
        len(avg_values),
        3,
    )
    smoothed_curves = {
        name: _rolling_median(values, smooth_window)
        for name, values in summary_values.items()
    }
    smoothed = smoothed_curves["avg"]
    gradient = np.gradient(smoothed, depths)
    abs_gradient = np.abs(gradient)

    gradient_noise = _robust_sigma(gradient)
    if gradient_noise > 0:
        gradient_threshold = max(
            gradient_noise * 8.0,
            np.nanpercentile(abs_gradient, 99) * 0.25,
            1e-6,
        )
    else:
        gradient_threshold = max(
            np.nanpercentile(abs_gradient, 99) * 0.3,
            1e-6,
        )
    step_peaks, step_properties = find_peaks(
        abs_gradient,
        distance=min_distance,
        height=gradient_threshold,
        prominence=gradient_threshold,
    )
    step_prominences = step_properties.get(
        "prominences",
        np.zeros(len(step_peaks)),
    )
    for peak_idx, prominence in zip(step_peaks, step_prominences):
        gradient_candidates.append(
            {
                "idx": int(peak_idx),
                "depth": float(depths[peak_idx]),
                "score": float(prominence / max(gradient_noise, 1e-12)),
                "kind": "gradient",
            }
        )

    for edge_idx in (0, len(abs_gradient) - 1):
        edge_value = abs_gradient[edge_idx]
        if edge_value >= gradient_threshold:
            gradient_candidates.append(
                {
                    "idx": int(edge_idx),
                    "depth": float(depths[edge_idx]),
                    "score": float(edge_value / max(gradient_noise, 1e-12)),
                    "kind": "edge_gradient",
                }
            )

    if not spike_candidates and not gradient_candidates:
        if return_candidates:
            return [], [], depths.tolist(), avg_values.tolist()
        return []

    merge_distance_m = min(max(depth_step * 2.0, 0.02), 0.05)
    spike_candidates = [
        candidate
        for candidate in spike_candidates
        if candidate["score"] >= min_marker_score
    ]
    gradient_candidates = [
        candidate
        for candidate in gradient_candidates
        if candidate["score"] >= min_gradient_score
    ]
    candidates = _merge_marker_candidates(
        spike_candidates + gradient_candidates,
        merge_distance_m,
    )

    if len(candidates) < 2:
        if return_candidates:
            return [], candidates, depths.tolist(), avg_values.tolist()
        return []

    logger.info(
        "Log-markers detection: avg_col=%s, spike_peaks=%d, "
        "gradient_peaks=%d, "
        "selected_boundaries=%d.",
        avg_col,
        len(spike_peaks),
        len(step_peaks),
        len(candidates),
    )
    for i, candidate in enumerate(candidates):
        components = ", ".join(
            f"{name}@{depth:.2f}/s={candidate['component_scores'][name]:.0f}"
            for name, depth in candidate.get("component_depths", {}).items()
        )
        if not components:
            components = "-"
        logger.info(
            "  Boundary %d at depth %.2f m  |  kind=%s  |  "
            "score=%.2f  |  components=%s",
            i,
            candidate["depth"],
            candidate["kind"],
            candidate["score"],
            components,
        )

    joint_boundaries = []
    for i in range(len(candidates) - 1):
        top = candidates[i]["depth"]
        bottom = candidates[i + 1]["depth"]
        joint_boundaries.append({
            "top": top,
            "bottom": bottom,
            "length": bottom - top,
            "top_kind": candidates[i].get("kind", ""),
            "bottom_kind": candidates[i + 1].get("kind", ""),
        })

    if return_candidates:
        return joint_boundaries, candidates, depths.tolist(), avg_values.tolist()

    return joint_boundaries


def _joint_length(joint):
    """Return the length of a detected joint (dict or tuple)."""
    if isinstance(joint, dict):
        if "length" in joint:
            return float(joint["length"])
        return abs(float(joint["bottom"]) - float(joint["top"]))
    return abs(float(joint[1]) - float(joint[0]))


def _tally_length(entry):
    """Return the length of a tally entry from TopMD/BottomMD."""
    return abs(float(entry["BottomMD"]) - float(entry["TopMD"]))


def _tally_lengths_are_uniform(tal_len, cv_threshold=0.05):
    """Return True if tally lengths are too uniform for fingerprint matching.

    Uses coefficient of variation (std / mean).  A CV below *cv_threshold*
    means almost all joints are the same length and the fingerprint is flat.
    """
    if len(tal_len) < 2:
        return True
    arr = np.asarray(tal_len, dtype=float)
    mean = arr.mean()
    if mean == 0:
        return True
    return float(arr.std() / mean) < cv_threshold


_DP_MATCH = "match"
_DP_MERGE = "merge"
_DP_SPLIT = "split"
_DP_SKIP = "skip"


def _dp_align_joints(det_len, tal_len, merge_penalty=0.1, split_penalty=0.1,
                     skip_penalty=0.5, max_merge_width=5,
                     max_merge_error=0.20, max_split_error=0.30,
                     max_match_error=0.50):
    """Align detected joint lengths to tally lengths via dynamic programming.

    Allows 1:1 matches (capped at *max_match_error*), N:1 merges up to
    *max_merge_width* (extra boundaries in detection, capped at
    *max_merge_error* normalised error and rejected when the dominant segment
    alone is a better match), 1:2 splits (missed boundary, capped at
    *max_split_error*), and skipping detected joints (noise).

    The tally can be longer than detected (log starts/ends in the middle) --
    starting and trailing tally entries are free to skip.

    Returns a list of operation tuples:
        ("match", det_idx, tal_idx, cost)
        ("merge", (det_idx_a, ..., det_idx_z), tal_idx, cost)
        ("split", det_idx, (tal_idx_a, tal_idx_b), cost)
        ("skip", det_idx, None, cost)
    """
    n = len(det_len)
    m = len(tal_len)
    INF = 1e18

    dp = np.full((n + 1, m + 1), INF, dtype=float)
    # Free start: can begin matching at any tally position
    dp[0, :] = 0.0

    # Backtrace: store (operation, source_i, source_j[, width]) per cell
    bt = [[None] * (m + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        for j in range(0, m + 1):
            # Skip detected joint i-1 (noise)
            skip_cost = dp[i - 1, j] + skip_penalty
            if skip_cost < dp[i, j]:
                dp[i, j] = skip_cost
                bt[i][j] = (_DP_SKIP, i - 1, j)

            if j < 1:
                continue

            # 1:1 match: det[i-1] <-> tal[j-1]
            safe_t = tal_len[j - 1] if tal_len[j - 1] > 0 else 1e-9
            cost_11 = abs(det_len[i - 1] - tal_len[j - 1]) / safe_t
            if cost_11 <= max_match_error:
                val_11 = dp[i - 1, j - 1] + cost_11
                if val_11 < dp[i, j]:
                    dp[i, j] = val_11
                    bt[i][j] = (_DP_MATCH, i - 1, j - 1)

            # N:1 merge: det[i-w]..det[i-1] <-> tal[j-1] (extra boundaries)
            for w in range(2, max_merge_width + 1):
                if i < w:
                    break
                seg_slice = det_len[i - w : i]
                merged_len = float(np.sum(seg_slice))
                merge_err = abs(merged_len - tal_len[j - 1]) / safe_t
                if merge_err > max_merge_error:
                    continue
                # Reject if the dominant segment alone is a better match
                # and the merge error is non-trivial (>5%).
                best_single = abs(float(np.max(seg_slice)) - tal_len[j - 1]) / safe_t
                if best_single < merge_err and merge_err > 0.05:
                    continue
                cost_w1 = merge_err + (w - 1) * merge_penalty
                val_w1 = dp[i - w, j - 1] + cost_w1
                if val_w1 < dp[i, j]:
                    dp[i, j] = val_w1
                    bt[i][j] = (_DP_MERGE, i - w, j - 1, w)

            # 1:2 split: det[i-1] <-> tal[j-2]+tal[j-1] (missed boundary)
            if j >= 2:
                combined_tal = tal_len[j - 2] + tal_len[j - 1]
                safe_ct = combined_tal if combined_tal > 0 else 1e-9
                split_err = abs(det_len[i - 1] - combined_tal) / safe_ct
                if split_err <= max_split_error:
                    cost_12 = split_err + split_penalty
                    val_12 = dp[i - 1, j - 2] + cost_12
                    if val_12 < dp[i, j]:
                        dp[i, j] = val_12
                        bt[i][j] = (_DP_SPLIT, i - 1, j - 2)

    # Find best ending column (free end: remaining tally entries unmatched)
    best_j = int(np.argmin(dp[n, :]))
    total_cost = dp[n, best_j]

    # Backtrace
    ops = []
    ci, cj = n, best_j
    while ci > 0:
        entry = bt[ci][cj]
        if entry is None:
            break
        op = entry[0]
        prev_i, prev_j = entry[1], entry[2]

        if op == _DP_MATCH:
            det_idx = ci - 1
            tal_idx = cj - 1
            safe_t = tal_len[tal_idx] if tal_len[tal_idx] > 0 else 1e-9
            err = abs(det_len[det_idx] - tal_len[tal_idx]) / safe_t
            ops.append((_DP_MATCH, det_idx, tal_idx, err))
            ci, cj = prev_i, prev_j

        elif op == _DP_MERGE:
            width = entry[3]
            det_indices = tuple(range(ci - width, ci))
            tal_idx = cj - 1
            merged_len = float(np.sum(det_len[list(det_indices)]))
            safe_t = tal_len[tal_idx] if tal_len[tal_idx] > 0 else 1e-9
            err = abs(merged_len - tal_len[tal_idx]) / safe_t
            ops.append((_DP_MERGE, det_indices, tal_idx, err))
            ci, cj = prev_i, prev_j

        elif op == _DP_SPLIT:
            det_idx = ci - 1
            tal_idx_a = cj - 2
            tal_idx_b = cj - 1
            combined_tal = tal_len[tal_idx_a] + tal_len[tal_idx_b]
            safe_ct = combined_tal if combined_tal > 0 else 1e-9
            err = abs(det_len[det_idx] - combined_tal) / safe_ct
            ops.append((_DP_SPLIT, det_idx, (tal_idx_a, tal_idx_b), err))
            ci, cj = prev_i, prev_j

        elif op == _DP_SKIP:
            det_idx = ci - 1
            ops.append((_DP_SKIP, det_idx, None, skip_penalty))
            ci, cj = prev_i, prev_j
        else:
            break

    ops.reverse()
    return ops, total_cost


def match_joints_to_tally(
    detected_joints, well_tally, *, length_tol=0.3, overlap_penalty=0.1,
    merge_penalty=0.1, split_penalty=0.1, skip_penalty=0.5,
    max_merge_width=5, max_merge_error=0.20,
    max_split_error=0.30, max_match_error=0.50,
    qa_log_file=None,
):
    """Match detected joint boundaries to well tally entries by length fingerprint.

    Uses a sliding-window approach first (fast, O(N*M)).  If the residual
    exceeds *length_tol*, a dynamic-programming alignment is run that can
    handle extra boundaries (N:1 merge up to *max_merge_width*, capped at
    *max_merge_error*), missed boundaries (1:2 split, capped at
    *max_split_error*), and noise (skip detected joints).

    Parameters
    ----------
    detected_joints : list[dict | tuple]
        Each entry is a dict with ``top``, ``bottom``, ``length`` (from
        ``candidates_to_joint_boundaries``) or a ``(top, bottom)`` tuple.
    well_tally : list[dict]
        Tally entries with at least ``TopMD``, ``BottomMD``, ``ID``, ``OD``.
    length_tol : float
        Mean normalised length error above which the DP path is triggered
        and/or a warning is logged.
    overlap_penalty : float
        Weight applied to penalise low-overlap alignments in the sliding
        window so that it prefers offsets that match more detected joints.
    merge_penalty : float
        DP penalty for merging two detected joints into one tally entry.
    split_penalty : float
        DP penalty for splitting one detected joint across two tally entries.
    skip_penalty : float
        DP penalty for skipping a detected joint (treating it as noise).

    Returns
    -------
    list[tuple[dict|tuple, dict, float]]
        ``(joint_boundary, tally_entry, match_error)`` triples for the best
        alignment.  *match_error* is the normalised length difference (0.0 =
        perfect match, 0.1 = 10 % length mismatch).  For merged entries the
        boundary dict has a ``"merged": True`` flag and combined depth range.
    """
    if not detected_joints or not well_tally:
        return []

    n_det = len(detected_joints)
    n_tal = len(well_tally)

    det_len = np.array([_joint_length(j) for j in detected_joints], dtype=float)
    tal_len = np.array([_tally_length(e) for e in well_tally], dtype=float)

    # --- Single detected joint: match to closest tally length, break ties
    #     by absolute depth proximity. ----------------------------------------
    if n_det == 1:
        length_diffs = np.abs(tal_len - det_len[0])
        best_idx = int(np.argmin(length_diffs))

        similar_mask = length_diffs <= (length_diffs[best_idx] + 1e-6)
        if similar_mask.sum() > 1:
            det_top = float(
                detected_joints[0]["top"]
                if isinstance(detected_joints[0], dict)
                else detected_joints[0][0]
            )
            tal_tops = np.array(
                [float(well_tally[i]["TopMD"]) for i in range(n_tal)]
            )
            depth_diffs = np.abs(tal_tops - det_top)
            depth_diffs[~similar_mask] = np.inf
            best_idx = int(np.argmin(depth_diffs))

        logger.info(
            "Joint-tally match (single joint): matched to tally index %d "
            "(det_len=%.2f m, tal_len=%.2f m, diff=%.2f%%).",
            best_idx,
            det_len[0],
            tal_len[best_idx],
            100 * length_diffs[best_idx] / max(tal_len[best_idx], 1e-9),
        )
        single_error = float(length_diffs[best_idx] / max(tal_len[best_idx], 1e-9))
        return [(detected_joints[0], well_tally[best_idx], single_error)]

    # --- Uniform-length fallback: if the tally fingerprint is flat, use
    #     absolute depth proximity instead. ------------------------------------
    if _tally_lengths_are_uniform(tal_len):
        det_top = float(
            detected_joints[0]["top"]
            if isinstance(detected_joints[0], dict)
            else detected_joints[0][0]
        )
        tal_tops = np.array([float(e["TopMD"]) for e in well_tally], dtype=float)
        best_k = int(np.argmin(np.abs(tal_tops - det_top)))
        n_overlap = min(n_det, n_tal - best_k)

        logger.warning(
            "Joint-tally match: tally lengths are nearly uniform — "
            "falling back to depth-proximity alignment (offset=%d, overlap=%d).",
            best_k,
            n_overlap,
        )
        fallback_safe = np.where(tal_len[best_k : best_k + n_overlap] > 0,
                                  tal_len[best_k : best_k + n_overlap], 1e-9)
        fallback_err = np.abs(
            det_len[:n_overlap] - tal_len[best_k : best_k + n_overlap]
        ) / fallback_safe
        return [
            (detected_joints[i], well_tally[best_k + i], float(fallback_err[i]))
            for i in range(n_overlap)
        ]

    # --- Length-fingerprint sliding window ------------------------------------
    best_k = 0
    best_cost = np.inf

    for k in range(n_tal):
        n_overlap = min(n_det, n_tal - k)
        if n_overlap < 1:
            break

        safe_tal = np.where(tal_len[k : k + n_overlap] > 0,
                            tal_len[k : k + n_overlap], 1e-9)
        norm_diff = np.abs(det_len[:n_overlap] - tal_len[k : k + n_overlap]) / safe_tal
        mean_cost = float(norm_diff.mean())

        adjusted = mean_cost + overlap_penalty * (1.0 - n_overlap / n_det)

        if adjusted < best_cost:
            best_cost = adjusted
            best_k = k

    n_overlap = min(n_det, n_tal - best_k)
    safe_tal = np.where(tal_len[best_k : best_k + n_overlap] > 0,
                        tal_len[best_k : best_k + n_overlap], 1e-9)
    residuals = np.abs(
        det_len[:n_overlap] - tal_len[best_k : best_k + n_overlap]
    ) / safe_tal
    mean_residual = float(residuals.mean())
    max_residual = float(residuals.max()) if len(residuals) > 0 else 0.0
    n_outliers = int((residuals > length_tol).sum())

    # Trigger DP if:
    #   - mean error exceeds threshold, OR
    #   - any individual joint has error > threshold (local insertion/deletion), OR
    #   - detected count differs from tally count (possible extra/missed boundaries)
    needs_dp = (
        mean_residual > length_tol
        or n_outliers > 0
        or n_det != n_tal
    )

    # --- If sliding-window is good enough, return directly ---------------------
    if not needs_dp:
        logger.info(
            "Joint-tally match (sliding-window): offset=%d, overlap=%d/%d "
            "detected, mean length error=%.1f%%.",
            best_k,
            n_overlap,
            n_det,
            100 * mean_residual,
        )
        return [
            (detected_joints[i], well_tally[best_k + i], float(residuals[i]))
            for i in range(n_overlap)
        ]

    # --- Sliding-window has issues — run DP alignment -------------------------
    trigger_reasons = []
    if mean_residual > length_tol:
        trigger_reasons.append(f"mean_error={100*mean_residual:.1f}%")
    if n_outliers > 0:
        trigger_reasons.append(
            f"{n_outliers} joints with error>{100*length_tol:.0f}% "
            f"(max={100*max_residual:.1f}%)"
        )
    if n_det != n_tal:
        trigger_reasons.append(f"count mismatch (detected={n_det}, tally={n_tal})")

    logger.info(
        "Joint-tally match: sliding-window offset=%d — triggering DP (%s).",
        best_k,
        "; ".join(trigger_reasons),
    )

    ops, dp_cost = _dp_align_joints(
        det_len, tal_len,
        merge_penalty=merge_penalty,
        split_penalty=split_penalty,
        skip_penalty=skip_penalty,
        max_merge_width=max_merge_width,
        max_merge_error=max_merge_error,
        max_split_error=max_split_error,
        max_match_error=max_match_error,
    )

    # Convert DP operations to the standard output format
    result = []
    n_matches = 0
    n_merges = 0
    n_splits = 0
    n_skips = 0

    for op_type, det_idx, tal_idx, err in ops:
        if op_type == _DP_MATCH:
            result.append((detected_joints[det_idx], well_tally[tal_idx], err))
            n_matches += 1

        elif op_type == _DP_MERGE:
            indices = det_idx
            first = detected_joints[indices[0]]
            last = detected_joints[indices[-1]]
            top = float(first["top"] if isinstance(first, dict) else first[0])
            bot = float(last["bottom"] if isinstance(last, dict) else last[1])
            merged_length = sum(_joint_length(detected_joints[k]) for k in indices)
            merged_boundary = {
                "top": top,
                "bottom": bot,
                "length": merged_length,
                "merged": True,
                "merged_from": list(indices),
            }
            result.append((merged_boundary, well_tally[tal_idx], err))
            n_merges += 1

        elif op_type == _DP_SPLIT:
            tal_a, tal_b = tal_idx
            result.append((
                detected_joints[det_idx],
                well_tally[tal_a],
                err,
            ))
            n_splits += 1

        elif op_type == _DP_SKIP:
            n_skips += 1

    # --- DP logging -----------------------------------------------------------
    logger.info(
        "Joint-tally match (DP): %d matches, %d merges, %d splits, "
        "%d skipped. Total DP cost=%.3f.",
        n_matches,
        n_merges,
        n_splits,
        n_skips,
        dp_cost,
    )

    for op_type, det_idx, tal_idx, err in ops:
        if op_type == _DP_MERGE:
            indices = det_idx
            parts = "+".join(f"[{k}]" for k in indices)
            lens = "+".join(f"{det_len[k]:.2f}" for k in indices)
            total = sum(det_len[k] for k in indices)
            logger.info(
                "  MERGE: detected%s (%s=%.2f m) -> "
                "tally[%d] (%.2f m), error=%.1f%%.",
                parts, lens, total,
                tal_idx,
                tal_len[tal_idx],
                100 * err,
            )
        elif op_type == _DP_SPLIT:
            tal_a, tal_b = tal_idx
            logger.info(
                "  SPLIT: detected[%d] (%.2f m) -> tally[%d]+[%d] "
                "(%.2f+%.2f=%.2f m), error=%.1f%%.",
                det_idx,
                det_len[det_idx],
                tal_a, tal_b,
                tal_len[tal_a], tal_len[tal_b],
                tal_len[tal_a] + tal_len[tal_b],
                100 * err,
            )
        elif op_type == _DP_SKIP:
            logger.info(
                "  SKIP: detected[%d] (%.2f m) — no tally match.",
                det_idx,
                det_len[det_idx],
            )
        elif err > length_tol:
            logger.info(
                "  MATCH: detected[%d] (%.2f m) -> tally[%d] (%.2f m), "
                "error=%.1f%% (high).",
                det_idx,
                det_len[det_idx],
                tal_idx,
                tal_len[tal_idx],
                100 * err,
            )

    # --- QA JSON log ----------------------------------------------------------
    if qa_log_file is not None:
        qa_entries = []
        for op_type, det_idx, tal_idx, err in ops:
            entry = {"operation": op_type, "error_pct": round(100 * err, 2)}
            if op_type == _DP_MATCH:
                entry["detected_idx"] = det_idx
                entry["detected_length_m"] = round(float(det_len[det_idx]), 3)
                entry["tally_idx"] = tal_idx
                entry["tally_length_m"] = round(float(tal_len[tal_idx]), 3)
            elif op_type == _DP_MERGE:
                indices = det_idx
                entry["detected_indices"] = list(indices)
                entry["detected_lengths_m"] = [
                    round(float(det_len[k]), 3) for k in indices
                ]
                entry["merged_length_m"] = round(
                    sum(float(det_len[k]) for k in indices), 3
                )
                entry["tally_idx"] = tal_idx
                entry["tally_length_m"] = round(float(tal_len[tal_idx]), 3)
            elif op_type == _DP_SPLIT:
                tal_a, tal_b = tal_idx
                entry["detected_idx"] = det_idx
                entry["detected_length_m"] = round(float(det_len[det_idx]), 3)
                entry["tally_indices"] = [tal_a, tal_b]
                entry["tally_lengths_m"] = [
                    round(float(tal_len[tal_a]), 3),
                    round(float(tal_len[tal_b]), 3),
                ]
            elif op_type == _DP_SKIP:
                entry["detected_idx"] = det_idx
                entry["detected_length_m"] = round(float(det_len[det_idx]), 3)
            qa_entries.append(entry)

        qa_log = {
            "timestamp": datetime.now().isoformat(),
            "n_detected": int(len(det_len)),
            "n_tally": int(len(tal_len)),
            "dp_cost": round(float(dp_cost), 4),
            "summary": {
                "matches": n_matches,
                "merges": n_merges,
                "splits": n_splits,
                "skips": n_skips,
            },
            "operations": qa_entries,
        }
        try:
            Path(qa_log_file).parent.mkdir(parents=True, exist_ok=True)
            with open(qa_log_file, "w", encoding="utf-8") as f:
                json.dump(qa_log, f, indent=2, ensure_ascii=False)
            logger.info("QA log written to %s", qa_log_file)
        except OSError as exc:
            logger.warning("Could not write QA log to %s: %s", qa_log_file, exc)

    return result


def _estimate_joint_length_from_tally(well_tally, default=12.0):
    """Estimate expected joint length from tally depths."""
    lengths = []
    for joint in well_tally:
        try:
            top = float(joint["TopMD"])
            bottom = float(joint["BottomMD"])
        except (KeyError, TypeError, ValueError):
            continue

        length = abs(bottom - top)
        if np.isfinite(length) and length > 0:
            lengths.append(length)

    if not lengths:
        return default
    return float(np.median(lengths))


# ---------------------------------------------------------------------------
# Joint detection (standalone)
# ---------------------------------------------------------------------------


def detect_joints(uploaded_logs, well_tally, detection_params=None):
    """Detect raw boundary candidates for each uploaded log (QA/QC step).

    Returns a list (one entry per log) of dicts, each containing:

    * ``method``      -- detection method (``'ccl'``, ``'log_markers'``, or ``'tally'``)
    * ``candidates``  -- list of raw candidate dicts with ``depth``, ``kind``,
                         ``score``, ``idx``
    * ``chart_depths``  -- depth array for plotting the caliper curve
    * ``chart_values``  -- signal array (avg caliper or CCL) for plotting
    * ``joint_boundaries`` -- derived boundaries [(top, bottom), ...] for preview

    The candidates are the raw boundary markers **before** matching to tally.
    The user reviews/excludes candidates; approved ones are later converted to
    boundaries in ``process_caliper_logs``.

    Parameters
    ----------
    detection_params : list[dict] | None
        Per-log detection parameters (parallel to ``uploaded_logs["data"]``).
        Recognised keys: ``min_marker_score``, ``min_gradient_score``.
    """
    if detection_params is None:
        detection_params = []
    all_log_results = []

    if len(uploaded_logs) == 0:
        return all_log_results

    for log_idx, caliper_log_data in enumerate(uploaded_logs["data"]):
        joint_marker = _get_log_metadata(uploaded_logs, "joint_identification_marker", log_idx)
        max_col = _get_log_metadata(uploaded_logs, "max_column_name", log_idx)
        min_col = _get_log_metadata(uploaded_logs, "min_column_name", log_idx)
        avg_col = _get_log_metadata(uploaded_logs, "average_column_name", log_idx)

        log_params = detection_params[log_idx] if log_idx < len(detection_params) else {}
        marker_lower = (joint_marker or "").strip().lower()

        if marker_lower == "ccl":
            boundaries, candidates, chart_depths, chart_values = detect_joints_from_ccl(
                caliper_log_data, return_candidates=True
            )
            method = "ccl"

        elif marker_lower in ("log_markers", "log markers", "logmarkers"):
            if not avg_col:
                raise ValueError(
                    "Log-markers joint identification requires "
                    "average_column_name to be set."
                )
            expected_joint_length = _estimate_joint_length_from_tally(well_tally)
            extra_kw = {}
            if "min_marker_score" in log_params:
                extra_kw["min_marker_score"] = float(log_params["min_marker_score"])
            if "min_gradient_score" in log_params:
                extra_kw["min_gradient_score"] = float(log_params["min_gradient_score"])
            boundaries, candidates, chart_depths, chart_values = detect_joints_from_log_markers(
                caliper_log_data,
                max_col,
                min_col,
                avg_col,
                joint_length=expected_joint_length,
                return_candidates=True,
                **extra_kw,
            )
            method = "log_markers"

        else:
            method = "tally"
            candidates = [
                {"idx": i, "depth": float(joint["TopMD"]), "kind": "tally",
                 "score": 0.0}
                for i, joint in enumerate(well_tally)
            ]
            boundaries = [
                (joint["TopMD"], joint["BottomMD"])
                for joint in well_tally
            ]
            chart_depths = []
            chart_values = []

        serializable_candidates = []
        for c in candidates:
            serializable_candidates.append({
                "idx": int(c.get("idx", 0)),
                "depth": float(c["depth"]),
                "kind": str(c.get("kind", "")),
                "score": float(c.get("score", 0)),
            })

        all_log_results.append({
            "method": method,
            "candidates": serializable_candidates,
            "chart_depths": chart_depths,
            "chart_values": chart_values,
            "joint_boundaries": [
                (float(b["top"]), float(b["bottom"])) if isinstance(b, dict)
                else (float(b[0]), float(b[1]))
                for b in boundaries
            ],
        })

    return all_log_results


def candidates_to_joint_boundaries(candidates):
    """Convert approved candidate dicts to joint boundary records.

    Each joint spans consecutive candidate depths (sorted by ``depth``).
    Returns dicts with ``top`` and ``bottom`` [m], ``length`` = bottom − top,
    and ``top_kind`` / ``bottom_kind`` from the boundary candidates.

    This is what the user's QA/QC approval produces before passing to
    ``process_caliper_logs``.
    """
    if len(candidates) < 2:
        return []
    sorted_cands = sorted(candidates, key=lambda c: c["depth"])
    out = []
    for i in range(len(sorted_cands) - 1):
        top = float(sorted_cands[i]["depth"])
        bottom = float(sorted_cands[i + 1]["depth"])
        out.append({
            "top": top,
            "bottom": bottom,
            "length": bottom - top,
            "top_kind": sorted_cands[i].get("kind", ""),
            "bottom_kind": sorted_cands[i + 1].get("kind", ""),
        })
    return out


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------


def process_caliper_logs(uploaded_logs, well_tally, approved_joints=None,
                         qa_log_dir=None):
    """Build processed caliper logs for each uploaded log.

    Parameters
    ----------
    uploaded_logs : dict
        Structure with ``"data"`` list of DataFrames and parallel metadata lists.
    well_tally : list[dict]
        Well tally entries with at least TopMD, BottomMD, ID, OD.
    approved_joints : list[list[dict]] or None
        Optional pre-approved candidate list (one list per log).  Each entry is
        a list of candidate dicts with at least ``depth``.  These are converted
        to joint boundary dicts (``top``, ``bottom``, ``length``) via
        ``candidates_to_joint_boundaries`` and then matched to tally.
    qa_log_dir : str or Path or None
        Directory to write per-log QA JSON files for joint-to-tally matching.
        Files are named ``<log_name>_qa_match.json``.
    """
    processed_logs = []

    if len(uploaded_logs) == 0:
        return processed_logs

    for log_idx, caliper_log_data in enumerate(uploaded_logs["data"]):
        finger_name = _get_log_metadata(uploaded_logs, "finger_name", log_idx)
        finger_units = _get_log_metadata(uploaded_logs, "finger_units", log_idx)

        finger_prefix = finger_name if finger_name else "D"
        finger_regex = rf"^{re.escape(finger_prefix)}\d{{1,2}}$"

        # --- Determine joint boundaries -----------------------------------
        qa_file = None
        if qa_log_dir is not None:
            log_names = uploaded_logs.get("name", [])
            log_label = (
                log_names[log_idx] if log_idx < len(log_names) else f"log_{log_idx}"
            )
            safe_label = re.sub(r"[^\w\-.]", "_", str(log_label))
            qa_file = str(Path(qa_log_dir) / f"{safe_label}_qa_match.json")

        # Build a lookup from tally entry identity to its 1-based position
        _tally_pos_map = {id(e): i + 1 for i, e in enumerate(well_tally)}

        if (
            approved_joints is not None
            and log_idx < len(approved_joints)
            and approved_joints[log_idx] is not None
        ):
            approved_cands = approved_joints[log_idx]
            detected = candidates_to_joint_boundaries(approved_cands)
            matched = match_joints_to_tally(
                detected, well_tally, qa_log_file=qa_file,
            )
            joints_info = [
                {
                    "top": bd["top"],
                    "bottom": bd["bottom"],
                    "length": bd["length"],
                    "tally": tally_entry,
                    "match_error": match_err,
                    "tally_seq": _tally_pos_map.get(id(tally_entry), idx + 1),
                }
                for idx, (bd, tally_entry, match_err) in enumerate(matched)
            ]
        else:
            joints_info = [
                {
                    "top": float(entry["TopMD"]),
                    "bottom": float(entry["BottomMD"]),
                    "length": abs(
                        float(entry["BottomMD"]) - float(entry["TopMD"])
                    ),
                    "tally": entry,
                    "match_error": 0.0,
                    "tally_seq": i + 1,
                }
                for i, entry in enumerate(well_tally)
            ]

        # --- Process each joint -------------------------------------------
        n_joints = len(joints_info)
        joint_labels = [
            ji["tally"].get("Joint", str(i + 1)) for i, ji in enumerate(joints_info)
        ]
        tally_seq_labels = [ji["tally_seq"] for ji in joints_info]
        df = pd.DataFrame(
            {
                "Seq. No.": range(1, n_joints + 1),
                "Tally Seq. No.": tally_seq_labels,
                "Tally Joint No.": joint_labels,
            },
            index=range(n_joints),
        )
        processed_log = add_corrosion_columns(df)

        log_radii = caliper_log_data.filter(regex=finger_regex)
        if not log_radii.empty and log_radii.shape[1] > 0:
            units = (finger_units or "").strip()
            if units in ("double_radius", "diameter"):
                log_radii = log_radii / 2
        else:
            log_radii = None

        depth_step = (
            _estimate_depth_step(log_radii.index.values.astype(float))
            if log_radii is not None and len(log_radii) > 1
            else 1.0
        )

        for joint_nr, ji in enumerate(joints_info):
            try:
                if log_radii is None or log_radii.shape[1] == 0:
                    continue

                joint_radii = log_radii.loc[ji["top"] : ji["bottom"]]
                if joint_radii.empty:
                    continue

                # Adaptive spike exclusion: trim connection-spike influence
                top_excl, bot_excl = _compute_spike_exclusion_zone(
                    joint_radii, depth_step
                )
                trimmed_top = ji["top"] + top_excl
                trimmed_bot = ji["bottom"] - bot_excl
                joint_radii_clean = joint_radii.loc[trimmed_top:trimmed_bot]

                if joint_radii_clean.empty or len(joint_radii_clean) < 3:
                    joint_radii_clean = joint_radii

                logger.debug(
                    "Joint %d (%.2f–%.2f m): spike exclusion "
                    "top=%.3f m, bot=%.3f m, rows %d -> %d.",
                    joint_nr, ji["top"], ji["bottom"],
                    top_excl, bot_excl,
                    len(joint_radii), len(joint_radii_clean),
                )

                mean_radius = joint_radii_clean.mean().mean()
                max_radius = joint_radii_clean.max().max()
                min_radius = joint_radii_clean.min().min()

                max_cal_loc = joint_radii_clean.stack().idxmax()[0]
                min_cal_loc = joint_radii_clean.stack().idxmin()[0]

                tally_entry = ji["tally"]
                nominal_ir = tally_entry["ID"] / 2
                nominal_or = tally_entry["OD"] / 2

                n_fingers = joint_radii_clean.shape[1]

                max_penetration = (
                    100 * (max_radius - nominal_ir) / (nominal_or - nominal_ir)
                )

                max_circ_wall_loss = (
                    100
                    / n_fingers
                    * (
                        (joint_radii_clean**2 - nominal_ir**2)
                        / (nominal_or**2 - nominal_ir**2)
                    ).sum(axis=1)
                ).mean()

                remaining_wall_thickness = nominal_or - max_radius

                max_pen_row = joint_radii_clean.loc[max_cal_loc]
                row_mean_at_max = float(max_pen_row.mean())
                max_ovality = (
                    float(max_pen_row.max() - max_pen_row.min())
                    / row_mean_at_max * 100
                    if row_mean_at_max > 0 else 0.0
                )

                result_values = {
                    "Top Depth [m]": np.round(trimmed_top, 3),
                    "Bottom Depth [m]": np.round(trimmed_bot, 3),
                    "Length [m]": np.round(trimmed_bot - trimmed_top, 3),
                    "Nominal IR [inch]": np.round(nominal_ir, 3),
                    "Nominal OR [inch]": np.round(nominal_or, 3),
                    "Max. Penetration Depth [m]": max_cal_loc,
                    "Min. Penetration Depth [m]": min_cal_loc,
                    "Max. Penetration [%]": np.round(max_penetration, 1),
                    "Max. Wall Loss [%]": np.round(max_circ_wall_loss, 1),
                    "Max. Radius [inch]": max_radius,
                    "Min. Radius [inch]": min_radius,
                    "Mean. Radius [inch]": np.round(mean_radius, 3),
                    "Remaining wall thickness [inch]": np.round(
                        remaining_wall_thickness, 3
                    ),
                    "Ovality [%]": np.round(max_ovality, 1),
                    "Match Error [%]": np.round(
                        ji.get("match_error", 0.0) * 100, 1
                    ),
                }
                processed_log.loc[joint_nr, list(result_values.keys())] = list(
                    result_values.values()
                )
            except (KeyError, IndexError, ValueError):
                continue

        processed_logs.append(processed_log.copy())

    return processed_logs


def _get_sorted_logs(uploaded_logs, processed_logs):
    unsorted_logs = list(
        zip(
            uploaded_logs["name"],
            uploaded_logs["date"],
            uploaded_logs["data"],
            processed_logs,
        )
    )
    return sorted(unsorted_logs, key=lambda x: datetime.strptime(x[1], "%H-%M-%S %d-%m-%Y"))


def get_measured_corrosion_rate_from_logs(
    well_tally, logs_metadata, selected_log_names, processed_logs, start_time
):
    """Compute measured corrosion rate and corroded thickness from processed logs.

    Parameters
    ----------
    well_tally : list[dict]
        Well tally entries with at least ``ID``, ``OD``, and ``Joint``.
    logs_metadata : dict
        Per-log metadata dict (from ``logs_information.json``).  Keys are log
        names; values are dicts with ``"date"`` (YYYY-MM-DD) and optionally
        ``"is_baseline"`` (bool).
    selected_log_names : list[str]
        Ordered list of log names corresponding 1:1 to *processed_logs*.
    processed_logs : list[DataFrame]
        Processed log DataFrames (same order as *selected_log_names*).
    start_time : str
        Fallback baseline date (``"%Y-%m-%d %H:%M:%S"``), used when no log is
        marked as baseline.

    Baseline selection:
    - If a log is marked ``is_baseline`` in *logs_metadata*, that log's
      processed measurements are used as the baseline (time-zero reference).
    - Else, if at least two logs exist, the earliest log is used as the
      baseline so corrosion is measured forward from a real survey.
    - Otherwise (a single unmarked log), the baseline inner radius is the
      nominal inner radius adjusted for -12.5% wall thickness (API
      manufacturing tolerance): ``baseline_ir = (OD - 0.875 * (OD - ID)) / 2``
      per joint.

    Bore quantities are inner *radii*, so ``Corroded [mm]`` is a one-sided
    (radial) wall loss -- matching the DLD model output, which is a one-sided
    penetration rate.

    Returns a DataFrame with ``'Joint No.'`` and, for each interval, both a
    ``'Corrosion rate [mm/year] (date1 -> date2)'`` column and a
    ``'Corroded [mm] (date1 -> date2)'`` column.  Both are *signed* (later
    survey minus earlier): positive means the inner radius grew (metal loss /
    corrosion); negative means the bore shrank (scale/deposit, or tool /
    calibration differences between surveys).
    """
    n_tally = len(well_tally)
    n_logs = len(processed_logs)

    # -- initialise result DataFrame ----------------------------------------
    joint_labels = [e.get("Joint", str(i + 1)) for i, e in enumerate(well_tally)]
    result_df = pd.DataFrame(
        joint_labels,
        index=range(n_tally),
        columns=["Joint No."],
    )

    if n_logs == 0:
        result_df[WALL_THICKNESS_CHANGE_RATE_PREFIX] = np.nan
        result_df[WALL_THICKNESS_CHANGE_PREFIX] = np.nan
        return result_df

    # -- build sorted entries from logs_metadata and processed_logs ---------
    entries = []
    for idx, log_name in enumerate(selected_log_names):
        meta = logs_metadata.get(log_name, {})
        date_str = (meta.get("date") or "").strip()
        if not date_str:
            continue
        is_baseline = bool(meta.get("is_baseline", False))
        entries.append((log_name, date_str, processed_logs[idx], is_baseline))

    fmt_date = "%Y-%m-%d"
    sorted_entries = sorted(entries, key=lambda x: datetime.strptime(x[1], fmt_date))

    if not sorted_entries:
        result_df[WALL_THICKNESS_CHANGE_RATE_PREFIX] = np.nan
        result_df[WALL_THICKNESS_CHANGE_PREFIX] = np.nan
        return result_df

    # -- determine baseline source ------------------------------------------
    baseline_log_idx = None
    for idx, entry in enumerate(sorted_entries):
        if entry[3]:
            baseline_log_idx = idx
            break

    # No log is explicitly flagged as baseline: when at least two logs exist,
    # promote the earliest one (the pipe at its youngest, least-corroded state)
    # to baseline so corrosion is measured forward from a real survey instead of
    # the nominal ID.  A single unmarked log has no later survey to compare, so
    # it still falls back to the nominal-ID reference below.
    if baseline_log_idx is None and len(sorted_entries) >= 2:
        baseline_log_idx = 0

    if baseline_log_idx is not None:
        baseline_log_df = sorted_entries[baseline_log_idx][2]
        baseline_date = datetime.strptime(sorted_entries[baseline_log_idx][1], fmt_date)
        n_base = min(n_tally, len(baseline_log_df))
        # Inner *radius* in mm (one-sided): max radius [inch] -> mm.
        baseline_ir_mm = np.array(
            baseline_log_df["Max. Radius [inch]"].iloc[:n_base].astype(float) * 25.4
        )
        comparison_logs = sorted_entries[baseline_log_idx + 1:]
    else:
        # No usable baseline log: use nominal inner radius at -12.5% wall.
        # baseline_id = OD - 0.875 * (OD - ID) = 0.125 * OD + 0.875 * ID
        # baseline_ir = baseline_id / 2  (inner *radius*).
        od_inch = np.array([row["OD"] for row in well_tally], dtype=float)
        id_inch = np.array([row["ID"] for row in well_tally], dtype=float)
        baseline_ir_mm = (0.125 * od_inch + 0.875 * id_inch) / 2.0 * 25.4
        baseline_date = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        n_base = n_tally
        comparison_logs = sorted_entries

    if len(comparison_logs) == 0:
        return result_df

    # -- baseline to first comparison log -----------------------------------
    _, first_date_str, first_log_df, _ = comparison_logs[0]
    first_date = datetime.strptime(first_date_str, fmt_date)

    n_first = min(n_base, n_tally, len(first_log_df))
    # Inner *radius* in mm (one-sided): max radius [inch] -> mm.
    first_log_ir_mm = np.array(
        first_log_df["Max. Radius [inch]"].iloc[:n_first].astype(float) * 25.4
    )

    # Skip the baseline->first interval when it has zero (or negative) width.
    # With no dedicated baseline log the fallback baseline date equals the
    # earliest log's date, so this interval would otherwise emit a meaningless
    # "(date -> same date)" column.  The first log still becomes the reference
    # for the log-to-log intervals below.
    duration_days = (first_date - baseline_date).total_seconds() / 86400
    if duration_days > 0:
        # Signed bore change (later minus baseline): positive = inner radius
        # grew = metal loss (corrosion); negative = bore shrank (scale/deposit
        # or tool/calibration differences between surveys).
        corroded_mm = first_log_ir_mm - baseline_ir_mm[:n_first]
        rate_mm_yr = (corroded_mm * 365.0 / duration_days).round(5)

        start_str = baseline_date.strftime("%Y-%m-%d")
        end_str = first_date.strftime("%Y-%m-%d")
        rate_col = wall_thickness_change_rate_col(start_str, end_str)
        corroded_col = wall_thickness_change_col(start_str, end_str)

        rate_values = np.full(n_tally, np.nan, dtype=float)
        rate_values[:n_first] = np.asarray(rate_mm_yr).flat[:n_first]
        result_df[rate_col] = rate_values

        corroded_values = np.full(n_tally, np.nan, dtype=float)
        corroded_values[:n_first] = np.asarray(corroded_mm).flat[:n_first]
        result_df[corroded_col] = corroded_values

    if len(comparison_logs) == 1:
        return result_df

    # -- log-to-log intervals -----------------------------------------------
    prev_date = first_date
    prev_log_df = first_log_df

    for i in range(1, len(comparison_logs)):
        _, current_date_str, current_log_df, _ = comparison_logs[i]
        current_date = datetime.strptime(current_date_str, fmt_date)

        interval_duration_days = (current_date - prev_date).total_seconds() / 86400
        if interval_duration_days <= 0:
            # zero/negative-width interval (duplicate date) -> skip the column,
            # but keep the later log as the reference for the next interval.
            prev_date = current_date
            prev_log_df = current_log_df
            continue

        n_use = min(n_tally, len(prev_log_df), len(current_log_df))
        # Inner *radii* in mm (one-sided): max radius [inch] -> mm.
        prev_ir_mm = (
            prev_log_df["Max. Radius [inch]"].iloc[:n_use].astype(float) * 25.4
        ).values
        current_ir_mm = (
            current_log_df["Max. Radius [inch]"].iloc[:n_use].astype(float) * 25.4
        ).values

        # Signed bore change (later minus earlier); see baseline interval above.
        corroded_mm = current_ir_mm - prev_ir_mm
        rate_mm_yr = (corroded_mm * 365.0 / interval_duration_days).round(5)

        start_str = prev_date.strftime("%Y-%m-%d")
        end_str = current_date.strftime("%Y-%m-%d")
        rate_col = wall_thickness_change_rate_col(start_str, end_str)
        corroded_col = wall_thickness_change_col(start_str, end_str)

        rate_values = np.full(n_tally, np.nan, dtype=float)
        rate_values[:n_use] = rate_mm_yr
        result_df[rate_col] = rate_values

        corroded_values = np.full(n_tally, np.nan, dtype=float)
        corroded_values[:n_use] = corroded_mm
        result_df[corroded_col] = corroded_values

        prev_date = current_date
        prev_log_df = current_log_df

    return result_df


def get_remaining_thickness_at_log_dates(well_tally, uploaded_logs, processed_logs):
    """Compute remaining wall thickness [mm] at each log date.

    Uses the deepest pit (``Max. Radius``) as the inner radius, so the reported
    wall is the worst-case (thinnest) remaining wall.  This matches the
    prediction path and the measured corrosion rate, which both key off
    ``Max. Radius``; using ``Min. Radius`` here would mix a best-case wall with
    a worst-case rate in the remaining-life projection.
    """
    n_logs = len(processed_logs)
    if n_logs == 0:
        return None

    sorted_logs = _get_sorted_logs(uploaded_logs, processed_logs)
    n_tally = len(well_tally)
    od_nominal = np.array([row.get("OD") for row in well_tally], dtype=float)

    joint_labels = [e.get("Joint", str(i + 1)) for i, e in enumerate(well_tally)]
    remaining = pd.DataFrame(
        joint_labels,
        index=range(n_tally),
        columns=["Joint No."],
    )
    inch_to_mm = 25.4
    fmt_log = "%H-%M-%S %d-%m-%Y"
    for _log_name, log_date_str, _log_data, log_df in sorted_logs:
        log_date = datetime.strptime(log_date_str, fmt_log)
        n_use = min(n_tally, len(log_df))
        # Deepest pit -> largest inner radius -> thinnest (worst-case) wall.
        max_radius_inch = log_df["Max. Radius [inch]"].iloc[:n_use].astype(float).values
        # One-sided wall: nominal outer radius (OD/2) - inner radius [inch].
        remaining_thickness_inch = od_nominal[:n_use] / 2.0 - max_radius_inch
        remaining_thickness_mm = np.full(n_tally, np.nan, dtype=float)
        remaining_thickness_mm[:n_use] = (remaining_thickness_inch * inch_to_mm).flat[:n_use]
        col_name = f"Remaining thickness [mm] ({log_date.strftime('%Y-%m-%d')})"
        remaining[col_name] = np.round(remaining_thickness_mm, 3)

    return remaining


def get_remaining_days_to_min_thickness(
    well_tally, measured, remaining, min_remaining_thickness_mm,
):
    """Compute remaining days until remaining thickness reaches a minimum."""
    if measured is None or remaining is None or remaining.empty:
        return None

    try:
        min_mm = float(min_remaining_thickness_mm)
    except (TypeError, ValueError):
        return None

    n_tally = len(well_tally)

    rate_cols = [
        c
        for c in measured.columns
        if c != "Joint No." and c.startswith(WALL_THICKNESS_CHANGE_RATE_PREFIX)
    ]
    date_end_re = re.compile(r"->\s*(\d{4}-\d{2}-\d{2})\s*\)?$")
    latest_rate_col = None
    latest_rate_date = None
    for c in rate_cols:
        m = date_end_re.search(c)
        if m:
            try:
                dt = datetime.strptime(m.group(1).strip(), "%Y-%m-%d")
                if latest_rate_date is None or dt >= latest_rate_date:
                    latest_rate_date = dt
                    latest_rate_col = c
            except ValueError:
                pass
    if latest_rate_col is None and rate_cols:
        latest_rate_col = rate_cols[-1]

    thick_cols = [
        c
        for c in remaining.columns
        if c != "Joint No." and c.startswith("Remaining thickness [mm]")
    ]
    date_re = re.compile(r"\((\d{4}-\d{2}-\d{2})\)\s*$")
    latest_thick_col = None
    latest_thick_date = None
    for c in thick_cols:
        m = date_re.search(c)
        if m:
            try:
                dt = datetime.strptime(m.group(1), "%Y-%m-%d")
                if latest_thick_date is None or dt >= latest_thick_date:
                    latest_thick_date = dt
                    latest_thick_col = c
            except ValueError:
                pass
    if latest_thick_col is None and thick_cols:
        latest_thick_col = thick_cols[-1]

    if latest_rate_col is None or latest_thick_col is None:
        return None

    rate_mm_per_year = np.asarray(measured[latest_rate_col], dtype=float)
    remaining_mm = np.asarray(remaining[latest_thick_col], dtype=float)
    n_use = min(n_tally, len(rate_mm_per_year), len(remaining_mm))

    days_per_year = 365.25
    days_arr = np.full(n_tally, np.nan, dtype=float)
    for i in range(n_use):
        t_cur = remaining_mm[i]
        r = rate_mm_per_year[i]
        if np.isnan(t_cur) or np.isnan(r):
            continue
        if t_cur <= min_mm:
            days_arr[i] = 0.0
            continue
        if r <= 0 or not np.isfinite(r):
            days_arr[i] = np.inf
            continue
        thickness_to_lose = t_cur - min_mm
        days_arr[i] = (thickness_to_lose / r) * days_per_year

    joint_labels = [e.get("Joint", str(i + 1)) for i, e in enumerate(well_tally)]
    return pd.DataFrame(
        {
            "Joint No.": joint_labels,
            "Remaining days to min. thickness [days]": days_arr,
        },
        index=range(n_tally),
    )
