"""Run the parity cases through the current package.

``evaluate_case`` of the phase-0 fixtures builds the module or calls the physics function of each
family and returns the outputs in the names and units of ``main``. Nothing here is imported by
``gemini``; it only lives next to the check.
"""

from tests.fixtures.evaluate import evaluate_case


def run_case(case):
    """Return the outputs of one case, or ``{"error": <exception class name>}`` if it raises."""
    try:
        return evaluate_case(case["family"], case)
    except Exception as error:
        return {"error": type(error).__name__}


def run(cases):
    """Return ``{name: outputs}`` for every case."""
    return {name: run_case(case) for name, case in cases.items()}
