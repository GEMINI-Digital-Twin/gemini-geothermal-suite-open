"""From 0.5.0 the public API is backward compatible: nothing of it may be lost or changed."""

import json
from functools import reduce

import pytest

import gemini as gm
from tests.fixtures.capture_frozen_api import (
    FROZEN,
    INHERITED,
    POSITIONAL,
    UNSET,
    capture,
    fingerprint_file,
)

FROZEN_FILE_HASH = "899be29a7e7fbecfb73794227e43df40281d1bb06e54f13e16619a070341467d"
"""Hash of ``public_api_0_5_0.json``; the file is written once and never regenerated."""

RULE = (
    "The public API is backward compatible from 0.5.0: no name, parameter, default, code or "
    "schema key may be renamed, removed or changed (additions are allowed). Undo the change, or "
    "ask the owner; do not edit public_api_0_5_0.json."
)

USED_BY_GEOMIND = (
    "gm.simulate",
    "gm.schedule",
    "gm.call",
    "gm.Case.from_dict",
    "gm.Case.from_json",
    "gm.Case.schema",
    "gm.Plant.from_dict",
    "gm.Plant.from_json",
    "gm.Plant.to_dict",
    "gm.plants.get",
    "gm.plants.names",
    "gm.plants.schema",
    "gm.plants.capabilities",
    "gm.plants.Doublet",
    "gm.modules.get",
    "gm.modules.names",
    "gm.modules.categories",
    "gm.evaluate.report",
    "gm.evaluate.totals",
    "gm.evaluate.failures",
    "gm.evaluate.compare",
    "gm.evaluate.capex",
    "gm.study.size",
    "gm.study.minimize",
    "gm.study.sample",
    "gm.study.sensitivity",
    "gm.units.Quantity",
    "gm.units.convert",
    "gm.units.names",
    "gm.errors.ValidationError",
    "gm.errors.CODES",
    "gm.Results.from_bytes",
    "gm.__version__",
)
"""The names geomind imports: each must exist, and the frozen file must hold each of them.

``gm.plants.validate`` was on the owner's list and does not exist at 0.5.0 (nor at 0.4.0).
"""


def lost_parameters(old, new):
    """Return what a new parameter list lost or changed against the old one."""
    if old is None or new is None:
        return [] if old == new else ["signature"]
    problems = []
    new_by_name = {item[0]: item for item in new}
    for item in old:
        if new_by_name.get(item[0]) != item:
            problems.append(f"parameter {item[0]} {item[1:]} -> {new_by_name.get(item[0])}")
    first = [item[0] for item in old if item[1] in POSITIONAL]
    if [item[0] for item in new if item[1] in POSITIONAL][: len(first)] != first:
        problems.append("positional order")
    old_names = {item[0] for item in old}
    problems += [
        f"new parameter {item[0]} without default"
        for item in new
        if item[0] not in old_names and item[2] == UNSET and not item[1].startswith("VAR")
    ]
    return problems


def lost(old, new, path=""):
    """Return every difference of ``new`` that breaks what ``old`` promised."""
    if new == INHERITED:
        return []
    if isinstance(old, list) and old and isinstance(old[0], list):
        return [f"{path}: {item}" for item in lost_parameters(old, new)]
    if isinstance(old, dict):
        if not isinstance(new, dict):
            return [f"{path}: was a mapping, now {new!r}"]
        found = []
        for key, value in old.items():
            if key not in new:
                found.append(f"{path}.{key}: removed")
            else:
                found += lost(value, new[key], f"{path}.{key}")
        return found
    return [] if old == new else [f"{path}: {old!r} -> {new!r}"]


def schema_losses(old, new):
    """Return schema keys removed, enum values removed and required keys added."""
    found = [f"schema key {key} removed" for key in set(old["paths"]) - set(new["paths"])]
    for key, values in old["lists"].items():
        now = new["lists"].get(key, [])
        if key.endswith("enum"):
            found += [f"{key}: value {value} removed" for value in set(values) - set(now)]
        else:
            found += [f"{key}: {value} is newly required" for value in set(now) - set(values)]
    return found


@pytest.fixture(scope="module")
def frozen():
    """Return the stored 0.5.0 surface."""
    return json.loads(FROZEN.read_text())


def test_the_frozen_file_is_the_one_that_was_written():
    """Editing or regenerating the 0.5.0 file changes its hash and fails here."""
    assert fingerprint_file() == FROZEN_FILE_HASH, RULE


def test_the_current_api_contains_the_whole_frozen_api(frozen):
    """Names, parameters (name, kind, default, order), the contract and the codes survive."""
    now = capture()
    found = []
    for key in ("scopes", "contract", "error_codes"):
        found += lost(frozen[key], now[key], key)
    found += [f"code {code} removed" for code in set(frozen["codes"]) - set(now["codes"])]
    found += [
        f"row code {code} removed" for code in set(frozen["row_codes"]) - set(now["row_codes"])
    ]
    assert not found, RULE + "\n" + "\n".join(found[:30])


def test_the_schemas_keep_every_key(frozen):
    """The case, economics, plant and study schemas lose no key and add no required key."""
    now = capture()["schemas"]
    found = [
        loss
        for name in frozen["schemas"]
        for loss in schema_losses(frozen["schemas"][name], now[name])
    ]
    assert not found, RULE + "\n" + "\n".join(found[:30])


def test_the_loss_check_sees_a_removed_and_a_changed_parameter():
    """The comparison itself fails on a lost name, a changed default and a reordered parameter."""
    old = [["a", "POSITIONAL_OR_KEYWORD", UNSET], ["b", "KEYWORD_ONLY", "1"]]
    assert lost_parameters(old, old + [["c", "KEYWORD_ONLY", "2"]]) == []
    assert lost_parameters(old, old[:1])
    assert lost_parameters(old, [old[0], ["b", "KEYWORD_ONLY", "2"]])
    assert lost_parameters(old, [["z", "POSITIONAL_OR_KEYWORD", UNSET], *old])
    assert lost_parameters(old, old + [["c", "KEYWORD_ONLY", UNSET]])
    assert schema_losses({"paths": ["a"], "lists": {}}, {"paths": [], "lists": {}})


@pytest.mark.parametrize("dotted", USED_BY_GEOMIND)
def test_every_name_geomind_uses_exists_and_is_frozen(dotted, frozen):
    """The named list exists in the code and in the frozen file."""
    parts = dotted.split(".")[1:]
    assert reduce(getattr, parts, gm) is not None
    scope = {"gm": "top"}.get(parts[0], parts[0])
    if len(parts) == 1:
        assert parts[0] in frozen["scopes"]["top"] or parts[0] == "__version__"
    elif scope in frozen["scopes"]:
        entry = frozen["scopes"][scope].get(parts[1])
        assert entry is not None, dotted
    else:
        entry = frozen["scopes"]["top"][parts[0]]
        assert parts[1] in entry["methods"], dotted
