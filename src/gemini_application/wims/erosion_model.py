"""Erosion analysis application for WIMS."""

import json
import os
from datetime import datetime, timezone

import numpy as np
import pytz

from gemini_application.application_abstract import ApplicationAbstract
from gemini_application.wims.erosion_from_prod_data import compute_erosion_for_segments
from gemini_application.wims.erosion_from_tally import (
    default_esp_geometry_template,
    get_production_casing_id_inch,
    resolve_production_tubing_id_inch,
    segments_from_tally,
)

tzobject = pytz.timezone("Europe/Amsterdam")

ESP_GEOMETRY_FILENAME = "esp_geometry.json"


class ErosionApplication(ApplicationAbstract):
    """Forward erosion calculation from well tally geometry and production data."""

    def init_parameters(self, initial_parameters=None):
        """Load well tally into inputs when available."""
        if initial_parameters:
            self.parameters.update(initial_parameters)
        well_tally = self._get_tally_from_well_parameters()
        if well_tally:
            self.inputs["well_tally"] = well_tally

    def calculate(self):
        """No-op; erosion workflow uses calculate_erosion()."""
        pass

    def _get_well_type(self):
        """Return 'productionwell' or 'injectionwell'."""
        try:
            ut = self.unit.parameters.get("type")
            if ut == "production_well":
                return "productionwell"
            if ut == "injection_well":
                return "injectionwell"
        except (KeyError, TypeError):
            pass
        if "production" in self.unit.name.lower():
            return "productionwell"
        if "injection" in self.unit.name.lower():
            return "injectionwell"
        return "productionwell"

    def _get_tally_from_well_parameters(self):
        """Get well tally from unit parameters (app builder)."""
        well_type = self._get_well_type()
        key = f"{well_type}_tally_table"
        prop = self.unit.parameters.get("property") or {}
        table = prop.get(key)
        if table is not None and len(table) > 0:
            first = table[0]
            if isinstance(first, list):
                if first:
                    return list(first)
            else:
                return list(table)
        if key in self.unit.parameters and self.unit.parameters[key]:
            tbl = self.unit.parameters[key]
            if isinstance(tbl, list) and tbl:
                first = tbl[0]
                if isinstance(first, list) and first:
                    return list(first)
                return list(tbl)
        return None

    def _get_esp_depth_m(self):
        """ESP setting depth [m] from linked ESP unit, or None."""
        for u in getattr(self.unit, "to_units", []):
            if "esp" in u.name.lower():
                prop = u.parameters.get("property") or {}
                depths = prop.get("esp_depth")
                if depths:
                    return float(depths[0])
        return None

    def _well_data_folder(self):
        project_folder = os.path.join(self.plant.project_path, self.plant.name + "/wims_data")
        return os.path.join(project_folder, self.unit.name)

    def esp_geometry_path(self):
        """Path to per-well ESP geometry JSON."""
        return os.path.join(self._well_data_folder(), ESP_GEOMETRY_FILENAME)

    def load_esp_geometry(self):
        """Load ESP geometry from disk or return default template."""
        path = self.esp_geometry_path()
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        return default_esp_geometry_template()

    def save_esp_geometry(self, geometry):
        """Write ESP geometry JSON for the current well."""
        os.makedirs(self._well_data_folder(), exist_ok=True)
        with open(self.esp_geometry_path(), "w") as f:
            json.dump(geometry, f, indent=2)

    def resolve_esp_setting_depth_m(self, esp_geometry):
        """Resolve ESP setting depth from geometry override or plant ESP unit."""
        override = esp_geometry.get("setting_depth_m")
        if override is not None and float(override) > 0:
            return float(override)
        esp_depth = self._get_esp_depth_m()
        if esp_depth is None:
            raise ValueError(
                "ESP setting depth not found. Set esp_depth on the ESP unit "
                "or setting_depth_m in esp_geometry.json."
            )
        return float(esp_depth)

    def get_production_data(self):
        """Read flow, pressure, temperature from internal database."""
        well_type = self._get_well_type()

        start_time = datetime.strptime(self.inputs["start_time"], "%Y-%m-%d %H:%M:%S")
        start_time = tzobject.localize(start_time)
        start_time = start_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        end_time = datetime.strptime(self.inputs["end_time"], "%Y-%m-%d %H:%M:%S")
        end_time = tzobject.localize(end_time)
        end_time = end_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        timestep = 3600

        if well_type == "productionwell":
            if not getattr(self.unit, "to_units", None) or len(self.unit.to_units) == 0:
                raise ValueError("Production well has no linked ESP unit.")
            flow_tag = "esp_flow.measured"
            pressure_tag = "esp_inlet_pressure.measured"
            temperature_tag = "esp_inlet_temperature.measured"
            asset_name = self.unit.to_units[0].name
        else:
            flow_tag = f"{well_type}_flow.measured"
            pressure_tag = f"{well_type}_wellhead_pressure.measured"
            temperature_tag = f"{well_type}_wellhead_temperature.measured"
            asset_name = self.unit.name

        try:
            result, time = self.plant.database.read_internal_database(
                self.unit.plant.name,
                asset_name,
                flow_tag,
                start_time,
                end_time,
                timestep,
            )
            self.inputs["flow"] = np.array(result)
            self.inputs["time"] = np.array(time)

            result, time = self.plant.database.read_internal_database(
                self.unit.plant.name,
                asset_name,
                pressure_tag,
                start_time,
                end_time,
                timestep,
            )
            self.inputs["pressure"] = np.array(result)

            result, time = self.plant.database.read_internal_database(
                self.unit.plant.name,
                asset_name,
                temperature_tag,
                start_time,
                end_time,
                timestep,
            )
            self.inputs["temperature"] = np.array(result)
        except Exception:
            pass

    def build_segments(self, esp_geometry=None, tubing_id_inch=None):
        """Build erosion flow-path segments from well tally and ESP geometry."""
        well_tally = self._get_tally_from_well_parameters()
        if not well_tally:
            raise ValueError("No well tally found in Well Parameters (app builder).")
        self.inputs["well_tally"] = well_tally

        well_type = self._get_well_type()
        esp_setting_depth_m = None

        if well_type == "productionwell":
            if esp_geometry is None:
                esp_geometry = self.load_esp_geometry()
            esp_setting_depth_m = self.resolve_esp_setting_depth_m(esp_geometry)

        segments = segments_from_tally(
            well_tally,
            well_type,
            esp_setting_depth_m=esp_setting_depth_m,
            esp_geometry=esp_geometry,
            tubing_id_inch=tubing_id_inch,
        )
        return segments, well_type, esp_setting_depth_m

    def get_production_geometry_from_tally(self, esp_geometry=None):
        """Return tally-derived production casing and tubing IDs [inch]."""
        well_tally = self._get_tally_from_well_parameters()
        if not well_tally:
            raise ValueError("No well tally found in Well Parameters (app builder).")
        if esp_geometry is None:
            esp_geometry = self.load_esp_geometry()
        setting_m = self.resolve_esp_setting_depth_m(esp_geometry)
        return {
            "production_casing_id_inch": get_production_casing_id_inch(well_tally, setting_m),
            "production_tubing_id_inch": resolve_production_tubing_id_inch(
                well_tally, setting_m, esp_geometry=esp_geometry
            ),
        }

    def calculate_erosion(
        self,
        erosion_model,
        erosion_params,
        esp_geometry=None,
        tubing_id_inch=None,
    ):
        """Run forward erosion calculation and store results in outputs."""
        segments, well_type, esp_depth_m = self.build_segments(
            esp_geometry=esp_geometry,
            tubing_id_inch=tubing_id_inch,
        )

        self.get_production_data()
        flow = self.inputs.get("flow")
        if flow is None or len(flow) == 0:
            raise ValueError("No production flow data for the selected time window.")

        segment_results, summary = compute_erosion_for_segments(
            segments,
            flow,
            erosion_model,
            erosion_params,
            well_type=well_type,
        )

        self.outputs["status"] = "ok"
        self.outputs["well_type"] = well_type
        self.outputs["esp_depth_m"] = esp_depth_m
        self.outputs["segments"] = segment_results
        self.outputs["summary"] = summary
        return self.outputs
