"""Registry of the agent tools: name -> function, OpenAI-style schemas, and call(name, args).

Each tool returns a flat dict, units in the key names; the tools live in the AI02_tools_<topic>.py files."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from AI02_tools_common import r2  # noqa: F401,E402
from AI02_tools_economics import economics, gas_point, layout_compare, lifetime_point, optimise_point, storage_point  # noqa: E402
from AI02_tools_gemini import gemini, gemini_replay, gemini_traps, gemini_version  # noqa: F401,E402
from AI02_tools_schema import ARGS, D, NUM, OPTIONAL, PEAKS, SIG, STRINGS  # noqa: F401,E402
from AI02_tools_site import demand_summary, doublet_point, heat_pump_point, injector_point, site_inputs  # noqa: E402
from AI02_tools_year import SWEEP_C, checks, cooling_year, heating_year, return_sweep  # noqa: F401,E402

FUNCS = {f.__name__: f for f in (site_inputs, demand_summary, doublet_point, heating_year, cooling_year, injector_point, gas_point,
                                 lifetime_point, heat_pump_point, checks, economics, layout_compare, storage_point, return_sweep,
                                 optimise_point, gemini_replay, gemini_traps)}
TOOLS = [{"type": "function", "function": {"name": n, "description": " ".join(FUNCS[n].__doc__.split()),
          "parameters": {"type": "object", "properties": {a: ARGS[a] for a in args},
                         "required": [a for a in args if a not in OPTIONAL]}}} for n, args in SIG.items()]


def call(name, args):
    """Run one tool by name; numeric arguments cast to int or float."""
    if name not in FUNCS:
        raise ValueError(f"unknown tool {name}; valid: {sorted(FUNCS)}")
    conv = lambda k, v: v if v is None or k in STRINGS else int(v) if k in ("n_doublets", "outage_days", "max_doublets") else float(v)
    return FUNCS[name](**{k: conv(k, v) for k, v in (args or {}).items()})


if __name__ == "__main__":
    two = {"n_doublets": 2, "t_return_c": 60}
    for name, args in (("site_inputs", {"depth_m": 2500, "supply_heat_c": 100, "supply_cold_c": 20}), ("demand_summary", {}),
                       ("doublet_point", {"q_m3h": 300, "t_return_c": 60}), ("heating_year", two), ("cooling_year", {"t_return_c": 60}),
                       ("injector_point", {"q_m3h": 300}), ("gas_point", {"q_m3h": 300}), ("lifetime_point", two),
                       ("heat_pump_point", {"t_brine_in_c": 63, "t_water_in_c": 82.58, "brine_m3h": 300, "water_m3h": 388,
                                            "t_brine_floor_c": 45.58}),
                       ("checks", two), ("economics", two), ("layout_compare", two), ("storage_point", two),
                       ("return_sweep", {"n_doublets": 2}), ("gemini_traps", {})):
        print(f"\n{name}({args})\n" + json.dumps(call(name, args), indent=1))
    print(f"\n{len(TOOLS)} tools, about {len(json.dumps(TOOLS)) // 4} tokens of schema")
