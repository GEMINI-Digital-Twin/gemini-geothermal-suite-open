"""Borehole heat exchanger (BHE) geoloop subsurface model.

Wraps the external ``geoloop`` simulation package to model a (deep or
shallow) borehole heat exchanger loop. The model accumulates the input
history over time (required by the underlying solver) and returns the
resulting fluid and borehole-wall temperatures, extracted heat and pump
power for the current time step.
"""

from pathlib import Path

import numpy as np

from geoloop.bin.SingleRunSim import SingleRun, optimize_forkeys
from geoloop.configuration import LithologyConfig, SingleRunConfig, load_nested_config
from geoloop.lithology.process_lithology import ProcessLithologyToThermalConductivity

from gemini_model.model_abstract import DynamicModel


class BHEGeoloop(DynamicModel):
    """Borehole heat exchanger geoloop model.

    Input (``u``) keys
    -------------------
    mass_flow_rate : float
        Circulation mass flow rate [kg/s].
    inlet_temperature : float, optional
        Fluid inlet temperature [degC]. Required when the configured
        ``run_type`` is ``"TIN"``; otherwise an optional override of the
        configured default inlet temperature.
    heat_load / heat_demand : float, optional
        Requested heat load [W]. Required when the configured
        ``run_type`` is ``"POWER"``.

    Output (``y``) keys
    --------------------
    outlet_temperature, heat_extracted, pump_power, inlet_temperature,
    mass_flow_rate, mean_borehole_wall_temperature,
    fluid_temperature_depth(_axis), borehole_wall_temperature_depth(_axis)
    """

    def __init__(self):
        """Model initialization."""
        super().__init__()
        self.state = {}
        self._isample = -1
        self._single_run = None
        self._config = None

        script_dir = Path(__file__).parent

        # TODO: Do not use hard-coded path for json file. Instead, use a default config and allow user to pass in a config file path.
        self.parameters["json_file_path"] = str(script_dir / "input_files" / "bhe_config.json")
        self._load_json_parameters(self.parameters["json_file_path"])
        self._set_empty_output()

    def update_parameters(self, parameters):
        """Update model parameters before building the geoloop config.

        Parameters
        ----------
        parameters: dict
            Parameters dict as defined by the model. Nested dict values
            (e.g. ``litho_k_param``) are merged rather than replaced.
        """
        for key, value in parameters.items():
            if isinstance(value, dict) and isinstance(self.parameters.get(key), dict):
                self.parameters[key].update(value)
            else:
                self.parameters[key] = value

    def initialize_state(self, x):
        """Generate an initial state based on user parameters.

        Builds the geoloop configuration/solver and resets the
        accumulated input/output history.
        """
        x = x or {}
        self.state["step_index"] = x.get("step_index", 0)
        self.state["mass_flow_rate_hist"] = []
        self.state["inlet_temperature_hist"] = []
        self.state["heat_load_hist"] = []
        self.state["outlet_temperature_hist"] = []
        self.state["heat_extracted_hist"] = []
        self.state["pump_power_hist"] = []
        self._set_empty_output()
        self._build_single_run()
        return self.state

    def set_initial_state(self):
        """Reset accumulated history, e.g. to re-run the model from a clean state."""
        self.initialize_state({})

    def update_state(self, u, x):
        """Advance the model state based on input ``u`` and state ``x``.

        Appends the current input to the accumulated history and re-runs
        the geoloop simulation over the full history (required by the
        underlying solver), storing the resulting output.
        """
        if self._single_run is None:
            self.initialize_state(x)

        config = self._config
        run_type = config.run_type

        mass_flow_value = u.get("mass_flow_rate")
        if mass_flow_value is None:
            self._set_empty_output()
            return self.state

        if run_type == "TIN":
            inlet_temp_value = u.get("inlet_temperature")
            if inlet_temp_value is None:
                self._set_empty_output()
                return self.state
            heat_load_value = float(config.Q)
        elif run_type == "POWER":
            heat_load_input = u.get("heat_load", u.get("heat_demand"))
            if heat_load_input is None:
                self._set_empty_output()
                return self.state
            heat_load_value = float(heat_load_input)
            inlet_temp_value = float(u.get("inlet_temperature", config.Tin))
        else:
            raise ValueError(f"Unsupported geoloop run_type: {run_type}")

        self.state["mass_flow_rate_hist"].append(float(mass_flow_value))
        self.state["inlet_temperature_hist"].append(float(inlet_temp_value))
        self.state["heat_load_hist"].append(float(heat_load_value))

        history_count = len(self.state["mass_flow_rate_hist"])

        self._single_run = SingleRun.from_config(config)
        sim_params = self._single_run.sim_params
        sim_params.Nt = history_count
        # geoloop expects simulation time in seconds.
        sim_params.time = sim_params.dt * np.arange(1, history_count + 1)
        sim_params.tmax = sim_params.time[-1]
        sim_params.m_flow = np.asarray(self.state["mass_flow_rate_hist"], dtype=float)
        sim_params.Tin = np.asarray(self.state["inlet_temperature_hist"], dtype=float)
        sim_params.Q = np.asarray(self.state["heat_load_hist"], dtype=float)

        old_err = np.seterr()
        try:
            result = self._single_run.run(self._isample)
        finally:
            np.seterr(**old_err)

        if result is None:
            raise RuntimeError("Geoloop simulation returned no result")

        self.output = {
            "outlet_temperature": float(result.T_fo[-1]),
            "heat_extracted": float(result.Q_b[-1]),
            "pump_power": float(result.qloop[-1]),
            "inlet_temperature": float(result.T_fi[-1]),
            "mass_flow_rate": float(result.flowrate[-1]),
            "mean_borehole_wall_temperature": float(result.T_bave[-1]),
            "fluid_temperature_depth": np.asarray(result.T_f[-1], dtype=float),
            "fluid_temperature_depth_axis": np.asarray(result.z, dtype=float),
            "borehole_wall_temperature_depth": np.asarray(result.T_b[-1], dtype=float),
            "borehole_wall_temperature_depth_axis": np.asarray(result.zseg, dtype=float),
        }

        self.state["outlet_temperature_hist"].append(self.output["outlet_temperature"])
        self.state["heat_extracted_hist"].append(self.output["heat_extracted"])
        self.state["pump_power_hist"].append(self.output["pump_power"])
        self.state["step_index"] = self.state.get("step_index", 0) + 1

        return self.state

    def calculate_output(self, u, x=None):
        """Calculate output of the model for the current time step.

        Advances the model state (which runs the geoloop simulation using
        the accumulated input history) and stores the resulting output.
        """
        self.update_state(u, x if x is not None else self.state)

    def _build_single_run(self):
        """Build the geoloop configuration and solver from ``self.parameters``."""
        config = SingleRunConfig(**self.parameters)
        config.lithology_to_k = None

        if config.litho_k_param:
            config.litho_k_param["basecase"] = True
            lithology_to_k = ProcessLithologyToThermalConductivity.from_config(
                LithologyConfig(**config.litho_k_param)
            )
            lithology_to_k.create_multi_thermcon_profiles()
            config.lithology_to_k = lithology_to_k

        if config.dooptimize:
            config_dump = config.model_dump()
            _, config_new = optimize_forkeys(
                config_dump,
                config.copcrit,
                config.optimize_keys,
                config.optimize_keys_bounds,
                self._isample,
            )
            config = SingleRunConfig(**config_new)

        self._config = config
        self._single_run = SingleRun.from_config(config)

    def _load_json_parameters(self, json_file_path):
        """Load JSON config and flatten optional nested config files."""
        keysneeded = []
        keysoptional = [
            "litho_k_param",
            "loadprofile",
            "borefield",
            "flow_data",
            "variables_config",
        ]
        json_parameters = load_nested_config(json_file_path, keysneeded, keysoptional)
        for key, value in json_parameters.items():
            self.parameters[key] = value

    def _set_empty_output(self):
        """Reset output to NaN/empty placeholders (e.g. before the first valid input)."""
        self.output = {
            "outlet_temperature": np.nan,
            "heat_extracted": np.nan,
            "pump_power": np.nan,
            "inlet_temperature": np.nan,
            "mass_flow_rate": np.nan,
            "mean_borehole_wall_temperature": np.nan,
            "fluid_temperature_depth": np.array([]),
            "fluid_temperature_depth_axis": np.array([]),
            "borehole_wall_temperature_depth": np.array([]),
            "borehole_wall_temperature_depth_axis": np.array([]),
        }
