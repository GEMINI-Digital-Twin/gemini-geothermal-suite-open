"""Request intake: the agent checks a design request before it runs anything.

The hackathon committee asked for evidence that the agent can handle incomplete or irrelevant
requests: identify missing inputs, refuse what is out of scope, and flag inconsistencies between
the stated inputs and the physics. This module is that gate. It is deterministic so the evidence
is reproducible; the Claude-orchestrated mode calls it as its first tool.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .spec import SPEC

REQUIRED_INPUTS = {
    "heating_demand_csv": "daily heating demand profile (date, MWth)",
    "cooling_demand_csv": "daily cooling demand profile (date, MWcool)",
    "supply_temperature_heating_c": "supply temperature to the heating network",
    "supply_temperature_cooling_c": "supply temperature to the cooling network",
    "reservoir_depth_m": "reservoir midpoint depth",
    "geothermal_gradient_c_per_km": "geothermal gradient (or a reservoir temperature)",
    "reservoir_pressure_bar": "reservoir pressure (or 'hydrostatic')",
    "permeability_md": "reservoir permeability",
    "brine_glr_nm3_per_m3": "gas-liquid ratio of the brine (sets the ESP intake constraint)",
}
OPTIONAL_INPUTS = {
    "max_flow_m3_h_per_doublet": "defaults to the challenge cap of 300 m3/h",
    "max_brine_cooling_c": "defaults to the challenge cap of 40 C",
    "operating_days_per_doublet": "defaults to 330",
    "district_return_c": "defaults to 60 C",
    "electricity_price_eur_mwh": "defaults to the indicative cost model",
}
IN_SCOPE = ("heating", "cooling", "district", "doublet", "geothermal", "heat pump", "chiller", "brine", "esp", "well")
OUT_OF_SCOPE = {
    r"\b(orc|organic rankine|turbine|power plant|electricity generation|mwe)\b": "electricity generation: this agent designs direct-use heating and cooling systems only",
    r"\b(oil|gas field|petroleum|frack|hydrocarbon)\b": "hydrocarbon production: outside the geothermal direct-use scope",
    r"\b(stock|crypto|weather|recipe|football|movie|song)\b": "not an engineering design question",
    r"\b(solar|wind farm|nuclear|hydrogen|battery storage)\b": "another energy source: the twin only models the geothermal plant; it can be added as a component model if you supply one",
}


@dataclass
class IntakeReport:
    status: str                              # ok | incomplete | out_of_scope | inconsistent
    missing: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    reply: str = ""

    def markdown(self) -> str:
        L = [f"**Agent status: {self.status}**", ""]
        if self.reply:
            L += [self.reply, ""]
        if self.missing:
            L += ["Missing inputs I need before I can size anything:"] + [f"- {m}" for m in self.missing] + [""]
        if self.issues:
            L += ["Inconsistencies I found:"] + [f"- {m}" for m in self.issues] + [""]
        if self.assumptions:
            L += ["Assumptions I will use unless you object:"] + [f"- {m}" for m in self.assumptions] + [""]
        if self.questions:
            L += ["Questions back to you:"] + [f"- {m}" for m in self.questions] + [""]
        return "\n".join(L)


def check_request(request: dict, text: str = "") -> IntakeReport:
    """Validate a design request. ``request`` holds the inputs the user supplied; ``text`` is the
    free-text ask, used for the scope check."""
    t = text.lower()
    # ---- scope
    for pat, why in OUT_OF_SCOPE.items():
        if re.search(pat, t) and not any(k in t for k in ("heating", "cooling", "district")):
            return IntakeReport("out_of_scope", reply=(
                f"I cannot help with that request: {why}. I design and validate deep-geothermal heating and cooling "
                "systems for a district using the GEMINI digital twin. If you have a heating and cooling demand profile "
                "and reservoir data, send those and I will start."))
    # ---- completeness
    missing = [f"{k}: {v}" for k, v in REQUIRED_INPUTS.items() if request.get(k) in (None, "", [])]
    for k in ("heating_demand_csv", "cooling_demand_csv"):
        p = request.get(k)
        if p and not Path(str(p)).exists():
            missing.append(f"{k}: file '{p}' not found")
    assumptions = [f"{k}: {v}" for k, v in OPTIONAL_INPUTS.items() if request.get(k) in (None, "")]
    rep = IntakeReport("incomplete" if missing else "ok", missing=missing, assumptions=assumptions)
    if missing:
        rep.reply = ("I can start the design loop once the inputs below are supplied. Without the cooling profile I "
                     "cannot size the chiller train or the brine split, and without supply temperatures I cannot decide "
                     "whether direct heat exchange is possible or a heat pump is needed.")
        rep.questions.append("Shall I proceed with the heating side only and report cooling as 'not sized'?")
        return rep
    # ---- physical consistency
    depth = float(request["reservoir_depth_m"]); grad = float(request["geothermal_gradient_c_per_km"])
    t_calc = SPEC.reservoir.surface_temperature_c + grad * depth / 1000.0
    t_given = request.get("reservoir_temperature_c")
    if t_given is not None and abs(float(t_given) - t_calc) > 10.0:
        rep.issues.append(f"stated reservoir temperature {float(t_given):.0f} C does not match {grad:.0f} C/km x {depth:.0f} m "
                          f"+ {SPEC.reservoir.surface_temperature_c:.0f} C surface = {t_calc:.0f} C; one of them is wrong")
        rep.questions.append("Which should I trust: the temperature log or the gradient? This decides whether a heat pump is needed.")
    sup = float(request["supply_temperature_heating_c"])
    if t_calc - 3.0 - 3.0 < sup:   # ~3 C wellbore loss, 3 C HX approach
        rep.assumptions.append(f"wellhead brine at {depth:.0f} m (~{t_calc - 3:.0f} C) is below the {sup:.0f} C supply + 3 C approach: "
                               "direct heat exchange is impossible there, so I will size a heat pump and also test deeper wells "
                               "(the brief allows other depths with hydrostatic pressure and the given gradient)")
    pres = request.get("reservoir_pressure_bar")
    if isinstance(pres, (int, float)) and abs(float(pres) - 1030 * 9.81 * depth / 1e5) > 60:
        rep.issues.append(f"reservoir pressure {float(pres):.0f} bar is far from hydrostatic at {depth:.0f} m; confirm it")
    glr = float(request["brine_glr_nm3_per_m3"])
    if glr > 0:
        rep.assumptions.append(f"GLR {glr} Nm3/m3 implies a bubble point of roughly {glr * 0.8 / 0.022:.0f} bar; the ESP intake will be kept above it")
    if rep.issues:
        rep.status = "inconsistent"
        rep.reply = "I found inputs that contradict each other. I will not size the plant until they are resolved, because the design flips between a heat-pump and a direct-supply system depending on the answer."
    else:
        rep.reply = "Inputs are complete and consistent. Starting the propose - evaluate - diagnose - repair loop."
    return rep
