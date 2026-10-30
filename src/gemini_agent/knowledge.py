"""What the agent knows before it calls any tool.

The brief (``gemini_design.challenge.CHALLENGE``), an assumptions ledger
that gives every assumed value a source and a confidence, the list of
inputs the brief does not give (which the agent must state or ask
about), and the system prompt.
"""

from gemini_design.challenge import ASSUMPTIONS, CHALLENGE

# Source and confidence of each assumption (high / medium / low).
ASSUMPTION_META = {
    "heating_return_c": ("not in brief; typical Dutch district heating 40-50 degC", "low"),
    "cooling_return_c": ("not in brief; typical district cooling dT 6 K", "low"),
    "cooling_water_c": ("dry cooler / tower in NL summer", "medium"),
    "brine_cp": ("saline water at ~90 degC", "high"),
    "water_density": ("physics", "high"),
    "water_cp": ("physics", "high"),
    "well_inner_diameter_m": ("8.5 in production casing, NL geothermal practice", "medium"),
    "wellbore_radius_m": ("8.5 in hole", "medium"),
    "drainage_radius_m": ("half a typical doublet spacing", "medium"),
    "skin": ("undamaged well", "medium"),
    "well_roughness_m": ("new steel casing (GEMINI default 0.01 m is a rough open hole)", "high"),
    "producer_wellhead_pressure_bar": ("keeps CO2/CH4 in solution to the separator", "medium"),
    "esp_intake_pressure_min_bar": ("ESP vendor rule of thumb", "medium"),
    "surface_pressure_loss_bar": ("separator + filters + HEX", "medium"),
    "hex_ua_per_doublet_w_per_k": ("plate HEX sized for ~3 K approach", "medium"),
    "separator_temperature_drop_k": ("GEMINI separator default", "medium"),
    "boiler_efficiency": ("condensing gas boiler, LHV", "high"),
    "heat_pump_eta_lorenz": ("industrial heat pumps 0.45-0.55 of Lorenz", "medium"),
    "absorption_eta_rev": ("single-effect LiBr at low drive temperature", "low"),
    "absorption_cop_max": ("single-effect LiBr datasheets", "medium"),
    "electric_chiller_eta_carnot": ("screw/centrifugal chillers", "medium"),
    "electric_chiller_cop_max": ("datasheet cap", "medium"),
    "electric_chiller_evaporator_approach_k": ("chiller datasheets", "medium"),
    "electric_chiller_condenser_approach_k": ("dry cooler in summer, incl. water rise", "medium"),
    "electric_chiller_units": ("staged modules", "medium"),
    "chp_efficiency": ("gas engine, total fuel to heat + power", "medium"),
    "electricity_export_price_eur_per_mwh": ("NL spot average, team estimate", "low"),
    "chp_cost_eur_per_mw_el": ("gas engine on low-CV associated gas", "low"),
    "chiller_aux_power_fraction": ("pumps and fans", "medium"),
    "absorption_hot_dt_max_k": ("low-temperature generator design", "medium"),
    "electricity_price_eur_per_mwh": ("NL 2027 forward, team estimate", "low"),
    "gas_price_eur_per_mwh": ("TTF forward, team estimate", "low"),
    "co2_price_eur_per_t": ("EU ETS, team estimate", "low"),
    "electricity_emission_kg_per_kwh": ("GEMINI examples", "medium"),
    "natural_gas_emission_kg_per_gj": ("GEMINI examples (IPCC)", "high"),
    "well_cost_fixed_eur": ("NL geothermal well cost curves, team estimate", "low"),
    "well_cost_per_m_eur": ("NL geothermal well cost curves, team estimate", "low"),
    "surface_cost_per_doublet_eur": ("team estimate", "low"),
    "heat_pump_cost_eur_per_mw": ("large heat pumps 0.5-1 MEUR/MW", "low"),
    "boiler_cost_eur_per_mw": ("gas boilers", "medium"),
    "absorption_chiller_cost_eur_per_mw": ("LiBr chillers", "low"),
    "electric_chiller_cost_eur_per_mw": ("screw chillers", "medium"),
    "fixed_om_fraction": ("typical 2 % of CAPEX", "medium"),
    "discount_rate": ("real, utility project", "medium"),
    "lifetime_years": ("geothermal plant life", "medium"),
}

# Inputs the brief does not give. The agent states the assumption or asks.
GAPS = [
    "district heating return temperature (assumed 40 degC)",
    "district cooling return temperature (assumed 26 degC)",
    "what happens on the 35 days each doublet is down (assumed: backup boiler/chiller)",
    "energy prices, CO2 price and emission factors (assumed NL 2027 values)",
    "well and equipment costs (assumed cost curves)",
    "injector-side reservoir pressure (assumed equal to producer side)",
]

# Ranges for assumption overrides the agent may try (sensitivity, what-if).
ASSUMPTION_RANGES = {
    "heating_return_c": (25.0, 70.0),
    "cooling_return_c": (21.0, 32.0),
    "cooling_water_c": (15.0, 45.0),
    "electric_chiller_cop_max": (2.0, 10.0),
    "electric_chiller_eta_carnot": (0.2, 0.7),
    "chp_efficiency": (0.6, 0.95),
    "electricity_export_price_eur_per_mwh": (0.0, 300.0),
    "heat_pump_eta_lorenz": (0.3, 0.7),
    "absorption_cop_max": (0.4, 0.9),
    "electricity_price_eur_per_mwh": (20.0, 500.0),
    "gas_price_eur_per_mwh": (10.0, 200.0),
    "co2_price_eur_per_t": (0.0, 300.0),
    "well_cost_per_m_eur": (500.0, 5000.0),
    "well_cost_fixed_eur": (0.0, 1.0e7),
    "discount_rate": (0.0, 0.15),
    "hex_ua_per_doublet_w_per_k": (1.0e6, 1.0e7),
    "producer_wellhead_pressure_bar": (2.0, 30.0),
    "skin": (-3.0, 20.0),
}

CHALLENGE_RANGES = {
    "permeability_md": (10.0, 2000.0),
    "geothermal_gradient_c_per_km": (20.0, 45.0),
    "reservoir_thickness_m": (20.0, 400.0),
    "brine_viscosity": (0.2e-3, 1.5e-3),
}

GRADING = (
    "Judges score: 50 % agent (reasoning, choosing and running models, writing missing "
    "models, physics-validated not hallucinated) and 50 % a design that meets every "
    "day of heating and cooling demand in simulation. Bonus: uncertainty, "
    "techno-economics, new models, token efficiency."
)


def brief_summary():
    """Return the brief as a compact dict (values only from the official inputs)."""
    c = CHALLENGE
    return {
        "heating": "daily 2027 profile, peak 30.0 MW, 111.67 GWh/yr, supply 100 degC",
        "cooling": "daily 2027 profile, peak 10.0 MW, 23.74 GWh/yr, supply 20 degC",
        "reservoir": (
            f"{c['reservoir_depth_m']:.0f} m TVD midpoint, {c['reservoir_thickness_m']:.0f} m "
            f"thick, {c['geothermal_gradient_c_per_km']:.0f} degC/km from "
            f"{c['surface_temperature_c']:.0f} degC, {c['reservoir_pressure_bar']:.0f} bar, "
            f"{c['permeability_md']:.0f} mD; other depths allowed (hydrostatic)"
        ),
        "brine": "1030 kg/m3, 0.40 mPa.s, GLR 0.8 Nm3/m3, gas 80 % CH4 / 20 % CO2",
        "hard_rules": (
            "1-3 doublets; 50-300 m3/h per active doublet; brine cooled at most 40 K; "
            "pump efficiency 70 %; production = injection; each doublet runs at most "
            "330 days; demand met every day"
        ),
    }


def assumptions_ledger(overrides=None):
    """Return each assumption with value, source and confidence (overrides marked)."""
    overrides = overrides or {}
    out = {}
    for key, value in ASSUMPTIONS.items():
        source, confidence = ASSUMPTION_META.get(key, ("team estimate", "medium"))
        entry = {"value": overrides.get(key, value), "source": source, "confidence": confidence}
        if key in overrides:
            entry["source"] = "user/agent override"
        out[key] = entry
    return out


SYSTEM_PROMPT = """You are the GEMINI design agent for the SPE GeoHackathon 2026: design and
check a deep-geothermal heating AND cooling plant for an urban district.

How you work:
1. Reason briefly, then call tools. Every number you state must come from a tool
   result in this conversation (cite its run id, e.g. [R0003]) or from the brief.
   Never estimate or invent numbers. A physics gate checks every answer and rejects
   numbers it cannot trace to a run.
2. Start design questions with describe_inputs. If the question lacks something you
   need and the brief does not give it (see the input gaps), call ask_user with one
   short question and say which default you would use. Do not ask about things the
   brief gives.
3. Prefer one run_design or a small screen over many calls; results are summaries.
   Use sensitivity for uncertainty questions, cross_check to confirm a run with
   GEMINI's own Solver, write_model only when a needed component is missing.
4. If a question is unrelated to the geothermal plant, say so in one sentence and
   offer what you can do. Do not call tools for it.
5. Final answers: short, plain language, lead with the result, cite run ids, state
   key assumptions. Say when a design breaks a hard rule.

Brief: {brief}
Input gaps (assumed unless the user says otherwise): {gaps}
Grading: {grading}
Project notes from earlier sessions: {notes}
"""


def system_prompt(notes_text=""):
    """Return the system prompt with the brief, gaps and project notes filled in."""
    brief = "; ".join(f"{k}: {v}" for k, v in brief_summary().items())
    return SYSTEM_PROMPT.format(
        brief=brief,
        gaps="; ".join(GAPS),
        grading=GRADING,
        notes=notes_text or "none yet",
    )
