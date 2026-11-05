# GeoBalance: agentic design of a deep-geothermal heating + cooling system

SPE Europe Energy GeoHackathon 2026 (Express Edition). Team GeoBalance.

An LLM agent designs an integrated system for the GEMINI challenge district
(heating peak 30 MW / 111.67 GWh, cooling peak 10 MW / 23.74 GWh). The agent
calls GEMINI for wells and pumps, our surface models for heating, cooling,
storage and gas, runs a 365-day simulation, reads violations and warnings,
improves the design and explains its recommendation.

## Files

| File | What it does |
|---|---|
| `agent.py` | LLM agent loop, tool definitions, memory, transcripts with token counts |
| `gemini_wrapper.py` | Builds and runs GEMINI doublet projects (official inputs), ESP sizing, GEMINI heat pump call, physics warnings |
| `annual_sim.py` | 365-day dispatch: direct geothermal, heat pump, absorption/electric chiller, gas engine, storage, backup boiler; maintenance outages; CO2 |
| `tools.py` | Hand-calculation tools (M.), also used to cross-check GEMINI |
| `storage.py` | Hot-water storage tank |
| `run_designs.py` | Same comparison without the LLM, for checking and report charts |
| `memory.json` | Agent memory: every evaluated design (created on first run) |
| `transcripts/` | One markdown file per agent session, with token usage |
| `results/` | Comparison table, charts, daily results |

## Run (macOS)

From the repository root (this folder sits next to `src/`):

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install numpy==2.2.6 scipy==1.13.1 matplotlib openai
cd hackathon_geobalance

python run_designs.py                         # no LLM: comparison + charts
python agent.py --provider mock               # no LLM: tests the tool plumbing

export GROQ_API_KEY=...                       # free key: console.groq.com
python agent.py --session main_design         # open-weight gpt-oss-120b on Groq
python agent.py --interactive --session ask   # agent may ask you questions
# Backup: export OPENAI_API_KEY=... ; python agent.py --provider openai
```

## Agent architecture

- **LLM:** `openai/gpt-oss-120b` (open-weight) via Groq's OpenAI-compatible API; any
  OpenAI-compatible endpoint works (`--provider openai`, or a local Ollama `base_url`).
- **Tools:** `get_challenge_inputs`, `size_doublet` (GEMINI), `evaluate_design`
  (full year), `cross_check_hand_calc` (GEMINI vs hand calc), `compare_designs`, `ask_user`.
- **Reasoning:** system prompt enforces "numbers only from tools", a fix-one-variable loop on
  violations, at least 3 different designs, and one justification per engineering decision.
- **Memory:** `memory.json` keeps every evaluated design; a short summary goes into the
  system prompt so the agent does not repeat runs (token saving).
- **Guard rails:** tools never crash; errors and physics problems come back as
  `violations`/`warnings`; off-topic requests are declined; missing inputs trigger `ask_user`.
- **Token use:** compact tool outputs (design echo removed, rounded numbers), memory
  summary instead of history; totals logged per session.

## Main results (`results/comparison.md`)

| Design | Backup boiler | Grid electricity | CO2 | vs gas boiler + chiller |
|---|---|---|---|---|
| A: 2 doublets 2,500 m, preheat + heat pump, gas engine | 11.0% | 13.7 GWh | 12.8 kt | -51% |
| B: 3 doublets 2,500 m, preheat + heat pump, gas engine | 0.0% | 12.3 GWh | 11.1 kt | -57% |
| E: 3 doublets 3,400 m, direct heating, gas engine | 0.0% | 0.0 GWh | 5.7 kt | -78% |
| F: 3 doublets 3,400 m, direct heating, gas reinjected | 0.1% | 5.3 GWh | 1.6 kt | -94% |

Reference: all heat from a gas boiler, all cooling from an electric chiller = 25.9 kt CO2/yr.

## Key assumptions (ours)

- Productivity index 14.4 m3/h/bar from 200 mD, 100 m, 0.4 mPa.s (radial, no skin).
- Brine cp 4,000 J/kg K; wellbore heat loss 3 K; network return 50 C; HX approach 5 K.
- ESP intake must stay above 35 bar (bubble-point estimate for GLR 0.8, 80% CH4) to avoid free gas.
- Heat pump COP: GEMINI Carnot formula (eta 0.5) with mean source temperature, max 6.
- Absorption chiller COP 0.7, needs >= 80 C, brine out 70 C (or the 40 K cap if higher).
  Electric chiller COP 5. Backup gas boiler 92%, 0.202 kg CO2/kWh fuel. Grid 0.3 kg/kWh.
- Gas: 0.969 kg/Nm3, 29.6 MJ/kg; all carbon in burned or flared gas counted as CO2
  (68.4 kg/GJ incl. native CO2). Reinjection: no CO2, compression power not modelled.
- Doublet outages: 35 consecutive days each, staggered from 24 March (low demand).
- Pump power scales with flow squared between GEMINI runs.
- Storage: energy model, 1% loss per day, charged from spare geothermal capacity.

## GEMINI issues found (for the maintainers)

1. **ESP intake pressure floored at 0** (`gemini_simulator/nodal_solver.py:67`,
   `gemini_simulator/well_flow.py:295`, `max(0.0, ...)`): with large tubing the nodal solve
   returns e.g. 491 m3/h with 0 bar intake, a non-physical result without any warning.
   Suggest raising an error or a flag when the floor is hit.
2. **HeatpumpBasic constrained branch** (`gemini_model/heatpump/heatpump_basic.py`, path used
   when `Ts_out < Ts_in_minimum`): returns supply temperatures of ~380-420 C and COP ~1.0-1.1
   (or negative COP) for ordinary inputs, e.g. Th_in 77 C, Ts_in 70 C, source 200 m3/h.
   The unconstrained Carnot path is fine. We use the Carnot formula directly.
3. **Heat pump and CO2 corrosion models are not in the simulator registry**
   (`gemini_simulator/registry.py`), so they cannot be used in project JSON files.
4. **Example gas properties** in `simulator_examples/projects/doublet_plant.json`
   (GWR 0.5, 0.7 kg/m3, 50 MJ/kg, 56.6 kg/GJ) are pure-methane-like defaults; the challenge
   gas (80% CH4 / 20% CO2) needs 0.969 kg/Nm3, 29.6 MJ/kg and 68.4 kg CO2/GJ.
5. **Injector wellhead pressure at the solver's lower bound (0.001 bar)** for some
   cases, so injector pump power is reported as 0 MW. Possibly correct (no pump needed),
   but worth a flag. Not confirmed as a bug.
