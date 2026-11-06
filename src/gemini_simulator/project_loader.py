"""Load an explicit-connections plant project JSON file into a Solver.

Project JSON schema
--------------------
::

    {
      "components": {
        "<name>": {"type": "<registry type>", "parameters": {...}},
        ...
      },
      "boundary_inputs": [
        {"component": "<name>", "key": "<key>", "value": <any>},
        ...
      ],
      "connections": [
        {"predecessor": "<name>", "successor": "<name>",
         "predecessor_output": "<key>", "successor_input": "<key>"},
        {"predecessor": "<name>", "successor": "<name>",
         "ports": [["<output_key>", "<input_key>"], ["<output_key>", "<input_key>"]]},
        ...
      ]
    }

``components`` instantiates one gemini_model object per entry (via
:func:`gemini_simulator.registry.create_component`) and applies its
``parameters``. ``connections`` are wired onto the Solver in the order
given -- this order matters (see :meth:`gemini_simulator.solver.Solver.connect`).
A connection entry either carries one output/input key pair
(``predecessor_output``/``successor_input``), or several pairs at once
between the same predecessor/successor via ``ports`` (a list of
``[predecessor_output, successor_input]`` pairs) -- ``ports`` is just a
compact way to write several ordinary connections between the same two
components without repeating their names. ``boundary_inputs`` set fixed
input values that are not produced by any other component's output
(e.g. ambient temperature, a fixed setpoint).

This keeps plant topology entirely data-driven: different plants are
just different JSON files, and a future diagram/GUI builder can emit
this same format.
"""

import json

from gemini_simulator.registry import create_component
from gemini_simulator.solver import Solver


def load_project(path):
    """Build a :class:`~gemini_simulator.solver.Solver` from a project JSON file.

    Parameters
    ----------
    path: str or Path
        Path to a project JSON file following the schema documented above.

    Returns
    -------
    Solver
        A solver with all components instantiated, parameterized, wired
        with connections, and boundary inputs applied. Call ``.run(...)``
        on it to simulate.
    """
    with open(path, "r", encoding="utf-8") as file:
        project = json.load(file)

    return build_project(project)


def build_project(project):
    """Build a :class:`~gemini_simulator.solver.Solver` from an already-parsed project dict.

    See :func:`load_project` for the expected schema.
    """
    components = {}
    for name, spec in project.get("components", {}).items():
        component = create_component(spec["type"])
        parameters = spec.get("parameters")
        if parameters:
            component.update_parameters(parameters)
        components[name] = component

    solver = Solver(components)

    for entry in project.get("boundary_inputs", []):
        solver.set_boundary_input(entry["component"], entry["key"], entry["value"])

    for entry in project.get("connections", []):
        if "ports" in entry:
            for output_key, input_key in entry["ports"]:
                solver.connect(entry["predecessor"], entry["successor"], output_key, input_key)
        else:
            solver.connect(
                entry["predecessor"],
                entry["successor"],
                entry["predecessor_output"],
                entry["successor_input"],
            )

    return solver
