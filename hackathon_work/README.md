# GEMINI Agentic Geothermal Hackathon — Starter Workspace

> **Current state (2026-11-05).** The sections below are the original starter notes. The design work has since
> been done: see `EVIDENCE_APPENDIX.md` (all evidence in one place), `STRONG_POINTS.md` (what the submission shows, with evidence and how to reproduce it),
> `CLAUDE.md` (inputs, provenance, decisions), `DECISIONS_LOG.md` (minor decisions taken without asking) and
> `dashboard/index.html` (results). Final pick: `n2_q300_s1.8_ua1000_z3500_co2ri`: 2 doublets at 3 500 m,
> CO₂ reinjected, CH₄ to CHP, 3 983 t CO₂/yr (85.1% below the gas-boiler + electric-chiller reference).

This folder is intentionally separate from GEMINI's `src/` code. The original GitHub `development` branch remains unchanged.

## Setup on your Windows work computer

1. Extract `hackathon_work/` from the ZIP into your existing project folder `Desktop/gemini-geothermal-suite-open/` (not into a second nested GEMINI repository).
2. Open the GEMINI repository root in VS Code, select the GEMINI Poetry Python 3.11 interpreter, and open **Terminal > New Terminal**.
3. Confirm you are on the `development` branch: `git branch --show-current`.
4. First, run the **original GEMINI doublet plant example** without modifying any JSON:

```powershell
$env:PYTHONPATH = "src"
py -3.11 -m poetry run python simulator_examples/run_doublet_plant_example.py
```

5. Then run the **2027 demand-baseline and input-validation script**:

```powershell
py -3.11 -m poetry run python hackathon_work/demand_baseline.py
```

No Docker containers are required for these two physics/simulator workflows. The full GEMINI web application is a separate, optional setup.

## What is included

- `inputs/GEMINI_Heating_Demand_Daily_2027.csv`: unmodified supplied heating profile
- `inputs/GEMINI_Cooling_Demand_Daily_2027.csv`: unmodified supplied cooling profile
- `inputs/challenge_inputs.json`: transcribed official fixed reservoir/brine and operating inputs; one explicitly labeled illustrative heat-capacity assumption
- `demand_baseline.py`: validates 365 dates; calculates daily/monthly/annual loads; screens theoretical geothermal heat-extraction maxima
- `outputs/baseline_summary.json`, `outputs/daily_demand_checked.csv`, `outputs/monthly_energy_GWh.csv`: example outputs you can regenerate on your computer

## Engineering boundaries

This first step is a screening and data-validation exercise. It does **not** validate 100 C heating supply, cooling equipment, fluid/pressure losses, operating shut-down scheduling, or full plant optimization. The original GEMINI example uses demonstration parameters and one time step: it is not automatically compliant with the hackathon constraints.

Next steps: inspect the output of the GEMINI example; work from an independent copy of `simulator_examples/projects/doublet_plant.json`; match challenge inputs; add cooling component(s) and 365-day dispatch with 330 active geothermal days; develop a traceable AI-agent optimization/validation workflow.

Sources: organizer's supplied PDF dated 28 October 2026, both video transcripts, and https://github.com/GEMINI-Digital-Twin/gemini-geothermal-suite-open/tree/development.
