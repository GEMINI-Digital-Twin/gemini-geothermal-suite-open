"""Scripted evidence scenarios (S1-S5) -> runs/<session>/ for the evidence appendix.

  PYTHONPATH=src python -m gemini_agent.scenarios <model> <scenario> [profile]

S1 full design (batch)          : complete autonomous design, defaults logged as assumptions
S2 incomplete request           : vague request -> agent asks; scripted human reply; agent designs
S3 off-topic question           : scope guard, no tools
S4 infeasible request           : 500 m3/h per doublet -> refuses with the hard limit
S5 follow-up what-ifs           : after a design: N-1 trip on the coldest day; deeper wells vs
heat pump
S6 missing model (Model Forge)  : seasonal storage question with the storage model removed
beforehand ->
                                  the agent must detect the gap and generate, test and use a
                                  new component
"""

from __future__ import annotations

import contextlib
import json
import shutil
import sys
from pathlib import Path

from gemini_agent.runner import AgentRunner

ROOT = Path(__file__).resolve().parents[2]
GENERATED = [
    ROOT / "src" / "gemini_model" / "generated" / "ht_ates_screening.py",
    ROOT / "unit_test" / "gemini_model" / "generated" / "test_ht_ates_screening.py",
]

SCENARIOS = {
    "S1": (
        "auto",
        [
            "Design a geothermal heating and cooling system for the supplied 2027 demand profiles. "
            "Balance cost and CO2 and explain every major decision."
        ],
    ),
    "S2": (
        "interactive",
        [
            "Design a heating and cooling system for our district.",
            "Prioritise low CO2 at reasonable cost. District heating return is 50 C. "
            "Go ahead with the design.",
        ],
    ),
    "S3": ("interactive", ["What will the weather be in Delft tomorrow?"]),
    "S4": (
        "interactive",
        ["Run each doublet at 500 m3/h so we need fewer wells, and evaluate that design."],
    ),
    "S5": (
        "interactive",
        [
            "Evaluate 2 doublets at 3100 m with a 10 MW electric chiller and an 18 MW gas "
            "backup boiler, gas reinjected.",
            "What happens if one doublet trips on the coldest day of the year?",
            "Why not use 2500 m wells with a heat pump instead of drilling to 3100 m?",
        ],
    ),
    "S6": (
        "interactive",
        [
            "Evaluate 1 doublet at 3100 m with a 10 MW electric chiller and a 31.5 MW gas backup "
            "boiler, gas reinjected.",
            "Our geothermal supply is largest in summer, when the district needs little heat. "
            "Could "
            "we store that summer surplus underground and use it in winter? Quantify what seasonal "
            "storage would do to the boiler heat of this design.",
        ],
    ),
}


@contextlib.contextmanager
def without_generated_models():
    """S6: hide the previously generated storage model so the agent faces a real capability gap;
    whatever the agent generates is kept as evidence and the originals are restored afterwards."""
    backup = {p: p.with_suffix(p.suffix + ".s6bak") for p in GENERATED if p.exists()}
    for p, b in backup.items():
        p.rename(b)
    try:
        yield
    finally:
        for p, b in backup.items():
            if (
                p.exists()
            ):  # the agent generated a model of the same name: keep it next to the original
                p.rename(p.with_suffix(".agent_generated.py.txt"))
            b.rename(p)


def run(model: str, scenario: str, profile: str = "deep") -> str:
    """Run one scenario; returns the session directory."""
    mode, turns = SCENARIOS[scenario]
    from gemini_agent.router import from_env

    with without_generated_models() if scenario == "S6" else contextlib.nullcontext():
        r = AgentRunner(
            model=model, profile=profile, mode=mode, router=from_env(model)
        )  # GEODESIGN_ROUTER=1
        meta = json.loads((r.run_dir / "meta.json").read_text())
        meta["scenario"] = scenario
        (r.run_dir / "meta.json").write_text(json.dumps(meta, indent=2))
        for msg in turns:
            t = r.ask(msg)
            print(
                f"[{scenario}] {t['llm_calls']} calls, "
                f"{t['prompt_tokens']}+{t['completion_tokens']} tok, "
                f"{t['seconds']} s, tools={t['tool_calls']}\n{t['answer'][:1500]}\n",
                flush=True,
            )
        if (
            scenario == "S6"
        ):  # keep what the Forge produced with the session (originals are .s6bak now)
            for d in (GENERATED[0].parent, GENERATED[1].parent):
                for p in d.glob("*.py"):
                    if p.stem != "__init__":
                        shutil.copy(p, r.run_dir / f"agent_generated_{p.name}")
    return str(r.run_dir)


if __name__ == "__main__":
    print(run(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "deep"))
