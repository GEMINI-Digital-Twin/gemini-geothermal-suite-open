"""Argument schemas of the agent tools: one entry per argument, and the argument list of each tool."""
from geo import gas, outage

NUM = lambda desc, lo, hi, kind="number": {"type": kind, "description": f"{desc}, {lo} to {hi}", "minimum": lo, "maximum": hi}
ARGS = {"depth_m": NUM("reservoir depth in m (omit for the brief's 2500 m); give the brief's depth to every tool", 1500, 4000),
        "supply_heat_c": NUM("heating supply temperature in C", 60, 120),
        "supply_cold_c": NUM("cooling supply temperature in C", 6, 25), "q_m3h": NUM("flow per well in m3/h", 50, 300),
        "t_return_c": NUM("network return temperature in C", 30, 70),
        "n_doublets": NUM("number of doublets", 1, 3, "integer"),
        "t_brine_in_c": NUM("brine temperature into the heat pump evaporator in C", 40, 90),
        "t_water_in_c": NUM("district water temperature into the heat pump condenser in C", 40, 99),
        "t_brine_floor_c": NUM("coldest brine allowed out of the evaporator in C, the wellhead T minus 40 K (omit: brine in minus 40 K)", 0, 90),
        "brine_m3h": NUM("brine flow through the evaporator in m3/h", 50, 600),
        "water_m3h": NUM("district water flow through the condenser in m3/h", 50, 600),
        "peak_heat_MW": NUM("peak heating demand of the brief in MW (omit for the 30 MW demand file)", 1, 100),
        "peak_cold_MW": NUM("peak cooling demand of the brief in MW (omit for the 10 MW demand file)", 0, 50),
        "outage_days": NUM("days one doublet is out in winter for the tank sizing (omit for 7)", 1, 35, "integer"),
        "spacing_m": NUM("distance producer to injector of one doublet at reservoir level in m (omit for 1500)", 500, 3000),
        "doublet_spacing_m": NUM("distance between neighbouring doublets in m (omit: equal to spacing_m)", 300, 5000),
        "esp_depth_m": NUM("ESP setting depth in m (omit for 1100 m); give the brief's or the plan's value to every tool", 300, 1250),
        "extra_return_c": NUM("one more return temperature in C to add to the sweep (omit for the six standard ones)", 30, 70),
        "priority": {"type": "string", "enum": ["lcoh", "co2"],
                     "description": "what the brief wants first: lcoh (cheapest heat, the default) or co2 (lowest emissions)"},
        "max_doublets": NUM("most doublets the brief allows (omit for 3)", 1, 3, "integer"),
        "outage_mode": {"type": "string", "enum": list(outage.MODES),
                        "description": "where the 35 planned outage days of each doublet fall: staggered (the default, least-demand "
                                       "windows one doublet at a time) or all_at_once (every doublet out together, backup carries it)"},
        "gas_handling": {"type": "string", "enum": list(gas.OPTIONS),
                         "description": "what happens to the gas dissolved in the brine (omit for the plan's choice by the gas "
                                        "rule): vent, flare, engine (gas engine), boiler (site boiler) or reinject (compressed "
                                        "into the injector)"}}
PEAKS = ["peak_heat_MW", "peak_cold_MW"]
OPTIONAL = PEAKS + ["t_brine_floor_c", "depth_m", "outage_days", "spacing_m", "doublet_spacing_m", "esp_depth_m", "extra_return_c",
            "priority", "max_doublets", "outage_mode", "gas_handling"]
D = ["depth_m", "esp_depth_m"]   # every tool that runs the producer takes both
SIG = {"site_inputs": ["depth_m", "supply_heat_c", "supply_cold_c"], "demand_summary": PEAKS,
       "doublet_point": ["q_m3h", "t_return_c"] + D, "heating_year": ["n_doublets", "t_return_c", "peak_heat_MW"] + D + ["outage_mode"],
       "cooling_year": ["t_return_c", "n_doublets"] + PEAKS + D, "injector_point": ["q_m3h", "depth_m"], "gas_point": ["q_m3h"] + D,
       "lifetime_point": ["n_doublets", "t_return_c", "peak_heat_MW"] + D + ["spacing_m", "doublet_spacing_m"],
       "heat_pump_point": ["t_brine_in_c", "t_water_in_c", "brine_m3h", "water_m3h", "t_brine_floor_c"],
       "checks": ["n_doublets", "t_return_c"] + PEAKS + D + ["outage_mode"], "economics": ["n_doublets", "t_return_c"] + PEAKS + D + ["outage_mode", "gas_handling"],
       "layout_compare": ["n_doublets", "t_return_c"] + PEAKS + D,
       "storage_point": ["n_doublets", "t_return_c", "peak_heat_MW"] + D + ["outage_days"],
       "return_sweep": ["n_doublets", "peak_heat_MW"] + D + ["extra_return_c"], "optimise_point": PEAKS + D + ["priority", "max_doublets"],
       "gemini_replay": ["n_doublets", "t_return_c", "peak_heat_MW"] + D,
       "gemini_traps": []}

STRINGS = ("priority", "outage_mode", "gas_handling")   # arguments passed through as text
