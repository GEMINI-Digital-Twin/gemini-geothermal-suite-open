"""The data folders are found here; a missing one raises a clear error."""

import pytest

import gemini as gm
from tests.fixtures import paths


def test_the_package_finds_its_folders():
    """``examples/`` and ``tests/fixtures/`` are next to the package."""
    assert paths.EXAMPLES.parent == paths.PACKAGE.parent
    assert paths.DATA.parent.parent == paths.PACKAGE.parent


@pytest.mark.parametrize(
    ("call", "folder", "name"),
    [
        (lambda: paths.plant_values("Doublet"), "DATA", "plants/Doublet.json"),
        (lambda: paths.doublet_heat("data.csv"), "DATA", "doublet_heat/data.csv"),
        (lambda: paths.legacy_project(), "DATA", "legacy_project"),
        (lambda: paths.example("shallow_district"), "EXAMPLES", "shallow_district"),
    ],
)
def test_each_folder_of_the_data_lies_below_its_root(tmp_path, monkeypatch, call, folder, name):
    """Each function gives its file, and without the folder an error that names the file."""
    monkeypatch.setattr(paths, folder, tmp_path)
    assert call() == tmp_path / name
    monkeypatch.setattr(paths, folder, tmp_path / "absent")
    with pytest.raises(gm.errors.RunError, match="source checkout") as caught:
        call()
    assert caught.value.code == "inputs_missing"
    assert caught.value.path == name
    assert name in str(caught.value)
