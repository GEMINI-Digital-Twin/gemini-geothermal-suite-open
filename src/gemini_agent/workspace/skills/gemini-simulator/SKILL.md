---
name: gemini-simulator
description: What the GEMINI digital-twin simulator contains, how a plant is described as JSON (components / boundary_inputs / connections), which models were added or fixed for this challenge. Read when asked about GEMINI, model coverage or missing models.
---
# GEMINI simulator

- Physics models (gemini_model): well DPDT (friction + gravity + heat loss), reservoir IPR, ESP, separator, filter, heat exchanger (NTU), heat pump (Carnot/Lorenz), boiler, CHP, pumps, mixer/splitter/adder.
- Simulator (gemini_simulator): a plant is one JSON file with three sections:
  `components` (type + fixed parameters), `boundary_inputs` (set-points), `connections` (predecessor output -> successor input). One `solver.run()` = one steady state; our annual driver repeats it for 365 days.
- Added for this challenge: absorption_chiller, electric_chiller, heat_pump registration, PI from permeability, thermal breakthrough, brine PVT override, annual dispatch.
- Fixed in GEMINI: injector friction sign (injection pressure was under-estimated by 2x friction), heat-pump solver returning non-physical points (e.g. 837 C), and others (see `list_gemini_models`).
Use `list_gemini_models` to report coverage and gaps with a fact ID.
