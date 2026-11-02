"""Run the parity cases through the models of ``origin/main`` (``gemini_model``).

Run with ``PYTHONPATH=<main worktree>/src python scripts/parity/main_adapter.py CASES OUT``:
``CASES`` is the json of ``cases.py``, ``OUT`` receives ``{name: outputs}`` as json. A case
that raises records ``{"error": <exception class name>}``. This file imports nothing of ``gemini``.
"""

import json
import sys

import numpy as np
from gemini_model.corrosion.co2_corrosion import CO2Corrosion
from gemini_model.corrosion.co2_corrosion_opt import CO2CorrosionOpt
from gemini_model.corrosion.correlation.co2_partial_pressure_model import CO2PartialPressureModel
from gemini_model.erosion.erosion_model import ErosionModel
from gemini_model.fluid.pvt_water_stp import PVTConstantSTP
from gemini_model.pump.esp import ESP
from gemini_model.reservoir.inflow_performance import IPR
from gemini_model.reservoir.injectivity_index import injectivity_index
from gemini_model.reservoir.reservoir_pressure_estimation import reservoir_pressure
from gemini_model.reservoir.reservoir_pressuredrop import bottomhole_skin_dp
from gemini_model.well.correlation.beggsbrill import BeggsBrill
from gemini_model.well.correlation.darcyweisbach import DarcyWeisbach
from gemini_model.well.correlation.temperaturedrop import TemperatureDrop
from gemini_model.well.pressure_drop import DPDT

ARRAYS = ("length", "angle", "diameter", "flow", "bottomhole_pressure")
MODELS = {
    "reservoir_estimate": reservoir_pressure,
    "injectivity": injectivity_index,
    "reservoir_dp": bottomhole_skin_dp,
    "chemistry": CO2PartialPressureModel,
}


def arrays(values):
    """Return the values with the array-valued entries as numpy arrays."""
    return {k: np.array(v) if k in ARRAYS else v for k, v in values.items()}


def model_class(family):
    """Return the class of ``main`` that a golden case family runs."""
    if family.startswith("esp_"):
        return ESP
    if family.startswith("ipr_"):
        return IPR
    if family.startswith("corrosion_"):
        return CO2CorrosionOpt if family.endswith("True") else CO2Corrosion
    if family.startswith("erosion_"):
        return ErosionModel
    return MODELS[family]


def run_model(cls, parameters, inputs):
    """Evaluate one model of ``main`` and return its output dict."""
    model = cls()
    model.update_parameters(arrays(parameters))
    model.calculate_output(arrays(inputs), None)
    return model.get_output()


def run_well(parameters, inputs):
    """March one well of ``main`` over its trajectory."""
    model = DPDT()
    model.PVT = PVTConstantSTP()
    model.update_parameters(arrays(parameters))
    model.calculate_output(inputs, None)
    return model.get_output()


def run_case(case):
    """Return the outputs of one case."""
    family, parameters, inputs = case["family"], case["parameters"], case["inputs"]
    if family in ("darcy", "beggs"):
        return (DarcyWeisbach if family == "darcy" else BeggsBrill).calculate_dp(*inputs)
    if family == "temperature":
        return TemperatureDrop.calculate_dt(*inputs)
    if family.startswith("well_"):
        return run_well(parameters, inputs)
    return run_model(model_class(family), parameters, inputs)


def main(cases_path, out_path):
    """Run every case; write the outputs, or the name of the exception a case raised."""
    results = {}
    for name, case in json.loads(open(cases_path).read()).items():
        try:
            results[name] = run_case(case)
        except Exception as error:
            results[name] = {"error": type(error).__name__}
    with open(out_path, "w") as handle:
        json.dump(results, handle, default=lambda x: x.tolist() if hasattr(x, "tolist") else x)


if __name__ == "__main__":
    main(*sys.argv[1:3])
