# GEMINI examples

Six scripts, each runs alone from any folder with `gemini` installed (`pip install -e .`), reads its
data from `examples/` through its own path and writes nothing to the repository except the
run records of `hackathon.py` in `runs/`.

| File | What it shows | Main names |
| --- | --- | --- |
| [quickstart.py](quickstart.py) | A JSON case and plant, `gm.check`, simulate, requirements, report (shallow district) | `gm.Case.from_json`, `gm.Plant.from_json`, `gm.check`, `gm.simulate`, `gm.evaluate.requirements`, `gm.evaluate.report` |
| [hackathon.py](hackathon.py) | The whole flow on the hackathon case from study files: every candidate sized and searched, ranked by the brief's rules only and again with the pump intake limits of standard stages, the Pareto front of the feasible designs, sensitivity and draws of the best design; takes about 4.5 minutes | `gm.Study.from_json`, `Study.run`, `result.to_json`, `gm.runtime.settings` |
| [costs.py](costs.py) | `gm.check`, capex per unit, opex, LCTS and CO2, a limit on the electricity bought as a requirement of the case, and how a missing assumption is reported | `gm.check`, `gm.evaluate.capex`, `opex`, `lcts`, `co2`, `requirements`, `missing_assumption` |
| [uncertainty.py](uncertainty.py) | `gm.check`, then the spread of LCTS and CO2 over the values the case declares uncertain | `gm.check`, `gm.study.sample` |
| [plant.py](plant.py) | A plant built from its class: `missing_parameters`, values set as quantities, `gm.plants.validate(plant)`, sized, `gm.check` on the case, run, failed steps grouped | `missing_parameters`, `set_params`, `gm.plants.validate`, `gm.study.size`, `gm.check`, `gm.evaluate.failures` |
| [evolve.py](evolve.py) | One plant file that states the six hackathon candidates at once (`hackathon_superstructure/`: the heat pump optional, each cooling unit a choice on or off), its valid structures, sized, then searched on LCTS and CO2 by a genetic algorithm with a small budget; prints the front and the best design; takes about 20 seconds | `optional`, `choices`, `plant.structures`, `gm.study.size`, `gm.study.evolve` |

```bash
python examples/quickstart.py
```
