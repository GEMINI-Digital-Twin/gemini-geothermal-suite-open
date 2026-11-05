"""Cross-check one GEMINI doublet against TNO's pyThermoGIS (DoubletCalc1D).

pyThermoGIS is TNO's Python API to the ThermoGIS Java doublet and cost
model (https://pythermogis-15909e.ci.tno.nl/). It is NOT a dependency of
this repo: install it in its own virtual environment from TNO's index,

    python -m venv thermogis_venv
    thermogis_venv/Scripts/python -m pip install pythermogis \
        --index-url https://ci.tno.nl/gitlab/api/v4/projects/18271/packages/pypi/simple

then run

    thermogis_venv/Scripts/python simulator_examples/run_thermogis_crosscheck.py

The first run downloads a Java 17 runtime (~350 MB). The PyPI package of the
same name (v0.1.6) is an old stub without the ThermoGIS jar and cannot run.

Cases (one doublet each, challenge reservoir moved to the given depth):

* ``matched``: our brief and design assumptions (12 degC + 30 degC/km,
  100 m, 200 mD, 40 K brine cool-down, 70% pump efficiency, skin 0,
  smooth steel casing, flow capped at the brief's 300 m3/h).
* ``matched_free_flow``: as ``matched`` but ThermoGIS may pick any flow up
  to its 500 m3/h default, to show what it would pump.
* ``matched_brief_salinity``: ``matched`` with salinity set to the brief's
  ~43 g/L brine (ThermoGIS default is ~145 g/L at 3.1 km).
* ``tno_defaults``: same reservoir and temperature, every other setting at
  the ThermoGIS NL base case.
* ``porosity_*``: ``matched`` with porosity 0.15 / 0.25 (the brief gives none;
  0.20 is our assumption). Porosity only moves the well spacing.
* ``depth_sweep``: ``matched`` from 2,000 to 3,600 m midpoint depth.

Output: ``study_results/2026-11-02/thermogis/thermogis_runs.csv`` and a
``run_info.json`` with the package version.
"""

import json
import os
import platform
import sys
from importlib import metadata

import numpy as np
import pandas as pd

from pythermogis.aquifer import Aquifer
from pythermogis.doublet import ThermoGISDoublet

try:
    from pythermogis import UTCSettings
except ImportError:  # module layout differs between releases
    from pythermogis.settings import UTCSettings

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "study_results", "2026-11-02", "thermogis")

# GeoHackathon brief (same numbers as gemini_design.challenge.CHALLENGE)
SURFACE_T_C = 12.0
GRADIENT_C_PER_KM = 30.0
THICKNESS_M = 100.0
PERMEABILITY_MD = 200.0
NTG = 1.0
POROSITY = 0.20  # not in the brief; team assumption
MAX_BRINE_COOLING_K = 40.0
HEATING_RETURN_C = 40.0  # our district heating return
PICK_DEPTH_MID_M = 3100.0

# Our design assumptions (gemini_design.challenge.ASSUMPTIONS)
MATCHED_SETTINGS = {
    "surface_temperature": SURFACE_T_C,
    "temperature_gradient": GRADIENT_C_PER_KM,
    "pump_efficiency": 0.70,
    "max_cooling_temperature_range": MAX_BRINE_COOLING_K,
    "dh_return_temp": HEATING_RETURN_C,
    "producer_skin": 0.0,
    "injector_skin": 0.0,
    # ThermoGIS reads roughness in milli-inch (Java multiplies by 2.54e-5 m),
    # although the pythermogis docstring says mm. Ours: 0.045 mm steel casing.
    "roughness": 0.045 / 0.0254,  # milli-inch (= 4.5e-5 m)
    "max_flow": 300.0,
}


def temperature_at_mid_depth(depth_mid_m):
    """Return the brief's reservoir temperature (degC) at a midpoint depth."""
    return SURFACE_T_C + GRADIENT_C_PER_KM * depth_mid_m / 1000.0


def run_case(name, depth_mid_m, settings_kwargs, porosity=POROSITY):
    """Run one deterministic ThermoGIS doublet and return a flat result dict."""
    settings = UTCSettings(**settings_kwargs)
    aquifer = Aquifer(
        thickness=THICKNESS_M,
        ntg=NTG,
        porosity=porosity,
        depth=depth_mid_m - THICKNESS_M / 2.0,  # ThermoGIS takes top depth
        permeability=PERMEABILITY_MD,
        temperature=temperature_at_mid_depth(depth_mid_m),
    )
    ds = ThermoGISDoublet(aquifer=aquifer, settings=settings).simulate().to_dataset()
    row = {"case": name, "depth_mid_m": depth_mid_m, "porosity_in": porosity}
    for var in ds.data_vars:
        row[var] = float(np.asarray(ds[var].values).squeeze())
    return row


def main():
    """Run every case and write the CSV."""
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = [
        run_case("matched", PICK_DEPTH_MID_M, MATCHED_SETTINGS),
        run_case("matched_free_flow", PICK_DEPTH_MID_M, {**MATCHED_SETTINGS, "max_flow": 500.0}),
        run_case(
            "matched_brief_salinity",
            PICK_DEPTH_MID_M,
            {**MATCHED_SETTINGS, "surface_salinity": 0.0, "salinity_gradient": 43.0 / 3.1},
        ),
        run_case("tno_defaults", PICK_DEPTH_MID_M, {}),
        run_case("porosity_0.15", PICK_DEPTH_MID_M, MATCHED_SETTINGS, porosity=0.15),
        run_case("porosity_0.25", PICK_DEPTH_MID_M, MATCHED_SETTINGS, porosity=0.25),
    ]
    for depth in np.arange(2000.0, 3601.0, 100.0):
        rows.append(run_case("depth_sweep", float(depth), MATCHED_SETTINGS))
    df = pd.DataFrame(rows)
    path = os.path.join(OUT_DIR, "thermogis_runs.csv")
    df.to_csv(path, index=False, float_format="%.6g")
    info = {
        "pythermogis_version": metadata.version("pythermogis"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "matched_settings": MATCHED_SETTINGS,
        "porosity_assumed": POROSITY,
    }
    with open(os.path.join(OUT_DIR, "run_info.json"), "w") as f:
        json.dump(info, f, indent=2)
    with pd.option_context("display.width", 200, "display.max_columns", 40):
        print(df.to_string(index=False))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
