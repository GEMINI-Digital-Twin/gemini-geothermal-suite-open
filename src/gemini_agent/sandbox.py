"""Let the agent write a missing component model, test it, and register it.

The code is checked statically (only numeric / GEMINI imports, no file,
network or process access, no ``eval``/``exec``), written to the
workspace, and its tests run in a separate Python process with a time
limit. Only a model whose tests pass is imported and added to
``gemini_simulator.registry.COMPONENT_REGISTRY``.
"""

import ast
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

from gemini_model.model_abstract import Model
from gemini_simulator.registry import COMPONENT_REGISTRY

ALLOWED_IMPORTS = ("math", "numpy", "scipy", "typing", "dataclasses", "gemini_model", "pytest")
FORBIDDEN_NAMES = {
    "eval",
    "exec",
    "compile",
    "open",
    "__import__",
    "input",
    "breakpoint",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
}
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
SRC_DIR = Path(__file__).resolve().parents[1]


def static_check(code, extra_imports=()):
    """Return a list of reasons the code is not allowed (empty = ok)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error: {exc}"]
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
            for name in names:
                root = (name or "").split(".")[0]
                if root not in ALLOWED_IMPORTS and root not in extra_imports:
                    problems.append(f"import of '{name}' is not allowed")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            problems.append(f"use of '{node.id}' is not allowed")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            if node.attr not in ("__init__", "__name__", "__doc__"):
                problems.append(f"dunder attribute '{node.attr}' is not allowed")
    return problems


def write_model(name, code, test_code, register_as, workspace, timeout_s=60):
    """Check, test and register a model. Returns a result dict for the agent."""
    if not NAME_RE.match(name or ""):
        return {"ok": False, "error": "name must be snake_case, 3-41 characters"}
    if not NAME_RE.match(register_as or ""):
        return {"ok": False, "error": "register_as must be snake_case, 3-41 characters"}
    if register_as in COMPONENT_REGISTRY and not getattr(
        COMPONENT_REGISTRY[register_as], "_agent_generated", False
    ):
        return {"ok": False, "error": f"'{register_as}' is a built-in GEMINI component"}
    problems = static_check(code) + [
        f"test: {p}" for p in static_check(test_code, extra_imports=(name,))
    ]
    if "def test_" not in test_code:
        problems.append("test_code must define at least one test_ function")
    if problems:
        return {"ok": False, "error": "code rejected", "problems": problems}

    folder = Path(workspace) / "generated_models"
    folder.mkdir(parents=True, exist_ok=True)
    model_path = folder / f"{name}.py"
    test_path = folder / f"test_{name}.py"
    model_path.write_text(code, encoding="utf-8")
    test_path.write_text(test_code, encoding="utf-8")

    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.pathsep.join([str(SRC_DIR), str(folder)]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", test_path.name],
            cwd=folder,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"tests timed out after {timeout_s} s"}
    output = (proc.stdout + proc.stderr).strip().splitlines()
    tail = "\n".join(output[-15:])
    if proc.returncode != 0:
        return {"ok": False, "error": "tests failed", "pytest": tail}

    spec = importlib.util.spec_from_file_location(f"agent_generated.{name}", model_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    classes = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, Model) and obj.__module__ == module.__name__
    ]
    if len(classes) != 1:
        return {"ok": False, "error": f"expected one Model subclass, found {len(classes)}"}
    cls = classes[0]
    cls._agent_generated = True
    COMPONENT_REGISTRY[register_as] = cls
    return {
        "ok": True,
        "registered_as": register_as,
        "class": cls.__name__,
        "file": str(model_path),
        "pytest": output[-1] if output else "",
    }
