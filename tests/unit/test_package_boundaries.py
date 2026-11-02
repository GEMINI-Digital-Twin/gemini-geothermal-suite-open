"""``gemini._utils`` and ``gemini.errors`` are leaf packages that import nothing else from GEMINI.

One file of ``gemini/_utils`` may import ``gemini.errors``, itself a leaf: ``registry.py``, which
refuses a name.
"""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
RAISES_ERRORS = ("registry.py",)
"""The topic files that raise a ``gm.errors`` class: they may import ``gemini.errors``."""


def imported_modules(path):
    """Return the absolute module names one file imports."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.add(node.module)
        elif isinstance(node, ast.ImportFrom):
            names.add("." * node.level + (node.module or ""))
    return names


@pytest.mark.parametrize("package", ["_utils", "errors"])
def test_leaf_package_imports_only_itself(package):
    """Every import is the standard library, a dependency, or the package itself."""
    offending = {}
    for path in sorted((ROOT / "gemini" / package).rglob("*.py")):
        names = imported_modules(path) - (
            {"gemini.errors"} if path.name in RAISES_ERRORS else set()
        )
        bad = {
            name
            for name in names
            if name.startswith(".")
            or (name.split(".")[0] == "gemini" and not name.startswith(f"gemini.{package}"))
        }
        if bad:
            offending[path.name] = sorted(bad)
    assert offending == {}


def test_a_dataset_knows_no_modules_or_engine():
    """``gemini/case/dataset.py`` is in-memory data, with nothing of a run."""
    names = imported_modules(ROOT / "gemini/case/dataset.py")
    assert [name for name in names if name.startswith(("gemini.modules", "gemini.engine"))] == []


FOLDERS = {
    path.name.removesuffix(".py")
    for path in (ROOT / "gemini").iterdir()
    if not path.name.startswith("__")
}
"""Every folder, and the file ``runtime.py``, of the package."""
BASE = {"errors", "_utils", "units"}
OPS = BASE | {"ops"}
PHYSICS = OPS | {"physics"}
STREAMS = PHYSICS | {"streams"}
MODULES = STREAMS | {"modules", "runtime"}
PLANTS = MODULES | {"plants"}
ENGINE = PLANTS | {"case"}
EVALUATE = ENGINE | {"engine"}
MAY_IMPORT = {
    "errors": set(),
    "_utils": {"errors"},
    "units": {"errors", "_utils"},
    "ops": {"units", "errors", "_utils"},
    "physics": OPS,
    "streams": PHYSICS,
    "runtime": {"ops", "errors", "_utils"},
    "modules": STREAMS | {"runtime"},
    "plants": MODULES,
    "case": PHYSICS | {"plants"},
    "engine": ENGINE,
    "evaluate": EVALUATE,
    "study": EVALUATE | {"evaluate", "analysis"},
    "analysis": PLANTS,
}
"""For each folder the folders it may import (R4 of ``.claude/docs/structure.md``): the chain
``units, errors, _utils -> ops -> physics -> streams -> modules -> plants -> engine -> evaluate ->
study``, ``case`` below the engine (it reads ``physics`` for the geotherm and ``plants`` for the
role table), ``analysis`` on top of ``plants`` and read by ``study``, and ``runtime`` read by every
folder from ``streams`` up. ``compiler`` may import everything and
nothing imports it."""


def folder_of(path):
    """Return the folder of a package file, or the stem of a file at the top (``runtime.py``)."""
    parts = path.relative_to(ROOT / "gemini").parts
    return parts[0].removesuffix(".py") if len(parts) > 1 or parts[0] != "__init__.py" else None


IMPORT = re.compile(
    r"^[ \t]*(?:from[ \t]+gemini(?:\.(\w+)[\w.]*)?[ \t]+import[ \t]+([^\n(]*)"
    r"|import[ \t]+gemini\.(\w+))",
    re.MULTILINE,
)
"""A ``from gemini... import`` or ``import gemini.<folder>`` statement, at any indentation."""


def imported_folders(path):
    """Return the folders of the package that one file imports, anywhere in the file."""
    found = set()
    for folder, names, plain in IMPORT.findall(path.read_text()):
        if folder:
            found.add(folder)
        elif plain:
            found.add(plain)
        else:
            found.update(name.strip().split(" ")[0] for name in names.split(","))
    return found & FOLDERS


def import_violations():
    """Return ``{(file, imported folder)}`` of every import against the direction of R4."""
    found = set()
    for path in sorted((ROOT / "gemini").rglob("*.py")):
        folder = folder_of(path)
        if folder in (None, "compiler"):
            continue
        for imported in imported_folders(path):
            if imported == folder:
                continue
            if imported == "compiler" or imported not in MAY_IMPORT[folder]:
                found.add((str(path.relative_to(ROOT)), imported))
    return found


def test_imports_follow_one_direction():
    """No folder imports one that the table of ``structure.md`` does not let it call."""
    assert import_violations() == set()


def test_every_folder_has_a_row_in_the_table():
    """A new folder must be placed in the direction of imports before it is used."""
    assert FOLDERS - {"compiler"} == set(MAY_IMPORT)
