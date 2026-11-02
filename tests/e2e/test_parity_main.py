"""The physics that ``origin/main`` (1.0.3) has gives the same numbers in the current package.

``scripts/capture_parity_main.py`` runs the models of ``main`` (ESP, inflow performance,
injectivity, reservoir pressure, well pressure and temperature march, friction and temperature
correlations, CO2 corrosion, erosion, CO2 partial pressure) on the golden inputs and on sweeps
around them. This test runs the same cases through the current modules and physics and compares
every number at 1e-9. A difference is a bug unless ``parity_main_allowed.json`` lists the case
with the commit that changed it on purpose and the reason.

The competition path itself (size, minimize, simulate, verdict, report, compare, sensitivity) does
not exist on ``main``; the allowed file names those parts.
"""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from scripts.parity import cases as parity_cases
from scripts.parity import current_adapter, flatten

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / ".tmp/parity"
ALLOWED = Path(__file__).with_name("parity_main_allowed.json")
pytestmark = pytest.mark.e2e
RTOL = 1e-9
HOW = (
    "run `python scripts/capture_parity_main.py` (needs network; see testing.md, Parity with main)"
)


@pytest.fixture(scope="module")
def stored():
    """Return the capture of ``main``: ``(record, numbers)``."""
    if not (CAPTURE / "main.json").exists() or not (CAPTURE / "main.npz").exists():
        pytest.skip(f"no capture of main in .tmp/parity: {HOW}")
    record = json.loads((CAPTURE / "main.json").read_text())
    with np.load(CAPTURE / "main.npz") as archive:
        return record, {key: archive[key] for key in archive.files}


@pytest.fixture(scope="module")
def current(stored):
    """Return the current numbers and exact leaves of the stored cases."""
    numbers, exact = {}, {}
    for name, outputs in current_adapter.run(stored[0]["cases"]).items():
        for path, leaf in flatten.flat(outputs).items():
            (numbers if isinstance(leaf, np.ndarray) else exact)[f"{name}{path}"] = leaf
    return numbers, exact


def differences(stored, current):
    """Return ``{key: description}`` of every number or exact leaf that differs."""
    (record, old), (new, new_exact) = stored, current
    found = {}
    for key in sorted(set(old) | set(new)):
        if key not in old or key not in new:
            found[key] = "only on " + ("main" if key in old else "current")
        elif old[key].shape != new[key].shape:
            found[key] = f"shape {old[key].shape} against {new[key].shape}"
        elif not np.allclose(old[key], new[key], rtol=RTOL, atol=0, equal_nan=True):
            worst = np.max(np.abs(old[key] - new[key]) / np.maximum(np.abs(old[key]), 1e-300))
            found[key] = f"main {old[key][:3]} current {new[key][:3]} (relative {worst:.3g})"
    for key in sorted(set(record["exact"]) | set(new_exact)):
        if record["exact"].get(key, "missing") != new_exact.get(key, "missing"):
            found[key] = f"main {record['exact'].get(key)!r} current {new_exact.get(key)!r}"
    return found


def case_of(key, names):
    """Return the case name that starts a key."""
    return max(
        (n for n in names if key == n or key.startswith(n + "/") or key.startswith(n + "[")),
        key=len,
    )


def test_the_capture_is_main_1_0_3(stored):
    """The capture was taken from ``main`` at version 1.0.3 and holds the cases of the check."""
    record, numbers = stored
    assert record["version"] == "1.0.3", HOW
    assert set(record["cases"]) == set(parity_cases.cases()), f"cases changed: {HOW}"
    assert numbers


def test_every_number_of_main_is_reproduced_at_1e_9(stored, current):
    """Each difference is listed in the allowed file; any other one is a bug."""
    found = differences(stored, current)
    allowed = json.loads(ALLOWED.read_text())["differences"]
    covered = {entry["case"]: entry for entry in allowed}
    names = list(stored[0]["cases"])
    unexplained = {k: v for k, v in found.items() if case_of(k, names) not in covered}
    assert not unexplained, json.dumps(unexplained, indent=1, default=str)
    stale = [c for c in covered if not any(case_of(k, names) == c for k in found)]
    assert not stale, f"allowed entries without a difference: {stale}"


def test_each_allowed_difference_names_its_commit_and_reason():
    """An entry holds a commit of this history that changed the output, and why."""
    for entry in json.loads(ALLOWED.read_text())["differences"]:
        assert entry["reason"].strip(), entry
        done = subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{entry['commit']}^{{commit}}"],
            capture_output=True,
        )
        assert done.returncode == 0, entry
