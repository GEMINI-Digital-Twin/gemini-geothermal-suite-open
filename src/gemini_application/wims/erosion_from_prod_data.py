"""Erosion rate estimation from production / injection flow data."""

import math

import numpy as np

from gemini_model.erosion.correlation.API import ErosionAPI
from gemini_model.erosion.erosion_model import ErosionModel, is_velocity_model

MM_PER_M = 1000.0


def _representative_flow(flow_m3h, flow_stat="mean"):
    """Return representative flow [m3/h] from a time series."""
    arr = np.asarray(flow_m3h, dtype=float)
    if arr.size == 0:
        return 0.0
    if flow_stat == "max":
        return float(np.nanmax(arr))
    return float(np.nanmean(arr))


def build_correlation_input_base(flow_m3h, erosion_params):
    """Correlation input fields independent of per-segment geometry."""
    rho_fluid_kgm3 = float(erosion_params.get("rho_fluid_kgm3", 1000))

    return {
        "alpha": float(erosion_params.get("alpha_deg", 90)),
        "rho_fluid": rho_fluid_kgm3,
        "flowRate": float(flow_m3h),
        "Hv": float(erosion_params.get("Hv_gpa", 1.0)),
        "mater_particle": erosion_params.get("mater_particle", "SIO2"),
        "diameter_particle": float(erosion_params.get("diameter_particle_mm", 0.1)),
        "mater": erosion_params.get("mater", "steel"),
        "rho_pipe": float(erosion_params.get("rho_pipe_kgm3", 7800)),
        "fs": float(erosion_params.get("fs", 0.5)),
    }


def flow_velocity_ms(flow_m3h, diameter_m):
    """Actual flow velocity [m/s] from volumetric flow and effective diameter."""
    diameter_m = float(diameter_m)
    if diameter_m <= 0:
        return None
    flow_m3s = float(flow_m3h) / 3600.0
    area_m2 = math.pi * diameter_m ** 2 / 4.0
    if area_m2 <= 0:
        return None
    return flow_m3s / area_m2


def api_velocity_comparison(flow_velocity_ms, api_limit_velocity_ms):
    """Compare actual flow velocity to API erosion velocity limit."""
    if flow_velocity_ms is None or api_limit_velocity_ms is None:
        return {
            "velocity_ratio": None,
            "velocity_margin_ms": None,
            "exceeds_api_limit": None,
        }

    actual_ms = float(flow_velocity_ms)
    limit_ms = float(api_limit_velocity_ms)
    if limit_ms <= 0:
        return {
            "velocity_ratio": None,
            "velocity_margin_ms": None,
            "exceeds_api_limit": None,
        }

    return {
        "velocity_ratio": actual_ms / limit_ms,
        "velocity_margin_ms": limit_ms - actual_ms,
        "exceeds_api_limit": actual_ms > limit_ms,
    }


def _base_result_fields(segment, rep_flow_m3h, diameter_m):
    """Geometry/flow fields common to every segment result."""
    result = dict(segment)
    result["flow_m3h"] = rep_flow_m3h
    result["flow_diameter_mm"] = diameter_m * MM_PER_M
    result["outer_id_mm"] = (
        segment.get("outer_id_m") * MM_PER_M if segment.get("outer_id_m") else None
    )
    result["inner_od_mm"] = (
        segment.get("inner_od_m") * MM_PER_M if segment.get("inner_od_m") else None
    )
    result["flow_area_mm2"] = segment.get("flow_area_mm2")
    return result


def compute_erosion_for_segments(
    segments,
    flow_m3h,
    erosion_model_name,
    erosion_params,
    well_type=None,
):
    """Compute erosion for each flow-path segment."""
    flow_stat = erosion_params.get("flow_stat", "mean")
    rep_flow = _representative_flow(flow_m3h, flow_stat=flow_stat)

    model = ErosionModel()
    model.update_parameters({"erosion_model": erosion_model_name})

    is_api_model = is_velocity_model(erosion_model_name)
    api_limit_velocity_ms = None
    if is_api_model:
        api_limit_velocity_ms = ErosionAPI.calculate_erosion_velocity(
            float(erosion_params.get("rho_fluid_kgm3", 1000))
        )

    # -- constant correlation inputs (only diameter varies per segment) -----
    correlation_input_base = build_correlation_input_base(rep_flow, erosion_params)

    results = []
    max_rate = 0.0

    for segment in segments:
        diameter_m = float(segment.get("flow_diameter_m") or 0)
        if diameter_m <= 0:
            result = _base_result_fields(segment, rep_flow, diameter_m)
            result["erosion_rate_mm_yr"] = None
            result["erosion_velocity_ms"] = None
            result["warning"] = "Invalid flow diameter"
            results.append(result)
            continue

        actual_flow_velocity_ms = flow_velocity_ms(rep_flow, diameter_m)

        if is_api_model:
            rate = None
            velocity = actual_flow_velocity_ms
        else:
            u = dict(correlation_input_base)
            u["diameter"] = diameter_m
            model.calculate_output(u, {})
            out = model.get_output()
            rate = out.get("erosion_rate_mm_yr")
            velocity = out.get("erosion_velocity_ms")
            if rate is not None:
                max_rate = max(max_rate, float(rate))

        result = _base_result_fields(segment, rep_flow, diameter_m)
        result["flow_velocity_ms"] = actual_flow_velocity_ms
        result["erosion_rate_mm_yr"] = rate
        result["erosion_velocity_ms"] = velocity
        if is_api_model:
            result["api_erosion_limit_velocity_ms"] = api_limit_velocity_ms
            result.update(
                api_velocity_comparison(actual_flow_velocity_ms, api_limit_velocity_ms)
            )
        results.append(result)

    summary = {
        "max_erosion_rate_mm_yr": max_rate,
        "segment_count": len(results),
    }
    if is_api_model:
        summary["api_erosion_limit_velocity_ms"] = api_limit_velocity_ms
    summary.update(aggregate_erosion_by_joint(results, well_type=well_type))
    return results, summary


def _joint_row_from_segment(segment):
    """Extract per-joint erosion fields from a segment result."""
    return {
        "joint": segment.get("joint"),
        "joint_id_inch": segment.get("joint_id_inch"),
        "tubing_id_inch": segment.get("tubing_id_inch"),
        "below_esp_intake": segment.get("below_esp_intake"),
        "flow_area": segment.get("flow_area"),
        "flow_area_mm2": segment.get("flow_area_mm2"),
        "name": segment.get("name") or segment.get("component_name"),
        "component_type": segment.get("component_type"),
        "top_md_m": segment.get("top_md_m"),
        "bottom_md_m": segment.get("bottom_md_m"),
        "flow_diameter_mm": segment.get("flow_diameter_mm"),
        "flow_m3h": segment.get("flow_m3h"),
        "flow_velocity_ms": segment.get("flow_velocity_ms"),
        "api_erosion_limit_velocity_ms": segment.get("api_erosion_limit_velocity_ms"),
        "velocity_ratio": segment.get("velocity_ratio"),
        "velocity_margin_ms": segment.get("velocity_margin_ms"),
        "exceeds_api_limit": segment.get("exceeds_api_limit"),
        "erosion_rate_mm_yr": segment.get("erosion_rate_mm_yr"),
        "erosion_velocity_ms": segment.get("erosion_velocity_ms"),
        "segment_type": segment.get("segment_type"),
    }


def aggregate_erosion_by_joint(segment_results, well_type):
    """Build per-joint erosion summary for production and injection wells."""
    joints_below_esp_intake = []
    esp_annulus_segments = []
    tubing_above_esp_joints = []
    tubing_interior_rates_mm_yr = []
    tubing_interior_velocities_ms = []
    tubing_interior_flow_velocities_ms = []
    tubing_interior_segment_count = 0
    injection_joints = []

    for segment in segment_results:
        segment_type = segment.get("segment_type")
        rate_mm_yr = segment.get("erosion_rate_mm_yr")
        velocity_ms = segment.get("erosion_velocity_ms")
        flow_velocity_ms_val = segment.get("flow_velocity_ms")

        if well_type == "productionwell":
            if segment_type == "tubing_interior" and segment.get("below_esp_intake"):
                joints_below_esp_intake.append(_joint_row_from_segment(segment))
            elif segment_type == "esp_joint_annulus":
                esp_annulus_segments.append(_joint_row_from_segment(segment))
            elif segment_type == "tubing_interior":
                if segment.get("below_esp_intake"):
                    joints_below_esp_intake.append(_joint_row_from_segment(segment))
                else:
                    tubing_above_esp_joints.append(_joint_row_from_segment(segment))
                    tubing_interior_segment_count += 1
                    if rate_mm_yr is not None:
                        tubing_interior_rates_mm_yr.append(float(rate_mm_yr))
                    if velocity_ms is not None:
                        tubing_interior_velocities_ms.append(float(velocity_ms))
                    if flow_velocity_ms_val is not None:
                        tubing_interior_flow_velocities_ms.append(float(flow_velocity_ms_val))
        elif well_type == "injectionwell":
            if segment_type == "tubular_interior":
                injection_joints.append(_joint_row_from_segment(segment))

    summary = {}

    if well_type == "productionwell":
        summary["joints_below_esp_intake"] = joints_below_esp_intake
        summary["esp_annulus_segments"] = esp_annulus_segments
        summary["tubing_above_esp_joints"] = tubing_above_esp_joints
        below_rates_mm_yr = [
            row["erosion_rate_mm_yr"]
            for row in joints_below_esp_intake
            if row.get("erosion_rate_mm_yr") is not None
        ]
        below_flow_velocities_ms = [
            row["flow_velocity_ms"]
            for row in joints_below_esp_intake
            if row.get("flow_velocity_ms") is not None
        ]
        summary["max_erosion_below_esp_intake_mm_yr"] = (
            float(max(below_rates_mm_yr)) if below_rates_mm_yr else None
        )
        summary["max_flow_velocity_below_esp_intake_ms"] = (
            float(max(below_flow_velocities_ms)) if below_flow_velocities_ms else None
        )
        summary["joints_exceeding_api_limit_count"] = sum(
            1 for row in joints_below_esp_intake if row.get("exceeds_api_limit")
        ) + sum(
            1 for row in esp_annulus_segments if row.get("exceeds_api_limit")
        ) + sum(
            1 for row in tubing_above_esp_joints if row.get("exceeds_api_limit")
        )
        esp_flow_velocities_ms = [
            row["flow_velocity_ms"]
            for row in esp_annulus_segments
            if row.get("flow_velocity_ms") is not None
        ]
        summary["max_flow_velocity_esp_annulus_ms"] = (
            float(max(esp_flow_velocities_ms)) if esp_flow_velocities_ms else None
        )
        esp_rates_mm_yr = [
            row["erosion_rate_mm_yr"]
            for row in esp_annulus_segments
            if row.get("erosion_rate_mm_yr") is not None
        ]
        summary["max_erosion_esp_annulus_mm_yr"] = (
            float(max(esp_rates_mm_yr)) if esp_rates_mm_yr else None
        )
        summary["tubing_interior_segment_count"] = tubing_interior_segment_count
        summary["tubing_interior_average_mm_yr"] = (
            float(np.mean(tubing_interior_rates_mm_yr))
            if tubing_interior_rates_mm_yr
            else None
        )
        summary["tubing_interior_average_velocity_ms"] = (
            float(np.mean(tubing_interior_velocities_ms))
            if tubing_interior_velocities_ms
            else None
        )
        summary["tubing_interior_average_flow_velocity_ms"] = (
            float(np.mean(tubing_interior_flow_velocities_ms))
            if tubing_interior_flow_velocities_ms
            else None
        )
    elif well_type == "injectionwell":
        summary["injection_joints"] = injection_joints
        injection_rates_mm_yr = [
            row["erosion_rate_mm_yr"]
            for row in injection_joints
            if row.get("erosion_rate_mm_yr") is not None
        ]
        injection_flow_velocities_ms = [
            row["flow_velocity_ms"]
            for row in injection_joints
            if row.get("flow_velocity_ms") is not None
        ]
        summary["max_erosion_rate_mm_yr"] = (
            float(max(injection_rates_mm_yr)) if injection_rates_mm_yr else 0.0
        )
        summary["max_flow_velocity_ms"] = (
            float(max(injection_flow_velocities_ms)) if injection_flow_velocities_ms else None
        )
        summary["joints_exceeding_api_limit_count"] = sum(
            1 for row in injection_joints if row.get("exceeds_api_limit")
        )

    return summary
