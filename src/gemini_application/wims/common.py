"""Shared helpers for WIMS application workflows."""

from __future__ import annotations

from typing import Iterable

import numpy as np


def get_well_type(unit) -> str:
    """Return the canonical WIMS well type for a unit."""
    try:
        unit_type = unit.parameters.get("type")
        if unit_type == "production_well":
            return "productionwell"
        if unit_type == "injection_well":
            return "injectionwell"
    except (AttributeError, KeyError, TypeError):
        pass

    unit_name = getattr(unit, "name", "").lower()
    if "production" in unit_name:
        return "productionwell"
    if "injection" in unit_name:
        return "injectionwell"
    return "productionwell"


def get_tally_from_well_parameters(unit) -> list | None:
    """Return the latest tally table from a unit if available."""
    well_type = get_well_type(unit)
    key = f"{well_type}_tally_table"
    prop = (unit.parameters.get("property") or {}) if hasattr(unit, "parameters") else {}
    table = prop.get(key)
    if table is not None and len(table) > 0:
        first = table[0]
        if isinstance(first, list):
            return list(first) if first else None
        return list(table)

    if key in getattr(unit, "parameters", {}) and unit.parameters[key]:
        tbl = unit.parameters[key]
        if isinstance(tbl, list) and tbl:
            first = tbl[0]
            if isinstance(first, list) and first:
                return list(first)
            return list(tbl)
    return None


def get_esp_depth_m(unit):
    """Return the ESP setting depth in meters if a linked ESP is present."""
    for linked_unit in getattr(unit, "to_units", []):
        if "esp" in getattr(linked_unit, "name", "").lower():
            prop = linked_unit.parameters.get("property") or {}
            depths = prop.get("esp_depth")
            if depths:
                return float(depths[0])
    return None


def get_esp_joint_start_idx(well_tally: Iterable, esp_depth_m):
    """Return the first tally index at or below the ESP setting depth."""
    if esp_depth_m is None:
        return 0

    for idx, entry in enumerate(well_tally):
        if float(entry["TopMD"]) >= esp_depth_m:
            return idx
    return len(well_tally)


def build_trajectory_geometry(well_traj):
    """Build section arrays from a trajectory table."""
    length = []
    diameter = []
    angle = []
    roughness = []

    for ii in range(1, len(well_traj)):
        md = well_traj[ii]["MD"] - well_traj[ii - 1]["MD"]
        tvd = well_traj[ii]["TVD"] - well_traj[ii - 1]["TVD"]
        length.append(md)
        diameter.append(well_traj[ii]["ID"])
        angle.append((np.round(90 - np.arccos(tvd / md) * 180 / np.pi, 2)) * np.pi / 180)
        roughness.append(well_traj[ii]["roughness"])

    return {
        "length": length,
        "diameter": diameter,
        "angle": angle,
        "roughness": roughness,
    }
