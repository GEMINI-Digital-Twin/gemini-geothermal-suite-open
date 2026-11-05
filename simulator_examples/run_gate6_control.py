"""Chance-level control for gate 6: how often does it accept a fabricated number?

Runs one design through the ToolBox (a full run summary is the evidence an answer is
checked against), then writes answers that quote invented numbers and counts how many
the gate lets through. Numbers are drawn at random in the range of typical KPIs
(13-60 with 1-2 decimals, 100-50,000 whole numbers), each one either bare or with a
unit (EUR/MWh, t CO2 per year, MWh). A gate at chance would accept nearly all; the
lower the rate the better. Prints the acceptance rate per kind.

    PYTHONPATH=src python simulator_examples/run_gate6_control.py [--n 400]
"""

import argparse
import json
import random
import shutil
import warnings
from pathlib import Path

from gemini_agent.memory import ProjectNotes, RunLedger
from gemini_agent.physics_gate import check_answer
from gemini_agent.tools import ToolBox
from gemini_design.challenge import ASSUMPTIONS, CHALLENGE, load_demand

WS = Path(__file__).parent / "outputs" / "gate6_control_ws"
DESIGN = {"n_doublets": 2, "depth_m": 3100, "upgrade": "boiler", "cooling": "electric"}


def fabricated(rng):
    """One invented number as text: a decimal KPI-like value or a large whole number."""
    if rng.random() < 0.5:
        return f"{rng.uniform(13, 60):.{rng.choice((1, 2))}f}"
    return f"{rng.randint(100, 50000):,}"


def main(argv=None):
    """Run the control and print acceptance rates."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=400, help="answers per kind")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)
    shutil.rmtree(WS, ignore_errors=True)
    ledger = RunLedger(WS)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        head = ToolBox(load_demand(), ledger, ProjectNotes(WS), WS, workers=1).call(
            "run_design", DESIGN
        )
    run_id = head["run_id"]
    evidence = [json.dumps(head), json.dumps(ledger.summary(run_id), default=float)]
    brief = [json.dumps(CHALLENGE), json.dumps(ASSUMPTIONS, default=str)]
    rng = random.Random(args.seed)
    kinds = {
        "bare": "The design reaches {x} in that case [{r}].",
        "EUR/MWh": "The design costs {x} EUR/MWh [{r}].",
        "t CO2/yr": "The design emits {x} t CO2 per year [{r}].",
        "MWh": "The design buys {x} MWh of gas [{r}].",
    }
    result = {}
    for kind, template in kinds.items():
        accepted = 0
        for _ in range(args.n):
            text = template.format(x=fabricated(rng), r=run_id)
            accepted += not check_answer(text, evidence, brief, ledger)
        result[kind] = accepted / args.n
        print(f"{kind:>10}: {accepted}/{args.n} fabricated numbers accepted ({result[kind]:.1%})")
    return result


if __name__ == "__main__":
    main()
