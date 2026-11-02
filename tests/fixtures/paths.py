"""Where the data folders are: the one place that names them.

The sample projects sit in ``examples/<name>/`` and the data the tests read (the measured doublet
series, the example plant values, the old project files) in ``tests/fixtures/``. Neither is
installed: a function of this file that needs one raises ``RunError`` with code ``inputs_missing``
when it is absent, and only then, so nothing fails at import time. It is a helper of the tests, the
scripts and the examples runner: the package itself does not know where a checkout keeps its data.
"""

from pathlib import Path

from gemini.errors import RunError

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "gemini"
EXAMPLES = ROOT / "examples"
DATA = ROOT / "tests" / "fixtures"


def _below(folder, relative):
    """Return the path of ``relative`` below ``folder``; raise when there is no such folder."""
    if not folder.is_dir():
        raise RunError(
            f"{folder.name}: {relative} = not found; expected a source checkout of the "
            "repository, whose data folders are not installed",
            path=relative,
            code="inputs_missing",
        )
    return folder / relative


def example(name):
    """Return the folder of the sample project ``name`` of ``examples/``."""
    return _below(EXAMPLES, name)


def plant_values(name):
    """Return the path of the example values of plant ``name``; the file may not exist."""
    return _below(DATA, f"plants/{name}.json")


def doublet_heat(name):
    """Return the path of the measured data file ``name``."""
    return _below(DATA, f"doublet_heat/{name}")


def legacy_project():
    """Return the folder of the old project files."""
    return _below(DATA, "legacy_project")
