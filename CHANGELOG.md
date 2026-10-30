# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- `gemini_model.chiller`: hot-water-fired absorption chiller and electric chiller models, with unit tests.
- `gemini_design`: heating + cooling plant design layer for the SPE GeoHackathon 2026
  (challenge inputs, doublet hydraulics at any depth, daily flowsheet with HEX bypass,
  heat pump and gas boiler top-up, 365-day dispatch with outage scheduling, hard-constraint
  checks, economics, design screening, and project-JSON export re-run through the Solver).
- `simulator_examples/run_heat_cool_design.py` and `run_design_screening.py`, plus the
  hackathon demand profiles in `simulator_examples/hackathon_inputs/`.
- `gemini_agent`: physics-gated design agent on any OpenAI-compatible LLM endpoint
  (default: Qwen3 8B on local Ollama, placeholder API key; GPT-6 Luna preset for comparison). Twelve tools over
  `gemini_design` / `gemini_simulator`, a six-step physics gate (schema, hard rules, daily
  energy balances, Solver re-run, Carnot and temperature bounds, no untraceable numbers in
  answers), three memory layers (scratchpad, run ledger, project notes), sandboxed
  model writing, a slot for a Fimbul reservoir provider, and JSONL/Markdown transcripts
  with token counts. CLI: `python -m gemini_agent`; demo transcripts:
  `simulator_examples/run_agent_transcripts.py`.
- Simulator registry entries for `heat_pump`, `absorption_chiller` and `electric_chiller`.
- Optional `pvt` overrides in well configs so wells can use a brine density/viscosity.
- `ElectricChiller`: refrigerant approach temperatures, DOE-2 part-load curve, staged
  modules and heat-rejection auxiliaries (system COP about 4-5 for 20 degC supply).
- `gemini_design`: optional CHP on associated gas (ahead of the boiler), with grid
  import/export, flaring accounting and CHP CAPEX; screening tries every design with and
  without it.
- `gemini_uncertainty`: Latin-hypercube Monte Carlo, P10/P90 tornado and paired design
  comparison over 14 sourced subsurface, demand, price and cost parameters; ThermoGIS well-cost
  model; report figures; agent tool `assess_design_uncertainty`
  (`simulator_examples/run_uncertainty_study.py`).
### Fixed
- Injection wellhead pressure: friction now opposes downward injection flow instead of
  adding to the bottomhole pressure, which made deep injectors look like they need no pump.

## [1.0.3] - 2026-10-13
## added
- parameters and tagnames of geothermal_example using csv data
### Fixed
- fix influxsb writing data float

## [1.0.2] - 2026-10-12
### Fixed
- fix grafana reverse-proxy authentication inside iframe

## [1.0.1] - 2026-08-20
### Fixed
- add python-dotenv package to pyproject.toml
### Changed
- more info for setting up environment variables in documentation
- change naming environment variables of OLLAMA and CHROMADB


## [1.0.0] - 2026-07-19

### Added
- Initial open-source release of the GEMINI Geothermal Suite.
- Initial release of the GEMINI Geothermal Model.
- Initial release of the GEMINI Geothermal Framework.
- Initial release of the GEMINI Geothermal Application.
  - Diagram Builder Application
  - ESP Monitoring Application
  - Productivity Application
  - Injectivity Application
  - Well Schematic Application
  - Well Integrity Monitoring Application
  - Time-series Visualization Application
  - Report Generation Application
  - Chatbot Application
- Initial release of the GEMINI Geothermal Interface.