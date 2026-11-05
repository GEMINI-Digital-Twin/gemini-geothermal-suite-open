# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - GeoHackathon 2026 (DeepLayers)
### Added
- `gemini_agent`: open-weight agentic design workflow (requirements -> subsurface screening -> design search ->
  stress/Monte-Carlo/sensitivity -> native GEMINI re-simulation), fact ledger + deterministic verifier,
  Gradio cockpit, evidence tooling (`docs_geohackathon2026/`).
- `gemini_model/chiller`: `AbsorptionChiller`, `ElectricChiller`; `heat_pump`, `absorption_chiller`,
  `electric_chiller` registered in `gemini_simulator.registry`.
- Model Forge (`gemini_agent/forge.py`): declarative spec -> validated, unit-tested, registered `StaticModel`.
- Deterministic harness around the LLM (`gemini_agent/request_check.py`, `runner.py`, `ledger.py`): request screen
  against the brief's limits, design/objective/priority/missing-model notes, verifier (numbers, units, claims,
  citations, request match, design status) with one revision, persistent memory from rejections (`lessons.py`).
### Fixed
- `nodal_solver._well_bottomhole_pressure_injection`: friction was added instead of subtracted (regression test).
- `HeatpumpBasic`: unbracketed Nelder-Mead replaced by bracketed `brentq` on both branches (non-physical
  837 C / COP 1e8 outputs; 35x faster; regression test).
- `well_flow`: optional `pvt` override so brine density/viscosity from the brief can be used.
### Reported (not changed)
- DPDT superficial gas velocity uses the gas mass fraction instead of the mass flow; default roughness 0.01 m.
  See `docs_geohackathon2026/GEMINI_MODEL_AUDIT.md`.

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