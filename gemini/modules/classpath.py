"""The path that plant files and checkpoints store for a module class, and the import back."""

import importlib

from gemini.errors import ValidationError
from gemini.modules.module import Module


def class_path(cls):
    """Return the ``module:qualname`` path that plant files and checkpoints store for a class.

    Together with ``import_class`` this is the only import-by-string in GEMINI: a saved plant or
    checkpoint must name the handwritten plant class that rebuilds its module tree.
    """
    return f"{cls.__module__}:{cls.__qualname__}"


def import_class(path):
    """Import the ``Module`` subclass named by a ``class_path`` string."""
    module_name, qualname = path.split(":", 1)
    value = importlib.import_module(module_name)
    for part in qualname.split("."):
        value = getattr(value, part)
    if not isinstance(value, type) or not issubclass(value, Module):
        raise ValidationError(f"Serialized class {path!r} is not a Module", code="invalid_format")
    return value
