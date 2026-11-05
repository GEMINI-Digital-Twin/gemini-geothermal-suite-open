# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Fixed
- injector friction sign in the nodal solver: injection flow is passed down the well as a negative
  flowrate, so friction raises the wellhead pressure an injector needs
### Added
- ESPAffinity, ESP head and power at any frequency by the pump similarity (affinity) laws
  (registry name `esp_affinity`)
- HeatPumpLift, HeatpumpBasic in Lorenz mode with a brine floor per call (`heatpump_lift`)
- HenryGasBubblePoint, bubble point of a brine with dissolved methane and CO2 (`henry_gas`)
- DoubletThermalBreakthrough, doublet breakthrough time and interference between doublets
  (`thermal_breakthrough`)
- AbsorptionChiller, single-effect absorption chiller driven by the brine (`absorption_chiller`)
- registry entry `heatpump` for the existing HeatpumpBasic

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