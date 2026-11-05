"""Fast doublet-performance lookup built from cached Fimbul.jl runs.

``simulate_doublet`` answers in microseconds without Julia, so the design
agent and the annual runner can call it in a loop. It interpolates a table
of 30-year Fimbul runs (``fimbul_table.json``, written by
``simulator_examples/run_fimbul_sweep.py``) in well spacing and flow rate,
using two scalings that the sweep checks:

* Temperature: the normalised drop
  ``theta = (T_res - T_prod) / (T_res - T_inj)`` does not depend on the
  injection temperature or on depth (only on spacing, rate and time), so
  any depth and injection temperature map onto the table.
* Pressure: drawdown and injection overpressure are linear in rate and in
  1/k, so other permeabilities scale as ``200 mD / k``. The injector also
  sees the cold plume's higher viscosity; other injection or reservoir
  temperatures scale its overpressure by the viscosity ratio to the 0.7
  power (fitted on two check runs).

Set ``live=True`` to run Fimbul itself for the exact case (needs Julia,
cached afterwards).
"""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from gemini_design.challenge import CHALLENGE, productivity_index_m3h_per_bar, reservoir_at_depth

TABLE = Path(__file__).with_name("fimbul_table.json")


@lru_cache(maxsize=1)
def load_table(path=TABLE):
    """Return the sweep table as numpy arrays (cached)."""
    raw = json.loads(Path(path).read_text())
    return {
        "meta": raw["meta"],
        "spacing_m": np.asarray(raw["spacing_m"], dtype=float),
        "flow_m3h": np.asarray(raw["flow_m3h"], dtype=float),
        "years": np.asarray(raw["years"], dtype=float),
        # arrays [spacing, flow, year]
        "theta": np.asarray(raw["theta"], dtype=float),
        "drawdown_bar": np.asarray(raw["drawdown_bar"], dtype=float),
        "injection_overpressure_bar": np.asarray(raw["injection_overpressure_bar"], dtype=float),
    }


def _bilinear(grid_x, grid_y, values, x, y):
    """Interpolate ``values[ix, iy, :]`` at (x, y), clamped to the grid."""
    x = float(np.clip(x, grid_x[0], grid_x[-1]))
    y = float(np.clip(y, grid_y[0], grid_y[-1]))
    i = int(np.clip(np.searchsorted(grid_x, x) - 1, 0, len(grid_x) - 2))
    j = int(np.clip(np.searchsorted(grid_y, y) - 1, 0, len(grid_y) - 2))
    tx = (x - grid_x[i]) / (grid_x[i + 1] - grid_x[i])
    ty = (y - grid_y[j]) / (grid_y[j + 1] - grid_y[j])
    return (
        (1 - tx) * (1 - ty) * values[i, j]
        + tx * (1 - ty) * values[i + 1, j]
        + (1 - tx) * ty * values[i, j + 1]
        + tx * ty * values[i + 1, j + 1]
    )


def simulate_doublet(
    depth_m=3100.0,
    flow_m3h=150.0,
    well_spacing_m=1200.0,
    years=30,
    permeability_md=None,
    injection_temperature_c=60.0,
    live=False,
    **kw,
):
    """Return 30-year reservoir performance of one doublet as plain JSON numbers.

    Parameters
    ----------
    depth_m : float
        Reservoir midpoint depth (temperature and pressure follow the brief).
    flow_m3h : float
        Annual-average production (= injection) rate of the doublet.
    well_spacing_m : float
        Injector-producer distance at reservoir depth.
    years : int
        Number of years reported (at most the table's 30).
    permeability_md : float, optional
        Reservoir permeability; defaults to the brief's 200 mD.
    injection_temperature_c : float
        Brine reinjection temperature.
    live : bool
        Run Fimbul for this exact case instead of interpolating (needs Julia).

    Returns
    -------
    dict
        ``production_temperature_c`` (one value per year, end of year),
        ``temperature_drop_c`` (from initial), ``breakthrough_year`` (first
        year the production temperature has fallen 1 K, or None),
        ``producer_drawdown_bar`` and ``injector_overpressure_bar`` per year,
        ``injector_pressure_bar`` per year (bottomhole), ``productivity_ratio``
        and ``injectivity_ratio`` per year (simulated PI and injectivity over
        the steady-state Darcy PI, for :class:`DoubletHydraulics`), and the
        inputs and the source (``fimbul_table`` or ``fimbul_live``).
    """
    if permeability_md is None:
        permeability_md = CHALLENGE["permeability_md"]
    t_res, p_res = reservoir_at_depth(depth_m)
    if live:
        return _simulate_live(
            depth_m, flow_m3h, well_spacing_m, years, permeability_md, injection_temperature_c, kw
        )
    tab = load_table()
    n = int(min(years, len(tab["years"])))
    theta = _bilinear(tab["spacing_m"], tab["flow_m3h"], tab["theta"], well_spacing_m, flow_m3h)
    f0 = tab["flow_m3h"]
    q_ref = float(np.clip(flow_m3h, f0[0], f0[-1]))
    k_scale = tab["meta"]["permeability_md"] / permeability_md
    # pressures are per unit rate in the table interpolation, then rescaled to flow_m3h
    dd = _bilinear(tab["spacing_m"], f0, tab["drawdown_bar"], well_spacing_m, flow_m3h)
    dpi = _bilinear(
        tab["spacing_m"], f0, tab["injection_overpressure_bar"], well_spacing_m, flow_m3h
    )
    dd = dd * flow_m3h / q_ref * k_scale
    dpi = (
        dpi
        * flow_m3h
        / q_ref
        * k_scale
        * _injectivity_viscosity_scale(injection_temperature_c, t_res, tab["meta"])
    )
    t_prod = t_res - theta * (t_res - injection_temperature_c)
    return _package(
        "fimbul_table",
        depth_m,
        flow_m3h,
        well_spacing_m,
        permeability_md,
        injection_temperature_c,
        t_res,
        p_res,
        t_prod[:n],
        dd[:n],
        dpi[:n],
        tab["meta"],
    )


# Exponent on the cold-brine viscosity ratio for injector overpressure: only
# the near-well region is cold, so the full ratio overstates the effect.
# Fitted on the sweep's 45 degC injection and 2.5 km depth checks (both
# within 2% after scaling, against 16% and 14% without).
INJECTOR_VISCOSITY_EXPONENT = 0.7


def _injectivity_viscosity_scale(t_inj, t_res, meta):
    """Return the injector overpressure factor for another T_inj or reservoir T."""
    from gemini_design.fimbul.runner import water_viscosity_pa_s as mu

    t_res_ref = meta["reservoir_temperature_c"]
    ratio = (mu(t_inj) / mu(t_res)) / (mu(meta["injection_temperature_c"]) / mu(t_res_ref))
    return ratio**INJECTOR_VISCOSITY_EXPONENT


def _package(source, depth_m, flow, spacing, perm, t_inj, t_res, p_res, t_prod, dd, dpi, meta):
    t_prod = [float(x) for x in t_prod]
    drop = [t_res - x for x in t_prod]
    # Simulated PI / injectivity against the steady-state Darcy PI of the
    # brief (same k and brine viscosity): fed to DoubletHydraulics as
    # ``productivity_ratio`` and ``injectivity_ratio``.
    challenge = dict(CHALLENGE, permeability_md=perm)
    pi_darcy = productivity_index_m3h_per_bar(challenge)
    breakthrough = next((i + 1 for i, d in enumerate(drop) if d >= 1.0), None)
    return {
        "source": source,
        "depth_m": float(depth_m),
        "flow_m3h": float(flow),
        "well_spacing_m": float(spacing),
        "permeability_md": float(perm),
        "injection_temperature_c": float(t_inj),
        "reservoir_temperature_c": float(t_res),
        "reservoir_pressure_bar": float(p_res),
        "years": list(range(1, len(t_prod) + 1)),
        "production_temperature_c": t_prod,
        "temperature_drop_c": drop,
        "breakthrough_year": breakthrough,
        "producer_drawdown_bar": [float(x) for x in dd],
        "injector_overpressure_bar": [float(x) for x in dpi],
        "injector_pressure_bar": [float(p_res + x) for x in dpi],
        "productivity_ratio": [float(flow / max(x, 1e-9) / pi_darcy) for x in dd],
        "injectivity_ratio": [float(flow / max(x, 1e-9) / pi_darcy) for x in dpi],
        "assumptions": meta.get("assumptions", {}),
    }


def _simulate_live(depth_m, flow, spacing, years, perm, t_inj, kw):
    from gemini_design.fimbul.runner import default_inputs, run_fimbul

    inputs = default_inputs(
        depth_m=depth_m,
        flow_m3h=flow,
        well_spacing_m=spacing,
        years=years,
        permeability_md=perm,
        injection_temperature_c=t_inj,
        **kw,
    )
    res = run_fimbul(inputs)
    annual = annual_series(res)
    t_res, p_res = reservoir_at_depth(depth_m)
    return _package(
        "fimbul_live",
        depth_m,
        flow,
        spacing,
        perm,
        t_inj,
        t_res,
        p_res,
        annual["Producer1"]["temperature_c"],
        annual["Producer1"]["drawdown_bar"],
        annual["Injector1"]["overpressure_bar"],
        {"assumptions": {k: inputs[k] for k in inputs if k != "schedule"}},
    )


def annual_series(result):
    """Return end-of-year bottomhole temperature and pressure change per well."""
    t = np.asarray(result["time_days"]) / 365.0
    ends = [int(np.argmin(np.abs(t - y))) for y in range(1, int(round(t[-1])) + 1)]
    out = {}
    for name, w in result["wells"].items():
        temp = np.asarray(w["bottomhole_temperature_c"])[ends]
        p = np.asarray(w["bottomhole_pressure_bar"])[ends]
        dp = p - w["initial_pressure_bar"]
        out[name] = {
            "temperature_c": temp.tolist(),
            "initial_temperature_c": w["initial_temperature_c"],
            "drawdown_bar": (-dp).tolist(),
            "overpressure_bar": dp.tolist(),
        }
    return out
