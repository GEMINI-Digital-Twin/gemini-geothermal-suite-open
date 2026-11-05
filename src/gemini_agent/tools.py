"""Typed, token-lean tools the LLM agents call.

Each tool returns compact JSON (no time series; large artefacts go to files)
and records its result in the session's fact ledger; the returned ``fact_id``
is what the agent must cite. Tools never ask the LLM for numbers they can
compute themselves.
"""

from __future__ import annotations

import functools
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

from langchain_core.tools import StructuredTool
from pydantic import BeforeValidator, model_validator

from gemini_agent.ledger import FactLedger, provenance_check
from gemini_agent.optimize import monte_carlo, score, search, stress_test
from gemini_agent.physics.constraints import _plain
from gemini_agent.physics.design import DesignSpec
from gemini_agent.physics.site import gas_properties, reservoir_state
from gemini_agent.physics.wells import WellSettings, injector_point, producer_point
from gemini_agent.service import DesignService, Evaluation
from gemini_simulator.registry import COMPONENT_REGISTRY

UPSTREAM_GEMINI_TYPES = {
    "adder",
    "mixer",
    "splitter",
    "separator",
    "filter",
    "heat_exchanger",
    "boiler",
    "chp",
    "injector_pump",
    "booster_pump",
    "well",
    "reservoir_bottomhole_skin",
    "reservoir_ipr",
    "esp",
    "producer_well",
    "injector_well",
}


@dataclass
class Session:
    """Per-conversation state shared by all tools."""

    svc: DesignService = field(default_factory=DesignService)
    ledger: FactLedger = field(default_factory=FactLedger)
    mode: Literal["interactive", "auto"] = "interactive"
    run_dir: Path = Path("runs/session")
    pending_question: str | None = None
    last_call: tuple | None = None  # repeat guard (reset every user turn)
    question_budget: int = 1  # clarifying questions allowed this turn (interactive mode)
    ask_tool: object = None
    assumptions_used: list[dict] = field(default_factory=list)
    current_design: str | None = None
    evaluations: dict[str, Evaluation] = field(default_factory=dict)

    def __post_init__(self):
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if not self.ledger.seed:
            self.ledger.seed = self.svc.brief.raw

    def remember(self, ev: Evaluation) -> Evaluation:
        """Track an evaluation so later tools can refer to it by design_id."""
        self.evaluations[ev.spec.key()] = ev
        return ev

    def design(self, design_id: str | None) -> Evaluation:
        """Evaluation by ID (or the current design)."""
        key = design_id or self.current_design
        if key not in self.evaluations and self.current_design:
            key = (
                self.current_design
            )  # small models often pass a label instead of the ID: use the current design
        if not key or key not in self.evaluations:
            raise ValueError(
                f"Unknown design_id '{design_id}'. Known: {list(self.evaluations)[-8:]}. "
                "Call evaluate_design or search_designs first."
            )
        return self.evaluations[key]


def _sig(v):
    """Round floats to 4 significant figures (token-lean, same values in ledger and prompt)."""
    if isinstance(v, float):
        return float(f"{v:.4g}") if v == v else None
    if isinstance(v, dict):
        return {k: _sig(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_sig(x) for x in v]
    return v


def _as_list(v):
    """Accept the list shapes small models produce: [2500], 2500, "2500, 3100", {"2500": 1}."""
    if v is None or isinstance(v, list):
        return v
    if isinstance(v, dict):
        keys = [k for k in v if str(k).replace(".", "", 1).isdigit()]
        return keys or list(v.values())
    if isinstance(v, str):
        return [x for x in re.split(r"[,;\s]+", v.strip("[]() ")) if x]
    return [v]


FloatList = Annotated[list[float] | None, BeforeValidator(_as_list)]
IntList = Annotated[list[int] | None, BeforeValidator(_as_list)]


def _out(session: Session, tool: str, args: dict, result: dict) -> str:
    result = _sig(_plain(result))
    fid = session.ledger.record(tool, args, result)
    return json.dumps({"fact_id": fid, **result}, separators=(",", ":"), default=str)


def build_tools(session: Session) -> list[StructuredTool]:
    """All tools bound to one session."""
    from gemini_agent.forge import load_generated

    load_generated()  # models generated in earlier sessions stay available
    s = session

    def get_brief() -> str:
        """Fixed inputs of the design brief, hard constraints, and the inputs the brief does
        NOT specify (with the default assumption the agent will use unless the user overrides)."""
        b = s.svc.brief
        res = {
            "reservoir": b.reservoir,
            "brine": b.brine,
            "constraints": b.constraints,
            "supply_temperatures_c": {
                "heating": b.raw["demand"]["heating_supply_temperature_c"],
                "cooling": b.raw["demand"]["cooling_supply_temperature_c"],
            },
            "not_in_brief_using_defaults": {a["name"]: a["value"] for a in b.assumptions_table()},
            "site_location": (
                "NOT SPECIFIED in the brief - needed for weather-driven cooling performance; "
                "ask the user, then call fetch_weather"
                if s.svc.weather is None
                else s.svc.weather.location
            ),
            "design_choices_left_to_us": [
                "district heating return temperature",
                "cooling network return temperature",
                "well depth",
                "number of doublets",
                "associated gas handling",
                "maintenance schedule",
            ],
            "economic_inputs_missing": [
                "energy prices",
                "CO2 price",
                "CAPEX unit costs",
                "discount rate",
            ],
        }
        return _out(s, "get_brief", {}, res)

    def analyze_demand() -> str:
        """Annual heating and cooling demand statistics (peaks, energy, seasonality)."""
        d = s.svc.demand
        res = d.summary()
        months = {}
        for date, h, c in zip(d.dates, d.heating_mw, d.cooling_mw):
            m = date[5:7]
            months.setdefault(m, [0.0, 0.0, 0])
            months[m][0] += h
            months[m][1] += c
            months[m][2] += 1
        res["monthly_avg_mw"] = {
            m: [round(v[0] / v[2], 1), round(v[1] / v[2], 1)] for m, v in months.items()
        }
        res["note"] = "monthly_avg_mw = [heating, cooling]"
        return _out(s, "analyze_demand", {}, res)

    def list_gemini_models() -> str:
        """GEMINI component models available to the simulator, which needs they cover, and
        which modelling capabilities were missing upstream (and were added)."""
        reg = sorted(COMPONENT_REGISTRY)
        res = {
            "registered_components": reg,
            "added_for_this_challenge": sorted(set(reg) - UPSTREAM_GEMINI_TYPES),
            "coverage": {
                "subsurface_wells": [
                    "producer_well",
                    "injector_well",
                    "well (DPDT)",
                    "reservoir_ipr",
                    "esp",
                ],
                "heating": ["heat_exchanger", "heat_pump", "boiler", "chp"],
                "cooling": ["absorption_chiller", "electric_chiller"],
            },
            "gaps_found_in_upstream_gemini": [
                "no cooling model -> added absorption_chiller and electric_chiller",
                "heat_pump existed but was not registered -> registered",
                "no productivity index from permeability -> added (Darcy radial flow)",
                "no thermal breakthrough / doublet lifetime model -> added (Gringarten-Sauty)",
                "no annual (365-day) driver or dispatch -> added",
                "brine properties not configurable in wells -> added 'pvt' override",
            ],
        }
        return _out(s, "list_gemini_models", {}, res)

    def reservoir_at_depth(depth_m: float) -> str:
        """Reservoir temperature, pressure and productivity index at a well depth (TVD, m)."""
        rs = reservoir_state(s.svc.brief, depth_m)
        res = dict(rs.__dict__)
        t_sup = s.svc.demand.heating_supply_c
        if rs.temperature_c < t_sup + 3.0:  # below supply + heat-exchanger approach
            res["note"] = (
                f"{rs.temperature_c:.0f} C is below the {t_sup:.0f} C heating supply: no "
                f"direct supply "
                "from this depth; it needs a heat pump/boiler or deeper wells (reference 2500 m; "
                "screen 2000-3500 m)"
            )
        return _out(s, "reservoir_at_depth", {"depth_m": depth_m}, res)

    def well_performance(depth_m: float, flow_m3h: float) -> str:
        """GEMINI well model (DPDT + IPR + injector nodal solve) for one doublet at a flow:
        wellhead temperature, ESP and injection pump power, drawdown, max thermal power."""
        b = s.svc.brief
        ws = WellSettings.from_brief(b)
        p = producer_point(b, depth_m, flow_m3h, ws)
        inj_t = p.wellhead_temperature_c - b.constraints["max_brine_cooling_k"]
        i = injector_point(b, depth_m, flow_m3h, inj_t, ws)
        cp = b.assumption("brine_specific_heat_j_per_kgk")
        q_max = (
            flow_m3h
            / 3600
            * b.brine["density_kg_m3"]
            * cp
            * b.constraints["max_brine_cooling_k"]
            / 1e6
        )
        res = {
            "producer": p.as_dict(),
            "injector": i.as_dict(),
            "max_thermal_power_mw_at_40K": round(q_max, 3),
            "gas_fuel_mw_if_separated": round(
                flow_m3h / 3600 * gas_properties(b).fuel_energy_mj_per_m3, 3
            ),
        }
        c = b.constraints
        if not c["min_flow_m3h_per_doublet"] <= flow_m3h <= c["max_flow_m3h_per_doublet"]:
            res["constraint_violation"] = (
                f"flow {flow_m3h:g} m3/h is outside the brief's hard limit "
                f"{c['min_flow_m3h_per_doublet']:g}-{c['max_flow_m3h_per_doublet']:g} "
                "m3/h per doublet: not a valid design point"
            )
        return _out(s, "well_performance", {"depth_m": depth_m, "flow_m3h": flow_m3h}, res)

    def evaluate_design(
        well_depth_m: float = 2500.0,
        n_doublets: int = 2,
        max_flow_m3h: float = 300.0,
        dh_return_temperature_c: float = 50.0,
        heat_pump_mw: float = 0.0,
        absorption_chiller_mw: float = 0.0,
        electric_chiller_mw: float = 10.0,
        backup_boiler_mw: float = 10.0,
        backup_fuel: Literal["gas", "electric"] = "gas",
        gas_handling: Literal[
            "separate_and_burn", "keep_in_solution_reinject"
        ] = "keep_in_solution_reinject",
    ) -> str:
        """Simulate one full year (365 daily steps, GEMINI physics) for a design and return
        KPIs, economics and constraint checks. Capacities in MW."""
        args = {
            k: v for k, v in locals().items() if k != "s"
        }  # locals() also holds the closure's session
        try:
            spec = DesignSpec(**args)
        except Exception as exc:
            return json.dumps({"error": f"invalid design: {exc}. Fix the fields and retry."})
        prev = s.evaluations.get(s.current_design) if s.current_design else None
        ev = s.remember(s.svc.evaluate(spec))
        res = ev.summary()
        if prev is not None and prev.spec.key() != spec.key():
            # what-if: show what changed, so a dropped chiller is visible to the model (S5 qwen3:4b)
            old, new = prev.spec.model_dump(), spec.model_dump()
            res["changed_vs_previous"] = {
                k: [old[k], new[k]] for k in args if old.get(k) != new.get(k)
            }
            if not res["feasible"] and prev.summary()["feasible"]:
                res["note"] = (
                    f"previous design {prev.spec.key()} was feasible; for a what-if, keep "
                    f"unchanged "
                    "every field the user did not ask to change"
                )
        s.current_design = spec.key()
        return _out(s, "evaluate_design", args, res)

    def search_designs(
        objective: Literal["min_lcoe", "balanced", "min_co2"] = "balanced",
        depths_m: FloatList = None,
        doublets: IntList = None,
        heat_pumps_mw: FloatList = None,
    ) -> str:
        """Deterministic optimisation over depth, doublets, heat pump, cooling mix, gas handling
        and DH return temperature (boilers right-sized incl. N-1). Returns top designs + Pareto.
        objective: balanced = cost AND CO2 matter (default; CO2 priced at a shadow price),
        min_lcoe = cheapest only, min_co2 = lowest emissions only (cost secondary).
        The standard grid (2200-3400 m, 1-3 doublets, heat pump 0-15 MW) is always searched;
        depths_m / doublets / heat_pumps_mw only ADD extra candidates."""
        import inspect

        grid = {
            k: v.default
            for k, v in inspect.signature(search).parameters.items()
            if k in ("depths", "doublets", "heat_pumps")
        }
        kw = {"objective": objective}
        for key, extra, lo, hi in (
            ("depths", depths_m, 1500, 4000),
            ("doublets", doublets, 1, 3),
            ("heat_pumps", heat_pumps_mw, 0, 30),
        ):
            add = [x for x in (extra or []) if lo <= float(x) <= hi]
            kw[key] = tuple(sorted(set(grid[key]) | set(add)))
        out = search(s.svc, **kw)
        for ev in out["ranked"]:
            s.remember(ev)
        s.current_design = out["best"].spec.key()
        res = {
            "objective": objective,
            "designs_evaluated": out["n_evaluated"],
            "top": [_brief_summary(ev) for ev in out["ranked"][:5]],
            "pareto_lcoe_vs_co2": [_brief_summary(ev) for ev in out["pareto"]],
        }
        if objective != "balanced":  # make the price of the chosen objective explicit
            best = out["best"]
            bal = min(out["ranked"], key=lambda ev: score(ev, "balanced"))
            if bal.spec.key() != best.spec.key():
                d_lcoe = best.economics["lcoe_eur_per_mwh"] - bal.economics["lcoe_eur_per_mwh"]
                d_co2 = bal.kpis["co2_t"] - best.kpis["co2_t"]
                energy_mwh = (bal.kpis["heat_demand_gwh"] + bal.kpis["cool_demand_gwh"]) * 1000
                price = s.svc.econ["values"]["co2_eur_per_t"]
                res["trade_off_vs_balanced"] = {
                    "balanced_design": _brief_summary(bal),
                    "lcoe_difference_eur_per_mwh": round(d_lcoe, 2),
                    "co2_difference_t": round(-d_co2),
                    "cost_per_t_co2_avoided_eur": (
                        round(d_lcoe * energy_mwh / d_co2) if d_co2 > 0 else None
                    ),
                    "assumed_co2_price_eur_per_t": price,
                    "note": (
                        "the balanced design is the economic optimum with CO2 priced at 200 EUR/t; "
                        "present it unless the user explicitly accepts any cost for lower CO2"
                        if objective == "min_co2"
                        else "the balanced design cuts CO2 at a cost below 200 EUR/t avoided"
                    ),
                }
        return _out(s, "search_designs", {k: v for k, v in kw.items()}, res)

    def compare_designs(design_ids: list[str]) -> str:
        """Side-by-side KPIs of already evaluated designs."""
        rows = [s.design(i).summary() for i in design_ids]
        return _out(s, "compare_designs", {"design_ids": design_ids}, {"designs": rows})

    def stress_test_design(
        design_id: str,
        scenario: Literal["doublet_trip_on_peak_day", "demand_plus_10", "demand_plus_20"],
    ) -> str:
        """Stress a design: unplanned doublet trip on the peak heating day, or demand growth."""
        ev = s.design(design_id)
        res = stress_test(s.svc, ev.spec, scenario)
        return _out(s, "stress_test_design", {"design_id": design_id, "scenario": scenario}, res)

    def uncertainty_analysis(design_id: str, samples: int = 30) -> str:
        """Monte Carlo over geothermal gradient, permeability, demand, heat-pump efficiency and
        prices: P10/P50/P90 of LCOE, CO2 and the probability that demand is fully met.
        5-60 samples (each is a full annual simulation)."""
        ev = s.design(design_id)
        n = max(5, min(int(samples), 60))
        res = monte_carlo(s.svc, ev.spec, n=n)
        if n != int(samples):
            res["note"] = f"{int(samples)} samples requested, {n} run (limit 5-60); report {n}"
        return _out(s, "uncertainty_analysis", {"design_id": design_id, "samples": samples}, res)

    def add_capacity_margin(
        design_id: str,
        margin_pct: float = 10.0,
        part: Literal["cooling", "heating", "both"] = "both",
    ) -> str:
        """Scale the chillers (part="cooling"), the backup boiler (part="heating") or both by a margin and  # noqa: E501
        re-evaluate. Use the part verify_design reports as failing; do not oversize the other."""
        ev = s.design(design_id)
        f = 1 + margin_pct / 100
        up = lambda x: math.ceil(x * f * 2) / 2  # noqa: E731  half-MW steps
        spec = ev.spec.model_copy(
            update={
                "electric_chiller_mw": (
                    up(ev.spec.electric_chiller_mw)
                    if part != "heating"
                    else ev.spec.electric_chiller_mw
                ),
                "backup_boiler_mw": (
                    up(ev.spec.backup_boiler_mw) if part != "cooling" else ev.spec.backup_boiler_mw
                ),
            }
        )
        new = s.remember(s.svc.evaluate(spec))
        s.current_design = spec.key()
        return _out(
            s,
            "add_capacity_margin",
            {"design_id": design_id, "margin_pct": margin_pct, "part": part},
            new.summary(),
        )

    def sensitivity_analysis(design_id: str) -> str:
        """Tornado: LCOE and CO2 of a design when each main uncertain input (drilling cost, prices,
        discount rate, gradient, permeability, demand) is set to its low/high value."""
        from gemini_agent.sensitivity import tornado

        res = tornado(s.svc, s.design(design_id).spec)
        rows = [
            {
                k: r[k]
                for k in ("label", "low", "high", "lcoe_low", "lcoe_high", "co2_low", "co2_high")
            }
            for r in res["rows"]
        ]
        return _out(
            s,
            "sensitivity_analysis",
            {"design_id": design_id},
            {
                "base_lcoe": res["base_lcoe"],
                "base_co2_t": res["base_co2_t"],
                "ranked_by_lcoe_swing": rows,
            },
        )

    def break_even_analysis(
        design_a: str,
        design_b: str,
        input_name: Literal[
            "well_cost_eur_per_m",
            "electricity_eur_per_mwh",
            "gas_eur_per_mwh",
            "co2_eur_per_t",
            "discount_rate",
            "heat_pump_capex_eur_per_mw",
            "gradient_c_per_km",
            "permeability_md",
            "demand_scale",
        ],
        low: float,
        high: float,
    ) -> str:
        """Value of one input at which two designs have equal LCOE (when would the decision "
        "flip?)."""
        from gemini_agent.sensitivity import break_even

        res = break_even(
            s.svc, s.design(design_a).spec, s.design(design_b).spec, input_name, low, high
        )
        return _out(
            s,
            "break_even_analysis",
            {
                "design_a": design_a,
                "design_b": design_b,
                "input_name": input_name,
                "low": low,
                "high": high,
            },
            res,
        )

    def seasonal_balance(design_id: str) -> str:
        """Monthly unused geothermal capacity vs boiler heat of a design (input for storage "
        "screening)."""
        ev = s.design(design_id)
        r, b = ev.result, s.svc.brief
        cp = b.assumption("brine_specific_heat_j_per_kgk")
        q_max = (
            ev.spec.max_flow_m3h
            / 3600
            * b.brine["density_kg_m3"]
            * cp
            * b.constraints["max_brine_cooling_k"]
            / 1e6
        )
        months = {}
        for i, (date, d) in enumerate(zip(r.dates, r.days)):
            n_avail = sum(1 for a, z in r.windows if not (a <= i < z))
            used = d.q_hex + max(0.0, d.q_hp - d.hp_el) + d.q_abs_gen
            m = months.setdefault(int(date[5:7]), [0.0, 0.0])
            m[0] += max(0.0, n_avail * q_max - used) * 24 / 1000
            m[1] += d.q_boiler * 24 / 1000
        summer = sum(v[0] for k, v in months.items() if 4 <= k <= 10)
        winter = sum(v[1] for k, v in months.items() if k <= 3 or k >= 11)
        res = {
            "summer_surplus_gwh": summer,
            "winter_boiler_gwh": winter,
            "annual_heat_gwh": ev.kpis["heat_demand_gwh"],
            "monthly_spare_and_boiler_gwh": {
                k: [round(v[0], 2), round(v[1], 2)] for k, v in sorted(months.items())
            },
        }
        return _out(s, "seasonal_balance", {"design_id": design_id}, res)

    def generate_model(spec_json: str | dict) -> str:
        """Model Forge: create a NEW GEMINI component from a declarative JSON spec (inputs, parameters,  # noqa: E501
        outputs as math expressions, invariants, tests). It is validated, compiled, unit-tested and
        registered only if the tests pass. Read skill model-forge first."""
        from gemini_agent.forge import forge

        res = forge(spec_json)
        return _out(s, "generate_model", {"spec_name": res.get("model_type", "?")}, res)

    def run_model(model_type: str, inputs: dict, parameters: dict | None = None) -> str:
        """Evaluate any registered GEMINI component once (including models created by "
        "generate_model)."""
        from gemini_agent.forge import run_model as _rm

        res = _rm(model_type, inputs, parameters)
        return _out(
            s,
            "run_model",
            {"model_type": model_type, "inputs": inputs, "parameters": parameters or {}},
            res,
        )

    def fetch_weather(
        location: str = "",
        latitude: float | None = None,
        longitude: float | None = None,
        reference_year: int | None = None,
    ) -> str:
        """Design input only: PAST-year daily weather of the plant site (ERA5 archive) to set
        cooling-tower water temperatures for the simulations. Not a forecast: never use it to answer
        weather questions. Leave latitude/longitude empty if the site is unknown (documented
        default).
        """
        import datetime

        from gemini_agent.physics.weather import fetch_weather as _fw

        b, notes = s.svc.brief, []
        if (
            latitude is None
            or longitude is None
            or (abs(latitude) < 1e-9 and abs(longitude) < 1e-9)
        ):
            latitude, longitude = b.assumption("default_site_latitude"), b.assumption(
                "default_site_longitude"
            )
            if location and location.strip():  # a place name without coordinates is not a site
                notes.append(
                    f"'{location}' has no coordinates and is NOT in the brief: ignored; the "
                    "documented default site (Delft, NL) is used instead"
                )
            else:
                notes.append(
                    "site not given: documented default site used (assumption, weather only)"
                )
            location = "default proxy site (Delft, NL)"
        last_full_year = datetime.date.today().year - 1
        if reference_year is None or not 1950 <= int(reference_year) <= last_full_year:
            if reference_year is not None:
                notes.append(
                    f"reference_year {reference_year} has no complete record; default year used"
                )
            reference_year = int(b.assumption("default_weather_year"))
        elif int(reference_year) != int(b.assumption("default_weather_year")):
            notes.append(
                f"reference_year {reference_year} chosen by the agent; the documented default is "
                f"{int(b.assumption('default_weather_year'))}"
            )
        wx = _fw(location or "site", latitude, longitude, int(reference_year))
        if s.svc.weather is not None and s.svc.weather.key() == wx.key():
            notes.append("this weather was already loaded at session start (documented default)")
        s.svc.weather = wx
        res = wx.summary()
        if notes:
            res["assumptions"] = notes
        return _out(
            s,
            "fetch_weather",
            {
                "location": location,
                "latitude": latitude,
                "longitude": longitude,
                "reference_year": reference_year,
            },
            res,
        )

    def ask_user(question: str, default_if_no_answer: str) -> str:
        """Ask the human for a missing or ambiguous input. In batch mode the default is used and
        logged as an assumption."""
        if s.mode == "auto" or s.question_budget <= 0:
            s.assumptions_used.append({"question": question, "assumed": default_if_no_answer})
            why = (
                "batch mode, no user"
                if s.mode == "auto"
                else "the user already answered your question this turn: do not ask again"
            )
            return _out(
                s,
                "ask_user",
                {"question": question},
                {
                    "answer": f"({why}) use default: {default_if_no_answer}",
                    "logged_as_assumption": True,
                },
            )
        s.question_budget -= 1
        s.pending_question = question
        return json.dumps(
            {
                "status": "question shown to the user; STOP now and wait for the reply",
                "question": question,
            }
        )

    def check_numbers(text: str) -> str:
        """Verifier: every number in the text must trace to a recorded fact or the brief."""
        res = provenance_check(text, s.ledger)
        return json.dumps(res)

    def export_gemini_project(
        design_id: str, day: Literal["peak_heating", "peak_cooling", "shoulder"] = "peak_heating"
    ) -> str:
        """Compile one doublet of a design into a native GEMINI simulator project JSON for a
        representative day, run it in GEMINI's Solver, and compare with the annual screening."""
        from gemini_agent.physics.gemini_project import verify_day

        ev = s.design(design_id)
        dem = s.svc.demand
        idx = {
            "peak_heating": max(range(365), key=lambda i: dem.heating_mw[i]),
            "peak_cooling": max(range(365), key=lambda i: dem.cooling_mw[i]),
            "shoulder": min(range(365), key=lambda i: abs(dem.heating_mw[i] - 12.0)),
        }[day]
        v = verify_day(ev, idx, s.svc.brief)
        path = s.run_dir / f"gemini_project_{design_id}_{day}.json"
        path.write_text(json.dumps(v["project"], indent=2, default=str))
        res = {k: v[k] for k in ("date", "screening", "gemini_solver", "deviation", "consistent")}
        res.update(
            {
                "project_file": str(path),
                "components": list(v["project"]["components"]),
                "n_connections": len(v["project"]["connections"]),
            }
        )
        return _out(s, "export_gemini_project", {"design_id": design_id, "day": day}, res)

    def save_design_package(design_id: str) -> str:
        """Write the design package (spec, KPIs, economics, checks, daily series CSV) to disk."""
        ev = s.design(design_id)
        d = s.run_dir / f"design_{design_id}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "spec.json").write_text(ev.spec.model_dump_json(indent=2))
        (d / "summary.json").write_text(
            json.dumps(
                _plain({"kpis": ev.kpis, "economics": ev.economics, "checks": ev.checks}),
                indent=2,
                default=str,
            )
        )
        cols = [
            "q_hex",
            "q_hp",
            "q_boiler",
            "q_abs_cool",
            "q_ech_cool",
            "unmet_heat",
            "unmet_cool",
            "flow_per_doublet_m3h",
            "n_on",
            "wellhead_t_c",
            "injection_t_c",
            "brine_dt_k",
            "hp_cop",
            "el_total",
            "co2_t",
        ]
        lines = ["date,heat_demand_mw,cool_demand_mw," + ",".join(cols)]
        r = ev.result
        for i, day in enumerate(r.days):
            vals = [getattr(day, c) for c in cols]
            lines.append(
                f"{r.dates[i]},{r.heat_mw[i]},{r.cool_mw[i]}," + ",".join(f"{v:.4f}" for v in vals)
            )
        (d / "daily.csv").write_text("\n".join(lines))
        return _out(
            s, "save_design_package", {"design_id": design_id}, {"path": str(d), "files": 3}
        )

    def verify_design(design_id: str) -> str:
        """All robustness and verification checks of a design in ONE call: stress tests (doublet trip  # noqa: E501
        on the peak day, demand +10 %), Monte Carlo uncertainty, sensitivity ranking, GEMINI-solver
        check of the peak day, and the saved design package. Each part is recorded as its own fact.
        """
        part = lambda out: json.loads(out)  # noqa: E731
        stress = {
            sc: part(stress_test_design(design_id, sc))
            for sc in ("doublet_trip_on_peak_day", "demand_plus_10")
        }
        unc = part(uncertainty_analysis(design_id))
        sens = part(sensitivity_analysis(design_id))
        gem = part(export_gemini_project(design_id))
        pkg = part(save_design_package(design_id))
        # the peak-day trip reports "survives", demand growth reports "feasible"
        passed = {k: bool(v.get("survives", v.get("feasible"))) for k, v in stress.items()}
        failed = [k for k, ok_ in passed.items() if not ok_] + (
            [] if gem.get("consistent") else ["gemini_solver"]
        )
        short_heat = any(
            not passed[k] and (v.get("unmet_heat_mw") or v.get("unmet_heat_mwh"))
            for k, v in stress.items()
        )
        short_cool = any(not passed[k] and v.get("unmet_cool_mwh") for k, v in stress.items())
        part = (
            "both"
            if short_heat and short_cool
            else "heating" if short_heat else "cooling" if short_cool else "both"
        )
        ok = not failed
        return json.dumps(
            {
                "design_id": design_id,
                "stress": {
                    k: {
                        "fact_id": v.get("fact_id"),
                        "survives": passed[k],
                        **{
                            x: v[x]
                            for x in (
                                "unmet_heat_mw",
                                "boiler_mw",
                                "unmet_heat_mwh",
                                "unmet_cool_mwh",
                            )
                            if x in v
                        },
                    }
                    for k, v in stress.items()
                },
                "uncertainty": {
                    x: unc.get(x)
                    for x in (
                        "fact_id",
                        "samples",
                        "lcoe_eur_per_mwh",
                        "co2_t",
                        "probability_demand_fully_met",
                    )
                },
                "sensitivity": {
                    "fact_id": sens.get("fact_id"),
                    "top_lcoe_drivers": [
                        r["label"] for r in sens.get("ranked_by_lcoe_swing", [])[:3]
                    ],
                },
                "gemini_solver": {x: gem.get(x) for x in ("fact_id", "consistent")},
                "package": {x: pkg.get(x) for x in ("fact_id", "path")},
                "all_passed": ok,
                "failed": failed,
                "next": (
                    "write the final answer"
                    if ok
                    else f"failed: {', '.join(failed)} (short of {part}); add_capacity_margin(design_id, part=\"{part}\"), "  # noqa: E501
                    "then verify_design on the new design_id"
                ),
            },
            separators=(",", ":"),
        )

    fns = [
        get_brief,
        analyze_demand,
        list_gemini_models,
        reservoir_at_depth,
        well_performance,
        evaluate_design,
        search_designs,
        compare_designs,
        stress_test_design,
        uncertainty_analysis,
        add_capacity_margin,
        sensitivity_analysis,
        break_even_analysis,
        seasonal_balance,
        generate_model,
        run_model,
        fetch_weather,
        ask_user,
        check_numbers,
        export_gemini_project,
        save_design_package,
        verify_design,
    ]
    tools = []
    for f in fns:
        # interactive mode: asking the user ends the turn deterministically (small models keep re-asking)  # noqa: E501
        direct = f is ask_user and s.mode != "auto"
        tool = StructuredTool.from_function(
            _safe(f, s), handle_validation_error=_tool_error, return_direct=direct
        )
        tool.args_schema = _lenient(tool.args_schema)
        tools.append(tool)
        if f is ask_user:
            s.ask_tool = tool
    return tools


def _lenient(schema):
    """Unwrap {"value": 52.01} / {"year": 2023} sent for scalar fields (frequent with 1.5-4B "
    "models)."""

    class Lenient(schema):
        @model_validator(mode="before")
        @classmethod
        def _unwrap(cls, data):
            if not isinstance(data, dict):
                return data
            out = {}
            for k, v in data.items():
                f = cls.model_fields.get(k)
                ann = str(f.annotation) if f is not None else ""
                if (
                    isinstance(v, dict)
                    and len(v) == 1
                    and f is not None
                    and "dict" not in ann
                    and "list" not in ann
                ):
                    v = next(iter(v.values()))
                out[k] = v
            return out

    Lenient.__name__ = schema.__name__
    Lenient.__doc__ = schema.__doc__
    return Lenient


def _tool_error(exc: Exception) -> str:
    """Tool failures go back to the model as data (it can retry or ask), never crash the run."""
    return json.dumps(
        {
            "error": f"{type(exc).__name__}: {str(exc)[:400]}",
            "hint": "check the arguments against the tool description, then retry or ask_user",
        }
    )


def _safe(fn, session: Session):
    """Errors become data; an identical repeat of the previous call is answered without "
    "re-running."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        sig = (fn.__name__, json.dumps([args, kwargs], sort_keys=True, default=str))
        if sig == session.last_call:
            return json.dumps(
                {
                    "note": "identical to your previous call, so the result is the same as before. "
                    "Do something different: change the arguments, use another tool, "
                    "or give your answer."
                }
            )
        session.last_call = sig
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 -- reported to the model, logged in the trace
            return _tool_error(exc)

    return wrapper


def _brief_summary(ev: Evaluation) -> dict:
    k, e = ev.kpis, ev.economics
    return {
        "design_id": ev.spec.key(),
        "label": ev.spec.label(),
        "feasible": ev.checks["passed"],
        "lcoe_eur_per_mwh": e["lcoe_eur_per_mwh"],
        "co2_t": k["co2_t"],
        "capex_meur": e["capex_total_meur"],
        "geothermal_share_pct": k["geothermal_share_of_heat_pct"],
    }
