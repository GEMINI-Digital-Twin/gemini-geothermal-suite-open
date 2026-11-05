"""The compatibility surface of the public API: signatures, module contract, error codes, schemas.

``public_api_0_5_0.json`` is written once, from the code of version 0.5.0, and never regenerated:
from 0.5.0 on the API is backward compatible, so the current API must contain everything in it.
"""

import enum
import hashlib
import inspect
import json

import gemini as gm
from gemini.modules.declarations import State
from tests.fixtures.capture_public_api import NAMESPACES, ROOT

FROZEN = ROOT / "tests" / "fixtures" / "public_api_0_5_0.json"
SCHEMAS = ("case", "economics", "plant", "study")
SCOPES = ("top", "streams", "errors", "modules") + NAMESPACES
POSITIONAL = ("POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD")
UNSET = "<none>"
INHERITED = "<inherited>"
"""A method gemini did not write: its signature is Python's or pydantic's, and varies with them."""


def _default(parameter):
    if parameter.default is inspect.Parameter.empty:
        return UNSET
    text = repr(parameter.default)
    return "<object>" if " at 0x" in text else text


def parameters(function):
    """Return ``[[name, kind, default]]`` of a callable without ``self`` and ``cls``."""
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return None
    return [
        [name, parameter.kind.name, _default(parameter)]
        for name, parameter in signature.parameters.items()
        if name not in ("self", "cls")
    ]


def _written_by_gemini(owner, name):
    home = next((klass for klass in owner.__mro__ if name in vars(klass)), type(owner))
    return home.__module__.split(".")[0] == "gemini"


def _methods(owner):
    found = {}
    for name, member in inspect.getmembers(owner):
        if name.startswith("_") and name != "__init__":
            continue
        if not _written_by_gemini(owner, name):
            found[name] = INHERITED
        elif isinstance(inspect.getattr_static(owner, name), property):
            found[name] = "property"
        elif callable(member):
            found[name] = parameters(member)
    return found


def _member(value):
    if inspect.isclass(value):
        call = INHERITED if issubclass(value, enum.Enum) else parameters(value)
        return {"class": call, "methods": _methods(value)}
    if inspect.ismodule(value):
        return "module"
    return parameters(value) if callable(value) else type(value).__name__


def _scope(name):
    module = gm if name == "top" else getattr(gm, name)
    skip = set(gm.modules.names()) if name == "modules" else set()
    return {key: _member(getattr(module, key)) for key in module.__all__ if key not in skip}


def _walk(node, path, paths, lists):
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            paths.add(here)
            _walk(value, here, paths, lists)
    elif isinstance(node, list):
        if all(isinstance(item, (str, int, float, bool)) or item is None for item in node):
            lists[path] = sorted(map(str, node))
        for item in node:
            _walk(item, f"{path}[]", paths, lists)


def schema_keys(name):
    """Return the key paths of a schema file, and its ``required`` and ``enum`` lists by path."""
    paths, lists = set(), {}
    _walk(
        json.loads((ROOT / "docs" / "schemas" / f"{name}.schema.json").read_text()),
        "",
        paths,
        lists,
    )
    keep = {key: value for key, value in lists.items() if key.endswith(("required", "enum"))}
    return {"paths": sorted(paths), "lists": keep}


def capture():
    """Return the compatibility surface of the current code."""
    errors = {name: getattr(gm.errors, name) for name in gm.errors.__all__}
    return {
        "version": gm.__version__,
        "scopes": {name: _scope(name) for name in SCOPES},
        "contract": {
            "forward": parameters(gm.modules.Module.forward),
            "update": parameters(gm.modules.Module.update),
            "State": parameters(State),
        },
        "error_codes": {
            name: value.code
            for name, value in errors.items()
            if isinstance(value, type) and hasattr(value, "code")
        },
        "codes": list(gm.errors.CODES),
        "row_codes": sorted(gm.errors.ROW_CODES),
        "schemas": {name: schema_keys(name) for name in SCHEMAS},
    }


def fingerprint_file():
    """Return the hash of the stored baseline file, which the test holds as a constant."""
    return hashlib.sha256(FROZEN.read_bytes()).hexdigest()


if __name__ == "__main__":
    FROZEN.write_text(json.dumps(capture(), indent=1, sort_keys=True) + "\n")
    print(fingerprint_file())
