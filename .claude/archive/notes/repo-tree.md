# GEMINI repository tree structure (with notes)

Version reviewed: main branch on 2026-10-27. The `__init__.py` files, CSS/JS/fonts (`static/`) and documentation images are left out.
Marks: ✅ has real code · ⚪ only an empty placeholder · 📄 data or settings · ⭐ where we extend

```text
gemini-geothermal-suite-open/
├── README.md, CONTRIBUTING.md, CHANGELOG.md, LICENSE (Apache 2.0)
├── pyproject.toml              📄 dependencies (Poetry, Python 3.11–3.12), black/isort/flake8 settings
├── docker-compose.yml          📄 MySQL, InfluxDB, Redis, MongoDB, ChromaDB, Grafana, Ollama
├── .env.template               📄 environment variables (ports, passwords, LLM model)
├── .github/workflows/          test, lint and docs build on every push
├── ci/linux, ci/windows/       scripts for install, running the GUI, test, lint, Ollama models
│
├── dataset/
│   └── geothermal_example_dataset.csv   📄 17280 rows at 15 minutes (6 months): flow rate, temperatures, pressures, ESP power, thermal power
│
├── gemini-project/             📄 definitions of "plants" as JSON
│   ├── _template/              param template for each equipment type
│   │   ├── template_esp / production_well / injection_well / reservoir / heat_exchanger / ...   (has code)
│   │   ├── template_heat_pump / chp / heat_demand / elec_boiler / gas_boiler                  (no code!)
│   │   ├── grafana_template/   ready-made dashboards
│   │   └── report_generator/   Excel template for the Dutch production report
│   └── geothermal_example/     sample doublet: reservoir 80°C, 220 bar, depth 1800 m; ESP, exchanger, filters, degasser
│
├── src/
│   ├── gemini_model/           ✅ pure physical models (the most important part for us)
│   │   ├── model_abstract.py   base interface: StaticModel / DynamicModel
│   │   ├── pump/esp.py         ✅ ESP head, power and efficiency from polynomial curves
│   │   ├── well/               ✅ pressure and temperature drop in the well
│   │   │   ├── pressure_drop.py
│   │   │   └── correlation/    beggsbrill, darcyweisbach, temperaturedrop
│   │   ├── reservoir/          ✅ IPR, injectivity index, skin drop, reservoir pressure estimate
│   │   ├── fluid/pvt_water_stp.py   ✅ water properties
│   │   ├── corrosion/          ✅ CO2 corrosion (NORSOK, DLM, DLD + optimized versions)
│   │   ├── erosion/            ✅ erosion (DNV, API, Oka, Tulsa)
│   │   └── surface/            ⭐ new: exchanger, heat pump, absorption/compression chiller, storage, boiler, economics
│   │
│   ├── gemini_framework/       time series monitoring engine: reads data, runs the model, writes the result
│   │   ├── app.py              runs one step for one plant
│   │   ├── abstract/           base class for unit, module, database driver
│   │   ├── framework/          plant.py, boot_plant.py, mainmodule.py, loop.py
│   │   ├── database/           InfluxDB, AVEVA and CSV drivers
│   │   └── modules/            one folder for each piece of equipment
│   │       ├── esp/            ✅ 6 calculation modules (head, power, outlet pressure, VLP/IPR)
│   │       ├── injectionwell/  ✅ 2 modules (bottomhole pressure, injectivity index)
│   │       ├── heatexchanger/  ⚪ empty class ← ⭐ we fill it
│   │       ├── productionwell/ ⚪   reservoir/ ⚪   degasser/ ⚪   filter/ ⚪
│   │       ├── gasboiler/ ⚪   electricboiler/ ⚪   boosterpump/ ⚪   injectionpump/ ⚪   blowdown/ ⚪
│   │       └── heatpump/, chiller/, storage/   ⭐ new
│   │
│   ├── gemini_application/     application logic (behind the web pages)
│   │   ├── application_abstract.py
│   │   ├── esp/                ✅ ESP monitoring, calibration and forecasting (~1000 lines)
│   │   ├── productionwell/     ✅ production well performance
│   │   ├── injectionwell/      ✅ injection well monitoring
│   │   ├── wims/               ✅ well integrity: corrosion and erosion (~5000 lines)
│   │   ├── reportgenerator/    ✅ production report (~3000 lines)
│   │   ├── tagbrowser/         ✅ data and tag management
│   │   ├── chatpopup/          ✅ RAG chat with Ollama + ChromaDB (not an agent)
│   │   └── geomind/            ⭐ new: design agent (Interpreter, Orchestrator, Designer, Critic, ...)
│   │
│   ├── gemini_interface/       Flask web app
│   │   ├── app.py, create_app.py
│   │   ├── blueprint/          one routes folder for each page
│   │   │   ├── auth, dashboard, project, setting_plant, report
│   │   │   ├── app_builder     Diagram Builder (placing equipment on the diagram)
│   │   │   ├── app_esp, app_productionwellperformance, app_injectionwellmonitoring
│   │   │   ├── app_wellintegrity_monitoring (~2500 lines), app_reportgenerator
│   │   │   ├── app_tagbrowser, app_parameters_overview, app_well_schematics
│   │   │   ├── app_chatpopup
│   │   │   ├── app_geomind     ⭐ new: agent tasks and results page
│   │   │   ├── celerytasks.py  background jobs
│   │   │   └── dbmodels.py     user/project tables
│   │   ├── templates/          HTML for each page
│   │   └── static/             JS for each page + CSS/fonts of the Black Dashboard template
│   │
│   └── gemini_documentation/source/   Sphinx documentation (rst)
│
└── unit_test/                  tests, only for some of the models
    ├── gemini_model/           corrosion, fluid, pump, reservoir, well
    ├── gemini_framework/       AVEVA driver only
    └── gemini_model/surface/   ⭐ tests for the new models
```

## Summary

- The **physical brain** is in `gemini_model`: clean, independent and usable without a database.
- The **framework** is built for monitoring real data, and of the 12 pieces of equipment only 2 have calculations.
- The **bulk of the code** (about 16 thousand lines) is in the well monitoring and report applications, not in system design.
- There is no model for the demand side (demand, heat pump, chiller, storage) or for economics.
