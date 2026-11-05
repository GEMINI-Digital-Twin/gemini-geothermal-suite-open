"""Compact design specification: the only design object the LLM edits.

About fifteen fields describe a complete heating & cooling plant. Validation
messages are written to be actionable by a small LLM (they say what to change).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

ECON_PATH = Path(__file__).resolve().parents[1] / "data" / "economics_assumptions.yaml"


class DesignSpec(BaseModel):
    """Geothermal heating & cooling plant design (screening + verification input)."""

    well_depth_m: float = Field(2500.0, ge=1500.0, le=4000.0, description="Reservoir midpoint TVD")
    n_doublets: int = Field(2, ge=1, le=3)
    max_flow_m3h: float = Field(300.0, ge=50.0, le=300.0, description="Per doublet")
    dh_return_temperature_c: float = Field(50.0, ge=30.0, le=70.0)
    hex_approach_k: float = Field(3.0, ge=1.0, le=10.0, description="HEX design approach")
    heat_pump_mw: float = Field(0.0, ge=0.0, le=40.0, description="HP thermal output capacity")
    absorption_chiller_mw: float = Field(0.0, ge=0.0, le=20.0, description="Cooling capacity")
    electric_chiller_mw: float = Field(0.0, ge=0.0, le=20.0, description="Cooling capacity")
    backup_boiler_mw: float = Field(0.0, ge=0.0, le=40.0)
    backup_fuel: Literal["gas", "electric"] = "gas"
    gas_handling: Literal["separate_and_burn", "keep_in_solution_reinject"] = "separate_and_burn"
    maintenance_start_days: list[int] | Literal["auto"] = "auto"
    cooling_supply_temperature_c: float = 20.0
    heating_supply_temperature_c: float = 100.0

    @field_validator("maintenance_start_days")
    @classmethod
    def _days_ok(cls, v):
        if v != "auto" and any(not (0 <= d <= 364) for d in v):
            raise ValueError("maintenance_start_days must be day indices 0-364 or 'auto'")
        return v

    @model_validator(mode="after")
    def _consistency(self):
        if (
            self.maintenance_start_days != "auto"
            and len(self.maintenance_start_days) != self.n_doublets
        ):
            raise ValueError(
                f"maintenance_start_days needs one start day per doublet "
                f"({self.n_doublets}); got {len(self.maintenance_start_days)}. Use 'auto' to let "
                f"the scheduler choose."
            )
        return self

    def key(self) -> str:
        """Stable short hash (cache key / design ID)."""
        return hashlib.sha1(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()[:10]

    def label(self) -> str:
        """Human-readable one-liner."""
        parts = [
            f"{self.n_doublets}x doublet @ {self.well_depth_m:.0f} m (<= "
            f"{self.max_flow_m3h:.0f} m3/h)"
        ]
        if self.heat_pump_mw:
            parts.append(f"HP {self.heat_pump_mw:g} MW")
        if self.absorption_chiller_mw:
            parts.append(f"AbsCh {self.absorption_chiller_mw:g} MW")
        if self.electric_chiller_mw:
            parts.append(f"ElCh {self.electric_chiller_mw:g} MW")
        if self.backup_boiler_mw:
            parts.append(f"{self.backup_fuel} boiler {self.backup_boiler_mw:g} MW")
        parts.append(
            f"DH {self.heating_supply_temperature_c:.0f}/{self.dh_return_temperature_c:.0f} C"
        )
        parts.append("gas reinjected" if self.gas_handling.startswith("keep") else "gas burned")
        return ", ".join(parts)


def _num(v):
    """Coerce numeric-looking strings (YAML 1.1 parses '2.0e6' as str) to float."""
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return v
    return v


def load_economics(path: str | Path | None = None) -> dict:
    """Economic/technology assumptions as {name: value} plus the raw annotated tree."""
    with open(path or ECON_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    flat = {k: _num(v["value"]) for section in raw.values() for k, v in section.items()}
    return {"values": flat, "raw": raw}
