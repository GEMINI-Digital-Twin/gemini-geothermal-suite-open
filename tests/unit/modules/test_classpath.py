"""The path a checkpoint stores for a module class, and the import back."""

import pytest

import gemini as gm
from gemini.errors import ValidationError
from gemini.modules.classpath import class_path, import_class
from gemini.modules.pumps import ESP


def test_a_class_path_imports_the_same_class():
    """The path is ``module:qualname`` and the import returns the class."""
    assert class_path(ESP) == "gemini.modules.pumps.esp:ESP"
    assert import_class(class_path(ESP)) is ESP
    assert import_class(class_path(gm.plants.Doublet)) is gm.plants.Doublet


def test_a_path_that_is_not_a_module_class_is_refused():
    """Only a ``Module`` subclass is imported from a string."""
    with pytest.raises(ValidationError, match="is not a Module"):
        import_class("gemini.units.quantities:Power")
