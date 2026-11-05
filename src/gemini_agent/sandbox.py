"""Let the agent write a missing component model, test it, and register it.

The code is checked statically (only numeric / GEMINI imports, no file,
network or process access, no ``eval``/``exec``), written to the
workspace, and two sets of tests run in separate Python processes with a
time limit: the agent's own pytest tests, then the harness acceptance
tests (:mod:`gemini_agent.acceptance`), which the agent did not write and
can not change. Only a model that passes both is imported and added to
``gemini_simulator.registry.COMPONENT_REGISTRY``.
"""

import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from gemini_agent import acceptance
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
# numpy / scipy functions that read or write files (``open`` alone is not enough)
FORBIDDEN_ATTRS = {
    "fromfile",
    "tofile",
    "load",
    "loadtxt",
    "genfromtxt",
    "fromregex",
    "save",
    "savez",
    "savez_compressed",
    "savetxt",
    "memmap",
    "open_memmap",
    "DataSource",
    "loadmat",
    "savemat",
    "mmread",
    "mmwrite",
    "readsav",
    "netcdf_file",
    "wavfile",
}
BASE_CLASSES = ("Model", "StaticModel", "DynamicModel")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
SRC_DIR = Path(__file__).resolve().parents[1]


def _root_name(node):
    """Name at the root of an attribute chain (``np`` in ``np.lib.format.open_memmap``)."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def static_check(code, extra_imports=()):
    """Return a list of reasons the code is not allowed (empty = ok)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error: {exc}"]
    problems = []
    module_names = set()  # names bound to imported modules (np, numpy, scipy.io, ...)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            module_names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            module_names.update(a.asname or a.name for a in node.names)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
            for name in names:
                root = (name or "").split(".")[0]
                if root not in ALLOWED_IMPORTS and root not in extra_imports:
                    problems.append(f"import of '{name}' is not allowed")
            if isinstance(node, ast.ImportFrom) and node.module == "gemini_model":
                wrong = [a.name for a in node.names if a.name in BASE_CLASSES]
                if wrong:
                    problems.append(
                        f"'{wrong[0]}' is not in gemini_model itself: use "
                        f"'from gemini_model.model_abstract import {wrong[0]}'"
                    )
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            problems.append(f"use of '{node.id}' is not allowed")
        elif (
            isinstance(node, ast.Attribute)
            and node.attr in FORBIDDEN_ATTRS
            and _root_name(node) in module_names
        ):
            problems.append(f"file access '{node.attr}' is not allowed")
        elif isinstance(node, ast.alias) and node.name in FORBIDDEN_ATTRS:
            problems.append(f"file access '{node.name}' is not allowed")
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

    folder = (Path(workspace) / "generated_models").resolve()  # subprocesses run with cwd=folder
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

    harness = acceptance_check(model_path, register_as, env, folder, timeout_s)
    if harness["problems"]:
        return {
            "ok": False,
            "error": "your tests pass, but the harness acceptance tests failed",
            "pytest": output[-1] if output else "",
            "harness_level": harness["level"],
            "harness_problems": harness["problems"],
            "contract": acceptance.describe_contracts().get(register_as),
        }

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
    cls._source_hash = hashlib.sha1(code.encode("utf-8")).hexdigest()[:12]
    COMPONENT_REGISTRY[register_as] = cls
    return {
        "ok": True,
        "registered_as": register_as,
        "class": cls.__name__,
        "file": str(model_path),
        "pytest": output[-1] if output else "",
        "harness_tests": "pass: " + harness["level"],
    }


def acceptance_check(model_path, register_as, env, cwd, timeout_s=60):
    """Run the harness acceptance tests on a model file in a separate process."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "gemini_agent.acceptance", str(model_path), register_as],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {"problems": [f"harness tests timed out after {timeout_s} s"], "level": "timeout"}
    lines = proc.stdout.strip().splitlines()
    try:
        return json.loads(lines[-1])
    except (IndexError, ValueError):
        err = (proc.stderr.strip().splitlines() or ["no output"])[-1]
        return {"problems": [f"harness tests crashed: {err}"], "level": "crash"}
