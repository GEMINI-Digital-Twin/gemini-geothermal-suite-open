"""The cases of the parity check, in the names and units of ``main``, shared by both adapters.

``cases()`` returns ``{name: {"family", "parameters", "inputs"}}``. ``family`` is the name of the
phase-0 golden case the adapters dispatch on. The first block is the golden set itself; the other
blocks are deterministic sweeps around it (operating points, a seeded draw of correlation inputs).
"""

import copy
import itertools
import json
from pathlib import Path

import numpy as np

GOLDEN = Path(__file__).resolve().parents[2] / "tests/fixtures/golden_values.json"
SEED = 20260601
POWER = [10.02089977, -0.000160233, 6.52e-8, -2.13e-12, 1.71e-17, 1.38e-23]


def golden():
    """Return the phase-0 golden cases without their expected values."""
    stored = json.loads(GOLDEN.read_text())
    return {
        name: {"family": name, "parameters": c.get("parameters", {}), "inputs": c["inputs"]}
        for name, c in stored.items()
    }


def _add(out, name, family, base, parameters=None, inputs=None):
    """Add a copy of the golden case ``base`` with some parameters or inputs replaced."""
    case = copy.deepcopy(base[family])
    if isinstance(case["inputs"], dict):
        case["inputs"].update(inputs or {})
    elif inputs is not None:
        case["inputs"] = inputs
    case["parameters"].update(parameters or {})
    out[name] = case


def _pumps(out, base):
    """Add the pump at other flows and frequencies, with the all-zero and the real power fit."""
    for tag, extra in (("plain", {}), ("power", {"power_coeff": POWER})):
        for flow in (60, 100, 150, 200):
            for frequency in (35, 45, 55, 60):
                _add(
                    out,
                    f"esp_sweep_{tag}_q{flow}_f{frequency}",
                    "esp_50",
                    base,
                    extra,
                    {"pump_flow": flow / 3600, "pump_freq": frequency},
                )


def _reservoir(out, base):
    """Add inflow performance, injectivity, pressure estimation and skin drop at other points."""
    for role in ("production", "injection"):
        for flow in (0, 40, 100, 250):
            _add(out, f"ipr_sweep_{role}_{flow}", f"ipr_{role}", base, None, {"flow": flow / 3600})
    for flow, pressure in ((100, 22.6e6), (200, 23.4e6), (300, 24.1e6)):
        _add(
            out,
            f"injectivity_sweep_{flow}",
            "injectivity",
            base,
            None,
            {"flow": flow / 3600, "bottomhole_pressure": pressure},
        )
    rng = np.random.default_rng(SEED)
    for k in range(3):
        flow = np.sort(rng.uniform(0.005, 0.06, 6))
        pressure = 21.5e6 + 3e8 * flow + rng.normal(0, 5e4, 6)
        _add(
            out,
            f"reservoir_estimate_sweep_{k}",
            "reservoir_estimate",
            base,
            None,
            {"flow": flow.tolist(), "bottomhole_pressure": pressure.tolist()},
        )
    for skin in (0, 5):
        for flow in (50 / 3600, 250 / 3600):
            _add(
                out,
                f"reservoir_dp_sweep_s{skin}_q{round(flow * 3600)}",
                "reservoir_dp",
                base,
                None,
                {"skin_factor": skin, "flow": flow},
            )


def _wells(out, base):
    """Add both wells at other flows, inlet pressures and temperatures."""
    for family, direction in (("well_production", "up"), ("well_injection", "down")):
        sign = 1 if direction == "up" else -1
        points = itertools.product((60, 220), ((22e6, 343.15), (8e6, 363.15)))
        for flow, (pressure, temperature) in points:
            _add(
                out,
                f"{family}_sweep_q{flow}_p{round(pressure / 1e6)}",
                family,
                base,
                None,
                {"flowrate": sign * flow / 3600, "pressure": pressure, "temperature": temperature},
            )


def _correlations(out, base):
    """Add the three correlations at a seeded draw of inputs around the golden point."""
    rng = np.random.default_rng(SEED + 1)
    for family in ("darcy", "beggs", "temperature"):
        for k in range(12):
            factors = rng.uniform(0.8, 1.2, len(base[family]["inputs"]))
            inputs = [float(v) * float(f) for v, f in zip(base[family]["inputs"], factors)]
            if family == "temperature":
                inputs[3] = base[family]["inputs"][3]
            _add(out, f"{family}_sweep_{k}", family, base, None, inputs)
    for k, sign in enumerate((-1, 1)):
        inputs = list(base["darcy"]["inputs"])
        inputs[0] *= sign
        _add(out, f"darcy_flow_sign_{k}", "darcy", base, None, inputs)


def _chemistry_corrosion_erosion(out, base):
    """Add the chemistry, corrosion and erosion models at other temperatures, pressures, flows."""
    for k, (temperature, fraction) in enumerate(((30, 0.05), (60, 0.1), (95, 0.2))):
        _add(
            out,
            f"chemistry_sweep_{k}",
            "chemistry",
            base,
            None,
            {"temperature_system": temperature, "co2_mol_fraction": fraction},
        )
    grid = itertools.product(("False", "True"), ("NORSOK", "DLM", "DLD"), (30, 60, 90), (1, 10))
    for fitted, model, temperature, pressure in grid:
        _add(
            out,
            f"corrosion_sweep_{model}_{fitted}_t{temperature}_p{pressure}",
            f"corrosion_{model}_{fitted}",
            base,
            None,
            {"temperature": temperature, "pressure": pressure},
        )
    for model in ("DNV", "OKA", "TULSA", "API"):
        for flow, density in ((60, 1000), (300, 1150)):
            _add(
                out,
                f"erosion_sweep_{model}_q{flow}",
                f"erosion_{model}",
                base,
                None,
                {"flowRate": flow, "rho_fluid": density},
            )


def cases():
    """Return every case of the check, golden first, in a stable order."""
    base = golden()
    out = dict(base)
    for block in (
        _pumps,
        _reservoir,
        _wells,
        _correlations,
        _chemistry_corrosion_erosion,
    ):
        block(out, base)
    return out
