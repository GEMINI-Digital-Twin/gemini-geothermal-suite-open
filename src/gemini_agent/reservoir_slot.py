"""Pluggable reservoir simulators behind one agent tool.

The ``analytic`` provider is always there: temperature from the
gradient, hydrostatic pressure, Darcy productivity index and the GEMINI
well hydraulics at a few flow rates.

A ``fimbul`` provider (Fimbul / JutulDarcy doublet model, built in a
separate workstream) is picked up automatically when a module
``gemini_design.fimbul`` exposes::

    simulate_doublet(depth_m, flow_m3h, well_spacing_m, years, permeability_md, **kw) -> dict

returning plain numbers, e.g. ``production_temperature_c`` per year,
``breakthrough_year`` and ``injector_pressure_bar``. Any other provider
can be added with :func:`register_provider`.
"""

import importlib

from gemini_design.challenge import (
    CHALLENGE,
    productivity_index_m3h_per_bar,
    reservoir_at_depth,
)
from gemini_design.doublet import DoubletHydraulics

PROVIDERS = {}


def register_provider(name, function, description=""):
    """Add a reservoir provider: ``function(**arguments) -> dict``."""
    PROVIDERS[name] = {"function": function, "description": description}


def analytic_doublet(
    depth_m=2500.0, flow_m3h=None, permeability_md=None, well_spacing_m=None, years=None, **_
):
    """Steady-state reservoir + well hydraulics from the challenge data (no thermal decline)."""
    challenge = dict(CHALLENGE)
    if permeability_md is not None:
        challenge["permeability_md"] = float(permeability_md)
    temperature, pressure = reservoir_at_depth(depth_m, challenge)
    hyd = DoubletHydraulics(depth_m, challenge)
    flows = [flow_m3h] if flow_m3h else [100.0, 200.0, 300.0]
    curve = []
    for q in flows:
        p = hyd.producer(q)
        inj = hyd.injector(q, p["wellhead_temperature_c"] - challenge["brine_cooling_max_k"])
        curve.append(
            {
                "flow_m3h": q,
                "wellhead_temperature_c": p["wellhead_temperature_c"],
                "drawdown_bar": p["drawdown_bar"],
                "esp_power_kw": p["esp_power_w"] / 1e3,
                "injector_wellhead_pressure_bar": inj["wellhead_pressure_bar"],
                "injection_pump_power_kw": inj["pump_power_w"] / 1e3,
            }
        )
    return {
        "provider": "analytic",
        "reservoir_temperature_c": temperature,
        "reservoir_pressure_bar": pressure,
        "productivity_index_m3h_per_bar": productivity_index_m3h_per_bar(challenge),
        "per_flow": curve,
        "limits": "steady state: no thermal breakthrough, no pressure interference; "
        "use the fimbul provider for 30-year behaviour",
    }


register_provider(
    "analytic",
    analytic_doublet,
    "gradient temperature, hydrostatic pressure, Darcy PI, GEMINI well hydraulics",
)


def _load_fimbul():
    try:
        module = importlib.import_module("gemini_design.fimbul")
    except ImportError:
        return False
    function = getattr(module, "simulate_doublet", None)
    if function is None:
        return False
    register_provider(
        "fimbul",
        function,
        getattr(module, "__doc__", "") or "Fimbul/JutulDarcy doublet simulation",
    )
    return True


def available_providers():
    """Return provider names (tries to load Fimbul first)."""
    if "fimbul" not in PROVIDERS:
        _load_fimbul()
    return {name: p["description"].strip().splitlines()[0] for name, p in PROVIDERS.items()}


def simulate(provider="auto", **arguments):
    """Run a provider. ``auto`` prefers Fimbul when installed, else analytic."""
    names = available_providers()
    if provider == "auto":
        provider = "fimbul" if "fimbul" in names else "analytic"
    if provider not in PROVIDERS:
        return {
            "error": f"reservoir provider '{provider}' is not available",
            "available": sorted(names),
        }
    arguments = {k: v for k, v in arguments.items() if v is not None}
    result = PROVIDERS[provider]["function"](**arguments)
    result.setdefault("provider", provider)
    return result
