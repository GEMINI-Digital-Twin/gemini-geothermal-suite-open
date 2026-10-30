# agentic_design: simulation core for the GEMINI GeoHackathon 2026

A design-evaluation engine for a geothermal district heating (and, next, cooling)
plant, built on the GEMINI models. An agent can call one function, `evaluate(design)`,
and get back the annual performance, every constraint violation, and an independent
cross-check against the full GEMINI simulator.

## Install and run (Windows, from the repository root)

```
git checkout development            # this folder goes in the repo root, next to src/
pip install -r agentic_design/requirements.txt
python -m agentic_design.run_design --doublets 2 --depth 2500
python -m agentic_design.run_design --compare
pytest agentic_design/tests -q
```

No `PYTHONPATH` needed. Results are written to `agentic_design/results/<design>/`.

## What is in here

| File | Role |
|---|---|
| `config.py` | Challenge inputs (fixed, from the requirements document) and `Assumptions` (everything the challenge leaves open, each with a reason) |
| `wells.py` | Producer + ESP and injector at a set flow, using GEMINI `IPR` and `DPDT` per 100 m segment against the local geotherm |
| `annual.py` | 365-day simulation: per day, an exhaustive search over doublets-on and flow (1 m³/h steps) minimising CO₂; HX uses GEMINI's effectiveness-NTU equation at fixed size |
| `checks.py` | Every challenge constraint (C1–C8) and physical sanity checks (P1–P6), returned as structured findings |
| `plant_json.py` | Builds GEMINI simulator project files for 1–3 doublets, validates them before running, adds two components to the registry |
| `verify.py` | Rebuilds chosen days as full GEMINI projects, runs GEMINI's solver, compares with the fast model |
| `run_design.py` | Command-line entry point / the tool the agent calls |
| `tests/test_core.py` | 18 tests: hand calculations, constraint detection, GEMINI cross-check |

Speed: one full year ≈ 0.05 s per design, so the agent can compare hundreds of designs.

## Issues found in GEMINI (report these; they are fixed/avoided here)

1. **Injection friction sign.** `DPDT` with `direction="down"` always adds friction. For a producer walked
   top-down this is right; for brine flowing down an injector it is wrong, so `InjectorWell`
   underestimates the required injection pressure by 2 × friction (15.5 bar at 300 m³/h in a 0.2 m well;
   injection pump power about 33% too low at peak). Fix used here: pass a negative flow rate.
2. **Pipe roughness default** in `well_flow._build_dpdt` is 0.01 m (10 mm), about 100× steel casing;
   friction would be overstated several-fold. 0.1 mm used here.
3. **Fluid defaults** are fresh water (1,000 kg/m³, 1.0 mPa·s); the challenge brine is 1,030 kg/m³,
   0.40 mPa·s. Overridden here.
4. **Example ESP curve** cannot deliver the 300 m³/h cap (head goes negative above about 250 m³/h at
   65 Hz). Pump power here follows the challenge rule: Δp × Q / 0.70.
5. **Silent pressure clamp**: `DPDT` floors pressure at 0.001 Pa without warning; detected and reported here.
6. **Bootcamp figure**: reservoir temperature at 2,500 m is 12 + 30 × 2.5 = **87 °C**, not ~75 °C.

## Assumptions (not given by the challenge; all in `config.Assumptions`)

Network return temperature 55 °C · brine cp 4,000 J/kgK · PI from steady radial Darcy (re = 1,000 m,
rw = 0.108 m, skin 0) → 13.3 m³/h/bar · vertical wells, 0.20 m ID · ESP at 650 m · producer wellhead
10 bar (gas kept in solution) · surface Δp 3 bar at design flow · HX sized for 3 °C approach on the peak
day · boiler efficiency 0.90 · associated gas: 80/20 CH₄/CO₂, all combusted (used or flared) ·
electricity 0.30 kg CO₂/kWh · "330 daily steps" read as max 330 operating days per doublet (35-day
maintenance each, placed automatically in the lowest-load window).

## First results (heating only; cooling not yet modelled)

| Design | Geothermal share | Purchased gas | CO₂ |
|---|---|---|---|
| 1 doublet, 2,500 m | 45% | 50.7 GWh | 15.1 kt |
| 2 doublets, 2,500 m | 64% | 25.7 GWh | 11.0 kt |
| 3 doublets, 2,500 m | 63% | 25.5 GWh | 10.9 kt |
| 2 doublets, 3,000 m | 89% | 0.03 GWh | 4.6 kt |

At 2,500 m the limit is temperature, not flow: 85 °C brine can only lift a 55 °C network to about 82 °C,
so a third doublet adds nothing. Going to 3,000 m (102 °C) or adding a heat pump changes the picture.
