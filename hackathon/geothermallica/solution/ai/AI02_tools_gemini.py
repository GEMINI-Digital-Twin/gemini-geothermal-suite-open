"""GEMINI tools: version stamp, the known GEMINI traps, and a replay of our design in GEMINI's own solver."""
import subprocess
from functools import lru_cache
from pathlib import Path

from AI02_tools_common import _esp, _need, _peaks, r2
from geo.common import DEPTH_M
from geo import gemini_project

# the GEMINI classes each tool runs, so a tool result names the twin's components
PRODUCER_GEMINI = ["IPR", "DPDT", "ESP via similarity law (ESPAffinity-equivalent)", "PVTConstantSTP"]
INJECTOR_GEMINI = ["IPR (injection_reservoir)", "DPDT (signed flow, injector sign fix)", "PVTConstantSTP"]


@lru_cache
def gemini_version():
    """Path and git commit of the GEMINI package the tools import."""
    import gemini_model
    root = Path(gemini_model.__file__).parents[2]
    sha = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    return f"{_short(root)} @ {sha or 'no git'}"


def _short(path):
    """A path written from the home directory as ~/..., so no user name leaks into tool results."""
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def gemini(names):
    return {"gemini_components": names, "gemini_version": gemini_version()}


def gemini_traps():
    """GEMINI findings as short sentences the agent may cite; heat_pump_point runs GEMINI's own heat pump with the root fix."""
    return {"esp_floor": "The ESP curve is valid 158-342 m3/h; GEMINI returns numbers at 50 m3/h without warning, "
                         "so 160 m3/h is the real floor.",
            "return_temperature": "The network return temperature decides the plant: at 55-60 C a brine-source heat pump replaces the boiler.",
            "absorption_brine": "Most summer surplus brine is 46-63 C, too cold for absorption; "
                                "only the slice above 78 C (about 3 GWh) drives chillers.",
            "free_cooling": "Free cooling 77 % rests on a 26 C return, 4 K approach, De Bilt 2024 weather and daily maximum wet bulb "
                            "(92 % with daily mean).",
            "esp_head_law": "GEMINI's ESP reads the head curve at the actual flow, not q*60/f (similarity law); it overstates head "
                            "at reduced speed, 9 % at 57 Hz and 300 m3/h; corrected in ESPAffinity.",
            "injector_sign": "nodal_solver.py:150 passes a positive injection flow, so friction adds pressure going down. A 0.001 "
                             "bar injection wellhead at 300 m3/h is this bug: TNO 38.3 bar at 0.045 mm roughness, 0.001 at "
                             "the 10 mm default, our fork 63.3. Fixed on the fork.",
            "heatpump_floor_branch": "heatpump_basic.py:286-305: when the source floor binds, HeatpumpBasic has two roots and Nelder-Mead "
                                     "may pick the unphysical one (COP 1.01, water out 796 C at 720 m3/h); it flips root at 398.66 and "
                                     "534.48 m3/h. Our HeatPumpLift brackets the solve, swept 100-720 m3/h: never above 100 C, not "
                                     "exposed.",
            "exchanger_abs": "heat_exchanger.py:107 takes abs() of the temperature difference, so 2.15 MW flows from a 50 C primary to "
                             "a 56.5 C secondary. Our chain feeds the exchanger at 78 C or more against a 56.5 C return and never "
                             "enters that case.",
            "esp_intake_clamp": "nodal_solver.py:67 and well_flow.py:295 floor the ESP intake at 0 bar without a warning: 168.9 m3/h "
                                "reported with intake 0.00 bar where discharge minus head is -36.2 bar. Our check 14 needs the intake "
                                "above the gas bubble point, so a clamped intake fails, not passes.",
            "roughness_default": "well_flow.py defaults roughness to 0.01, read as metres (10 mm): 61.7 bar vs 12.5 bar of friction at "
                                 "300 m3/h in 7 in tubing over 2 500 m. We set 0.045 mm in geo/well.py and write it into every "
                                 "generated project.",
            "tag": "[C]"}


def _within(days, key):
    """'within X %' for the largest |key_diff_pct| over the days, or 'not compared' when no day has it."""
    diffs = [abs(d[key + "_diff_pct"]) for d in days if key + "_diff_pct" in d]
    return f"within {max(diffs):.1f} %" if diffs else "not compared"


def gemini_replay(n_doublets, t_return_c, peak_heat_MW=None, depth_m=DEPTH_M, esp_depth_m=None):
    """GEMINI's own simulator re-runs our design: the tool writes one doublet of the design as a native GEMINI project file
    (producer well with ESP, separator, filters, our absorption chiller, exchanger, our heat pump, boiler on the separator gas,
    injector, plus our gas bubble-point and thermal-breakthrough models) and runs GEMINI's solver on the coldest, the median and
    the mildest day of 2027 at the day's dispatch per doublet, heat demand scaled to peak_heat_MW if given (else 30 MW). Per day: GEMINI's flow at our ESP frequency, the frequency GEMINI
    needs for our flow, and at that flow GEMINI's pressures, brine and supply temperatures, exchanger, heat-pump, boiler and
    chiller MW, heat-pump COP, bubble point, breakthrough years and interference next to ours (_ours, _gemini, _diff_pct);
    residual columns take out the known 1 000 vs 1 030 kg/m3 well-column offset. Also the project file path, gemini_version
    and a verdict sentence."""
    _need("n_doublets", n_doublets, 1, 3)
    _need("t_return_c", t_return_c, 30, 70)
    _need("depth_m", depth_m, 1500, 4000)
    _peaks(peak_heat_MW, None)
    r = gemini_project.replay(int(n_doublets), float(t_return_c), float(depth_m), _esp(esp_depth_m), peak_heat_MW=peak_heat_MW)
    days = [r2({k: v for k, v in d.items() if v is not None and v == v}) for d in r["days"]]   # v == v drops nan
    solved = [d for d in days if "esp_head_residual_bar" in d]
    if not solved:
        return {"error": f"GEMINI's pump at 60 Hz cannot reach our flow on any of the {len(days)} days; nothing to compare"}
    head = max(abs(d["esp_head_residual_bar"]) for d in solved)
    inj = max(abs(d["p_injection_wellhead_residual_bar"]) for d in solved)
    gaps = [d["freq_hz_ours"] - d["freq_hz_gemini_same_flow"] for d in solved if "freq_hz_gemini_same_flow" in d]
    freq = (f" GEMINI needs up to {max(gaps):.1f} Hz less for the same flow (it reads the 60 Hz pump curve at the actual flow; "
            "we apply the similarity law)." if gaps else "")
    sign = (" GEMINI's injector friction sign (fixed on our branch) explains the rest."
            if inj > 3 and all(d["p_injection_wellhead_residual_bar"] < 0 for d in solved) else "")
    short = (f" GEMINI's pump at 60 Hz cannot reach our flow on {len(days) - len(solved)} of the days."
             if len(solved) < len(days) else "")
    cold = [d for d in solved if d.get("T_supply_C_gemini", 100.0) < 99.0]
    supply = (f" On {len(cold)} day(s) GEMINI's series chain (exchanger, then heat pump) reaches only "
              f"{min(d['T_supply_C_gemini'] for d in cold):.1f} C where our dispatch counts the heat at 100 C (heat pump cut "
              "back or off, or a boiler lift outside this chain); COP and duty differ on those days." if cold else "")
    verdict = (f"GEMINI's solver re-ran {len(solved)} days: ESP head within {head:.1f} bar, injection wellhead within {inj:.1f} bar, "
               f"heat-pump COP {_within(solved, 'cop_heat_pump')}, bubble point {_within(solved, 'p_bubble_bar')}, breakthrough "
               f"{_within(solved, 't_breakthrough_yr')}. "
               "The injection figure is after the water-column offset. Those come from GEMINI's nodal solve, its Lorenz "
               "heat-pump solve and its gas and breakthrough models with our "
               "parameters; flow, exchanger duty, full-draw heat-pump duty, boiler heat and chiller drive are equal by construction "
               "(the project carries our duty, floors, water flow and gas; the chiller has the same formula and wellhead temperature "
               "on both sides)." + freq + sign + short + supply)
    return {"n_doublets": int(n_doublets), "t_return_c": float(t_return_c), "peak_heat_MW": peak_heat_MW, "depth_m": float(depth_m),
            "esp_depth_m": _esp(esp_depth_m), "n_days": len(days), "days": days, "project_path": r["project_path"], "gemini_version": r["gemini_version"],
            "verdict": verdict, "basis": r["basis"], "tag": "[C]"}
