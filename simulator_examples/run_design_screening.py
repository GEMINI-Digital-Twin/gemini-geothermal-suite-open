"""Screen the GeoHackathon design space (1-3 doublets x depth x upgrade x cooling).

Writes ``simulator_examples/outputs/screening.csv`` ranked by levelised
cost among designs that meet every hard constraint and all demand.

Run with:
    $env:PYTHONPATH="src"; python simulator_examples/run_design_screening.py
"""

from pathlib import Path

import pandas as pd

from gemini_design.challenge import load_demand
from gemini_design.screening import candidate_designs, screen

INPUTS = Path(__file__).parent / "hackathon_inputs"
OUTPUTS = Path(__file__).parent / "outputs"


def main():
    """Run the default candidate grid and print the top of the ranking."""
    demand = load_demand(INPUTS)
    table, _ = screen(candidate_designs(), demand)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUTS / "screening.csv", index=False)
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(table.head(15).round(2).to_string(index=False))
    return table


if __name__ == "__main__":
    main()
