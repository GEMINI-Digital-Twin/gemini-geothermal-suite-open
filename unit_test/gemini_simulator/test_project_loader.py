"""Unit tests for gemini_simulator.project_loader."""

from gemini_simulator.project_loader import build_project, load_project


def _two_adder_project():
    return {
        "components": {
            "adder": {"type": "adder", "parameters": {"num_inputs": 2}},
            "splitter": {"type": "splitter", "parameters": {"split_fractions": [0.5, 0.5]}},
        },
        "boundary_inputs": [
            {"component": "splitter", "key": "input", "value": 100.0},
            {"component": "adder", "key": "input_1", "value": 0.0},
        ],
        "connections": [
            {
                "predecessor": "splitter",
                "successor": "adder",
                "predecessor_output": "output_0",
                "successor_input": "input_0",
            },
            {
                "predecessor": "splitter",
                "successor": "adder",
                "predecessor_output": "output_1",
                "successor_input": "input_1",
            },
        ],
    }


def test_build_project_wires_components_and_runs():
    """Building a project should wire components and be runnable."""
    solver = build_project(_two_adder_project())

    solver.run()

    assert solver.get_output("splitter", "output_0") == 50.0
    assert solver.get_output("adder", "output") == 100.0


def test_load_project_from_file(tmp_path):
    """Loading a project from a JSON file should build a runnable solver."""
    import json

    project_path = tmp_path / "project.json"
    project_path.write_text(json.dumps(_two_adder_project()))

    solver = load_project(project_path)
    solver.run()

    assert solver.get_output("adder", "output") == 100.0


def test_build_project_applies_parameters():
    """Building a project should apply each component's own parameters."""
    solver = build_project(_two_adder_project())

    assert solver.components["adder"].parameters["num_inputs"] == 2
    assert solver.components["splitter"].parameters["split_fractions"] == [0.5, 0.5]
