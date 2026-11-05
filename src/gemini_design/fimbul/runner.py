"""Run Fimbul.jl (JutulDarcy thermal) doublet simulations from Python.

Julia is called as a subprocess on ``doublet_sim.jl``; every run is cached
as JSON under ``cache_dir`` keyed by a hash of its inputs, so repeated
calls (from the agent, the sweep or the tests) never re-run Julia.

Julia set-up (once):
    julia --project=<env> -e 'using Pkg;
        Pkg.add(["Fimbul", "Jutul", "JutulDarcy", "HYPRE", "JSON"])'

then point ``GEMINI_JULIA`` at the julia executable and ``GEMINI_FIMBUL_ENV``
at ``<env>`` (or pass ``julia=``/``project=``).
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from gemini_design.challenge import ASSUMPTIONS, CHALLENGE

SCRIPT = Path(__file__).with_name("doublet_sim.jl")
DEFAULT_CACHE = Path(__file__).with_name("cache")

# Rock and model settings not given in the brief (stated so the agent can report them).
FIMBUL_ASSUMPTIONS = {
    "porosity": 0.20,
    "kv_kh": 0.1,
    "rock_density": 2650.0,  # kg/m3
    "rock_heat_capacity": 900.0,  # J/(kg.K)
    "reservoir_conductivity": 2.5,  # W/(m.K), sandstone
    "confining_conductivity": 2.0,  # W/(m.K), shale cap and base rock
    "confining_perm_md": 0.01,  # sealing cap and base rock
    "confining_m": 200.0,  # modelled cap/base rock thickness (thermal recharge)
    "well_radius_m": ASSUMPTIONS["wellbore_radius_m"],
}

# Mesh and numerics (checked in the grid study, see run_fimbul_sweep.py)
MESH = {
    "dx_m": 50.0,  # uniform cells around and between the wells
    "fine_pad_m": 300.0,
    "outer_m": 2500.0,  # graded cells out to this distance beyond the fine zone
    "growth": 1.3,
    "dx_max_m": 500.0,
    "nz_reservoir": 10,
    "nz_confining": 5,
    "confining_first_dz_m": 10.0,
    "max_timestep_days": 60.0,
}


def water_viscosity_pa_s(temperature_c):
    """Pure-water viscosity (Vogel fit, within ~5% of IAPWS for 20-150 degC)."""
    return 2.414e-5 * 10.0 ** (247.8 / (temperature_c + 273.15 - 140.0))


def mobility_factor(depth_m, challenge=CHALLENGE):
    """Return mu_water / mu_brine at reservoir temperature.

    Fimbul's fluid is pure water (IAPWS tables), less viscous than the
    challenge brine (0.40 mPa.s). Scaling the simulated permeability by this
    factor gives the brine's mobility k/mu, so pressures match the brief;
    temperatures do not depend on it in this homogeneous reservoir.
    """
    t_res = challenge["surface_temperature_c"] + challenge["geothermal_gradient_c_per_km"] * (
        depth_m / 1000.0
    )
    return water_viscosity_pa_s(t_res) / challenge["brine_viscosity"]


def default_inputs(**overrides):
    """Return a full Fimbul input dict for one constant-rate doublet at 3.1 km."""
    inputs = {
        "depth_m": 3100.0,
        "thickness_m": CHALLENGE["reservoir_thickness_m"],
        "permeability_md": CHALLENGE["permeability_md"],
        "surface_temperature_c": CHALLENGE["surface_temperature_c"],
        "gradient_c_per_km": CHALLENGE["geothermal_gradient_c_per_km"],
        "brine_cp": ASSUMPTIONS["brine_cp"],
        "brine_density": CHALLENGE["brine_density"],
        "pressure_ref_bar": CHALLENGE["reservoir_pressure_bar"],
        "pressure_ref_depth_m": CHALLENGE["reservoir_depth_m"],
        "n_doublets": 1,
        "well_spacing_m": 1200.0,
        "doublet_separation_m": 1500.0,
        **FIMBUL_ASSUMPTIONS,
        **MESH,
    }
    schedule = overrides.pop("schedule", None)
    years = overrides.pop("years", 30)
    flow = overrides.pop("flow_m3h", 150.0)
    t_inj = overrides.pop("injection_temperature_c", 60.0)
    inputs.update(overrides)
    inputs.setdefault("mobility_factor", mobility_factor(inputs["depth_m"]))
    if schedule is None:
        n = inputs["n_doublets"]
        schedule = constant_schedule([flow] * n, [t_inj] * n, years)
    inputs["schedule"] = schedule
    return inputs


def constant_schedule(flows_m3h, injection_temperatures_c, years, steps_per_year=4):
    """Return one schedule period per year at constant per-doublet rates."""
    return [
        {
            "duration_days": 365.0,
            "substeps": steps_per_year,
            "flow_m3h": list(map(float, flows_m3h)),
            "injection_temperature_c": list(map(float, injection_temperatures_c)),
        }
        for _ in range(int(years))
    ]


def schedule_from_daily(daily, availability, years=30):
    """Return a monthly schedule repeated for ``years`` from a runner ``daily`` table.

    ``daily`` is the DataFrame from :func:`gemini_design.annual.run_year`;
    ``availability`` is the (365, n_doublets) array from
    :func:`gemini_design.annual.schedule_outages`. On days with fewer active
    doublets than available ones, the lowest-numbered available doublets run.
    Each month uses the volume-averaged flow and flow-weighted injection
    temperature of each doublet.
    """
    n_doublets = availability.shape[1]
    flows = np.zeros((len(daily), n_doublets))
    t_inj = np.zeros((len(daily), n_doublets))
    for i, row in enumerate(daily.itertuples()):
        on = np.flatnonzero(availability[i])[: int(row.n_active)]
        flows[i, on] = row.flow_per_doublet_m3h
        t_inj[i, on] = row.injection_temperature_c
    months = np.asarray(daily["date"].dt.month)
    periods = []
    for m in range(1, 13):
        sel = months == m
        q = flows[sel].mean(axis=0)
        vol = flows[sel].sum(axis=0)
        t = np.where(vol > 0, (flows[sel] * t_inj[sel]).sum(axis=0) / np.maximum(vol, 1e-9), 60.0)
        periods.append(
            {
                "duration_days": float(sel.sum()),
                "substeps": 1,
                "flow_m3h": q.tolist(),
                "injection_temperature_c": t.tolist(),
            }
        )
    return periods * int(years)


def _key(inputs):
    blob = json.dumps(inputs, sort_keys=True).encode()
    blob += SCRIPT.read_bytes()
    return hashlib.sha1(blob).hexdigest()[:16]


def julia_available(julia=None):
    """Return True if a Julia executable is configured and on the path."""
    return shutil.which(julia or os.environ.get("GEMINI_JULIA", "julia")) is not None


def _julia_command(julia, project):
    julia = julia or os.environ.get("GEMINI_JULIA", "julia")
    project = project or os.environ.get("GEMINI_FIMBUL_ENV")
    if not julia_available(julia):
        raise RuntimeError(
            "Fimbul result not cached and Julia is not available; set GEMINI_JULIA "
            "and GEMINI_FIMBUL_ENV (see gemini_design/fimbul/runner.py)."
        )
    cmd = [julia]
    if project:
        cmd.append(f"--project={project}")
    return cmd


def run_fimbul(inputs, cache_dir=DEFAULT_CACHE, julia=None, project=None, timeout_s=None):
    """Run (or fetch from cache) Fimbul simulations and return their result dicts.

    ``inputs`` is one input dict (returns one result) or a list of them
    (returns a list; uncached cases run as one batch so Julia compiles once).
    A result holds ``time_days``, ``num_cells``, ``wall_time_s``, ``inputs``
    and, per well, ``bottomhole_temperature_c`` and ``bottomhole_pressure_bar``
    series (one value per report step) plus ``initial_pressure_bar`` and
    ``initial_temperature_c``.
    """
    single = isinstance(inputs, dict)
    cases = [inputs] if single else list(inputs)
    cache_dir = Path(cache_dir)
    files = [cache_dir / f"{_key(c)}.json" for c in cases]
    todo = [i for i, f in enumerate(files) if not f.exists()]
    if todo:
        cmd = _julia_command(julia, project)
        cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            inp, out = Path(tmp) / "in.json", Path(tmp) / "out.json"
            inp.write_text(json.dumps([cases[i] for i in todo]))
            subprocess.run(cmd + [str(SCRIPT), str(inp), str(out)], check=True, timeout=timeout_s)
            results = json.loads(out.read_text())
        for i, result in zip(todo, results):
            result["inputs"] = cases[i]
            files[i].write_text(json.dumps(result))
    results = [json.loads(f.read_text()) for f in files]
    return results[0] if single else results
