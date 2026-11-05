"""Curated user API and plant ownership contracts."""

import inspect
import json
import tomllib
from pathlib import Path

import gemini as gm
from tests.fixtures.capture_public_api import SNAPSHOT, capture, fingerprint
from tests.fixtures.sample_cases import example_plant

SNAPSHOTS = {
    "0.1.0": "f19ae90f18bb5a5a85e1b1f730276c9a50fdba0d46108c4bcd56488b48178a8b",
    "0.2.0": "cdfa3a358974d1b7ed055e0b94bd0711ffc54fff204bd0f9f4fe573a1ffe7b0d",
    "0.3.0": "98a5053ab31fbcd6432558ce481b181bbc1d361e933fdc1dba21920b2e01a3c4",
    "0.4.0": "4b80dd45200e479a329453542e6f90bf3d0f5eac37f66f0badd8dc87abc4d6d4",
    "0.5.0": "cd4c7005932a6d3918c006292fd7046eec95226640ee3cf4d3892077c92cca16",
    "0.5.1": "6d4e8da5a26f08918457e4a36cdaff02490c15dc7c11a1af4a14ad95008c7eb0",
    "0.5.2": "87e80ee76052df729e145c7b5a26bad88b53ab4a4220d39b5dd482883600a5c9",
    "0.5.3": "09c69731efd240b1a0463646ec433addb225e37d4e07f036c7ee9061a7984444",
    "0.5.4": "fc80a9d50828e72f64693f9bc387b6bb11022e1fc2a1992575f2f65eb8c30906",
    "0.5.5": "de33cfcd9a909813891f8446c982cff108f7e259b2a0df3c4513e1fb1e845e04",
    "0.5.6": "97930b80acfc4c42b5acc3da0e7dcaf9f4185d66ba1a133f052a6cef396349f3",
    "0.5.7": "a88a260b8685f662a3c9116ee6095c2bcd893e60e2f79afb582621d908531451",
    "0.5.8": "1eb0fc4f4fdf7fc1fa1fd0b090f8697941f8076ddbf1662eed8e45ba3750ed89",
    "0.5.9": "61c2c5feeadf1a88c296693332dc3b136c49628ab43e591c81aca7ad9851d3df",
    "0.5.10": "7cc6950c84ef35f5e79468cda41cdeae90addebe7f431dcb450a2ab455583184",
    "0.5.11": "19d16a247aae1135a127703e170b3d6e39a23daa3e3e37048c36a18600feb22a",
    "0.5.12": "b7096ad71deb9101693d5fd65a9bb350bd1458e26da85e5197ce354032f9cc84",
    "0.5.13": "ce83f227ffeadb55580b860a110a98f946db87bb1c301790c227d8dcfddd993b",
    "0.5.14": "96fe498e93c29799514fdcab0e8a288ce3949c615d46bfb7d3615585310350cc",
    "0.6.0": "71b988c79fc00a6142df7f0511ac4376da8499d8a5e4bb457b87ea4a60bcc119",
    "0.6.1": "45bde5061747496b18831fbe7a7b0aadecc7d7586abfab897f20fdc6f45f701a",
    "0.6.2": "f780cd863e379d39cd13bb355ef056dd16f30137f30f45a9890c368eb39c51d6",
    "0.6.3": "d1875b04bc10438688e5f25a0277cb8a9608083bc8216582b0b28fb324d5db21",
    "0.6.4": "8f3ab71ccac7bd4f051055062938520c2cbc1602e3b48ed9f755b6021b754375",
    "0.6.27": "c45ecde315698841a0290015c307025397dcee9d3285ba3dcf9cbf6b394080b1",
    "0.6.28": "c429f318eee67376948fa785c9c11e46602c5c79994cbf488cac51435ea54934",
}
"""Hash of the snapshot per ``gm.__version__``: a released entry never changes."""


EXPECTED = {
    "Module",
    "Plant",
    "Parameter",
    "Port",
    "Output",
    "Stream",
    "Fluid",
    "BRINE",
    "WATER",
    "Case",
    "Study",
    "check",
    "schedule",
    "simulate",
    "replay",
    "live",
    "resume",
    "call",
    "Results",
    "Dataset",
    "Engine",
    "modules",
    "plants",
    "case",
    "physics",
    "ops",
    "runtime",
    "units",
    "errors",
    "streams",
    "study",
    "evaluate",
    "analysis",
    "compiler",
}
"""The names of the top level, exactly."""


def test_public_names_and_docs():
    """Interactive completion exposes exactly the documented, individually documented names."""
    assert set(dir(gm)) == EXPECTED == set(gm.__all__)
    assert all(getattr(gm, name).__doc__ for name in EXPECTED)
    assert all(getattr(gm.modules, name).__doc__ for name in gm.modules.__all__)
    assert "Doublet" in gm.plants.names()


def test_readable_tree():
    """Printing a loaded plant displays nested equipment and scalar human-unit parameters."""
    plant = example_plant("DoubletHeatPlant")
    with gm.runtime.settings(display_units="field"):
        rendered = repr(plant)
    assert "DoubletHeatPlant(" in rendered and "(doublet): Doublet(" in rendered
    assert "ESP(" in rendered and "bar" in rendered and "°C" in rendered


def test_version_matches_the_package_metadata():
    """The version literal in ``gemini/__init__.py`` is the one in ``pyproject.toml``."""
    project = tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())
    assert gm.__version__ == project["project"]["version"]


def test_the_public_api_equals_the_stored_snapshot():
    """Every name, its parameter names and the schema files are as frozen."""
    stored = json.loads(SNAPSHOT.read_text())
    assert capture() == stored


def test_the_snapshot_changes_only_with_the_version():
    """A stored snapshot belongs to one version; changing it means raising the version."""
    stored = json.loads(SNAPSHOT.read_text())
    assert stored["version"] == gm.__version__
    assert fingerprint(stored) == SNAPSHOTS[gm.__version__]


def test_the_change_log_lists_the_version():
    """Each version has a line in the change log of the API page."""
    page = (Path(__file__).parents[2] / ".claude/docs/api.md").read_text()
    assert f"| {gm.__version__} |" in page.split("## Change log")[1]


def test_the_package_has_one_version():
    """``gm.API_VERSION`` is gone; ``gm.__version__`` is the one version."""
    assert not hasattr(gm, "API_VERSION")
    assert gm.__version__ == "0.6.28"


def test_every_economics_function_takes_the_plant_the_case_and_the_results():
    """``capex`` alone has no results; every function starts with the plant and the case."""
    for name in ("opex", "lcoh", "lcoc", "lcts", "annualised_cost", "co2", "npv", "payback"):
        arguments = list(inspect.signature(getattr(gm.evaluate, name)).parameters)
        assert arguments[:3] == ["plant", "case", "results"], name
    assert list(inspect.signature(gm.evaluate.capex).parameters)[:2] == ["plant", "case"]


def test_call_stays_beside_the_run_functions():
    """A call at one point is a run at one point; ``gm.modules.check`` is for developers."""
    assert "call" in gm.__all__ and "check" in gm.modules.__all__


def test_utils_stays_private():
    """Helpers are not part of the public API."""
    assert "_utils" not in gm.__all__


def test_the_old_project_import_is_not_in_the_package():
    """``gm.legacy`` and ``gm.Plant.from_legacy`` are gone."""
    assert not hasattr(gm, "legacy") and not hasattr(gm.Plant, "from_legacy")
