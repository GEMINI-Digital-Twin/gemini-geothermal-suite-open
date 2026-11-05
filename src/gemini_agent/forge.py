"""Model Forge: the agent generates new GEMINI component models at runtime, safely.

The LLM never writes Python. It writes a declarative JSON model spec:

    {"name": "seasonal_storage_screening",
     "description": "...", "reference": "...",
     "inputs":     {"summer_surplus_gwh": {"unit": "GWh", "description": "..."}, ...},
     "parameters": {"recovery_efficiency": {"value": 0.7, "unit": "-", "description": "..."}, ...},
     "outputs":    {"recovered_gwh": {"expr": "min(summer_surplus_gwh, capacity_gwh) *
     recovery_efficiency",
                                      "unit": "GWh", "description": "..."}, ...},
     "invariants": ["recovered_gwh <= summer_surplus_gwh", ...],
     "tests": [{"inputs": {...}, "expect": {"recovered_gwh": 14.0}, "tol": 1e-6}, ...]}

The forge then:
1. parses every expression to an AST and accepts only arithmetic, comparisons,
   boolean logic, conditional expressions and a whitelist of math functions over
   declared names (no attribute access, subscripts, imports or statements);
2. generates a GEMINI ``StaticModel`` subclass (``gemini_model/generated/<name>.py``)
   and a pytest module from the spec's tests and invariants;
3. runs the tests; only if they pass, registers the type in GEMINI's
   ``COMPONENT_REGISTRY`` (usable from plant JSON and by the agent).
Validation errors are returned in plain words so a small LLM can fix the spec.
"""

from __future__ import annotations

import ast
import importlib
import json
import keyword
import math
import re
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from gemini_simulator.registry import COMPONENT_REGISTRY

ROOT = Path(__file__).resolve().parents[2]
GEN_PKG = ROOT / "src" / "gemini_model" / "generated"
GEN_TESTS = ROOT / "unit_test" / "gemini_model" / "generated"
FUNCS = {
    "min": "min",
    "max": "max",
    "abs": "abs",
    "exp": "math.exp",
    "log": "math.log",
    "log10": "math.log10",
    "sqrt": "math.sqrt",
    "pow": "math.pow",
    "sin": "math.sin",
    "cos": "math.cos",
    "tanh": "math.tanh",
}
CONSTS = {"pi": "math.pi", "e": "math.e"}
ALLOWED = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.BoolOp,
    ast.IfExp,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.FloorDiv,
    ast.USub,
    ast.UAdd,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Eq,
    ast.NotEq,
)
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


class VarSpec(BaseModel):
    unit: str = "-"
    description: str = ""


class ParamSpec(VarSpec):
    value: float


class OutSpec(VarSpec):
    expr: str


class TestSpec(BaseModel):
    inputs: dict[str, float]
    parameters: dict[str, float] = Field(default_factory=dict)
    expect: dict[str, float | list[float]] = Field(default_factory=dict)
    tol: float = 1e-6


class ModelSpec(BaseModel):
    """Declarative model specification written by the agent."""

    name: str
    description: str
    reference: str = ""
    inputs: dict[str, VarSpec]
    parameters: dict[str, ParamSpec] = Field(default_factory=dict)
    outputs: dict[str, OutSpec]
    invariants: list[str] = Field(default_factory=list)
    tests: list[TestSpec] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        if not NAME_RE.match(v) or keyword.iskeyword(v):
            raise ValueError(
                "name must be snake_case, 2-41 chars, start with a letter (e.g. 'seasonal_storage')"
            )
        return v


def _check_expr(expr: str, known: set[str], where: str) -> ast.Expression:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"{where}: cannot parse '{expr}' ({exc.msg})") from None
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED):
            raise ValueError(
                f"{where}: '{type(node).__name__}' is not allowed in '{expr}'. Use arithmetic, "
                f"comparisons, 'x if c else y' and functions {sorted(FUNCS)}."
            )
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCS:
                raise ValueError(
                    f"{where}: function not allowed in '{expr}'. Allowed: {sorted(FUNCS)}."
                )
        elif (
            isinstance(node, ast.Name)
            and node.id not in known
            and node.id not in FUNCS
            and node.id not in CONSTS
        ):
            raise ValueError(
                f"{where}: unknown name '{node.id}' in '{expr}'. Declare it as an input or "
                f"parameter, or define an earlier output. Known: {sorted(known)}."
            )
        elif isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ValueError(f"{where}: only numeric constants are allowed in '{expr}'.")
    return tree


class _Py(ast.NodeTransformer):
    """Rewrite names to their Python locations (inputs/params/outputs/math)."""

    def __init__(self, inputs, params, outs):
        self.i, self.p, self.o = inputs, params, outs

    def visit_Name(self, node):
        n = node.id
        if n in self.i:
            src = f"u[{n!r}]"
        elif n in self.p:
            src = f"self.parameters[{n!r}]"
        elif n in self.o:
            src = f"y[{n!r}]"
        elif n in CONSTS:
            src = CONSTS[n]
        elif n in FUNCS:
            src = FUNCS[n]
        else:  # pragma: no cover - rejected earlier
            raise ValueError(n)
        return ast.parse(src, mode="eval").body


def validate(spec: ModelSpec) -> list[str]:
    """Static checks; returns a list of plain-language problems (empty = OK)."""
    problems = []
    names = list(spec.inputs) + list(spec.parameters) + list(spec.outputs)
    for n in names:
        if not NAME_RE.match(n):
            problems.append(f"variable '{n}' must be snake_case starting with a letter")
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        problems.append(f"names used twice: {sorted(dup)}")
    known = set(spec.inputs) | set(spec.parameters)
    for o, os_ in spec.outputs.items():
        try:
            _check_expr(os_.expr, known, f"output '{o}'")
        except ValueError as exc:
            problems.append(str(exc))
        known.add(o)
    for inv in spec.invariants:
        try:
            _check_expr(inv, known, "invariant")
        except ValueError as exc:
            problems.append(str(exc))
    for k, t in enumerate(spec.tests):
        missing = set(spec.inputs) - set(t.inputs)
        if missing:
            problems.append(f"test {k}: missing inputs {sorted(missing)}")
        bad = set(t.expect) - set(spec.outputs)
        if bad:
            problems.append(f"test {k}: expects unknown outputs {sorted(bad)}")
    if (
        problems == []
        and GEN_PKG.joinpath(f"{spec.name}.py").exists() is False
        and spec.name in COMPONENT_REGISTRY
    ):
        problems.append(
            f"'{spec.name}' clashes with an existing GEMINI component type; choose another name"
        )
    return problems


def _camel(name: str) -> str:
    return "".join(p.capitalize() for p in name.split("_"))


def generate_source(spec: ModelSpec) -> str:
    """Python source of the GEMINI StaticModel subclass."""
    tr = _Py(set(spec.inputs), set(spec.parameters), set(spec.outputs))
    lines = []
    for o, os_ in spec.outputs.items():
        tree = tr.visit(ast.parse(os_.expr, mode="eval"))
        lines.append(
            f"        y[{o!r}] = {ast.unparse(tree.body)}  # [{os_.unit}] {os_.description}"
        )
    params = {k: v.value for k, v in spec.parameters.items()}
    doc_in = "\n".join(f"    - ``{k}`` [{v.unit}]: {v.description}" for k, v in spec.inputs.items())
    doc_p = "\n".join(
        f"    - ``{k}`` = {v.value} [{v.unit}]: {v.description}" for k, v in spec.parameters.items()
    )
    doc_o = "\n".join(
        f"    - ``{k}`` [{v.unit}] = ``{v.expr}``: {v.description}" for k, v in spec.outputs.items()
    )
    return f'''"""{spec.description}

Generated by the GeoDesign Model Forge from a declarative spec (do not edit by hand).
Reference: {spec.reference or "-"}

Inputs (u):
{doc_in}

Parameters:
{doc_p or "    (none)"}

Outputs:
{doc_o}
"""

import math  # noqa: F401  (used by generated expressions)

from gemini_model.model_abstract import StaticModel

SPEC = {json.dumps(spec.model_dump(), indent=None)!r}


class {_camel(spec.name)}(StaticModel):
    """{spec.description}"""

    DEFAULTS = {params!r}

    def __init__(self):
        """Model initialization with default parameters."""
        self.parameters = dict(self.DEFAULTS)
        self.output = {{}}

    def update_parameters(self, parameters):
        """Update model parameters."""
        for key, value in parameters.items():
            self.parameters[key] = value

    def initialize_state(self, x):
        """Static model: no state."""
        pass

    def update_state(self, u, x):
        """Static model: no state."""
        pass

    def calculate_output(self, u, x=None):
        """Evaluate the generated equations."""
        y = {{}}
{chr(10).join(lines)}
        self.output = y

    def get_output(self):
        """Get output of the model."""
        return self.output
'''


def generate_tests(spec: ModelSpec) -> str:
    """Pytest module from the spec's test cases and invariants."""
    cls = _camel(spec.name)
    inv = [
        ast.unparse(
            _Py(set(spec.inputs), set(spec.parameters), set(spec.outputs))
            .visit(ast.parse(i, mode="eval"))
            .body
        ).replace("self.parameters", "m.parameters")
        for i in spec.invariants
    ]
    cases = json.dumps([t.model_dump() for t in spec.tests])
    return f'''"""Generated tests for {spec.name} (Model Forge)."""

import math  # noqa: F401

import pytest

from gemini_model.generated.{spec.name} import {cls}

CASES = {cases}
INVARIANTS = {inv!r}


@pytest.mark.parametrize("case", CASES)
def test_{spec.name}(case):
    m = {cls}()
    m.update_parameters(case["parameters"])
    u = case["inputs"]
    m.calculate_output(u)
    y = m.get_output()
    for k, v in y.items():
        assert isinstance(v, (int, float, bool)) and v == v, f"output {{k}} is not a finite number"
    for k, exp in case["expect"].items():
        if isinstance(exp, list):
            assert (
                exp[0] - case["tol"] <= y[k] <= exp[1] + case["tol"]
            ), f"{{k}}={{y[k]}} not in {{exp}}"
        else:
            assert y[k] == pytest.approx(
                exp, abs=case["tol"], rel=1e-6
            ), f"{{k}}={{y[k]}} != {{exp}}"
    for inv in INVARIANTS:
        assert eval(inv, {{"math": math, "u": u, "y": y, "m": m}}), f"invariant failed: {{inv}}"
'''


def parse_spec(spec_json: str | dict) -> dict:
    """The spec as a dict. Small models hand it over as a JSON string, a code-fenced string,
    a string with escaped newlines, or a Python-literal dict: all are accepted."""
    if isinstance(spec_json, dict):
        return spec_json
    s = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", spec_json.strip())
    for cand in (s, s.replace("\\n", "\n").replace("\\t", " ").replace('\\"', '"')):
        try:
            return json.loads(cand)
        except Exception:
            pass
        try:
            v = ast.literal_eval(cand)
            if isinstance(v, dict):
                return v
        except Exception:
            pass
    return json.loads(s)  # raises the original error


def forge(spec_json: str | dict, register: bool = True) -> dict:
    """Validate -> generate -> test -> register. Returns a plain report for the agent."""
    try:
        spec = ModelSpec(**parse_spec(spec_json))
    except Exception as exc:
        return {"ok": False, "stage": "parse", "problems": [str(exc)[:800]]}
    problems = validate(spec)
    if problems:
        return {"ok": False, "stage": "validate", "problems": problems}
    GEN_PKG.mkdir(parents=True, exist_ok=True)
    GEN_TESTS.mkdir(parents=True, exist_ok=True)
    (GEN_PKG / "__init__.py").touch()
    (GEN_TESTS / "__init__.py").touch()
    src_path = GEN_PKG / f"{spec.name}.py"
    test_path = GEN_TESTS / f"test_{spec.name}.py"
    previous = {
        p: p.read_text() for p in (src_path, test_path) if p.exists()
    }  # restored if the new one fails
    src_path.write_text(generate_source(spec))
    test_path.write_text(generate_tests(spec))
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(test_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )
    passed = proc.returncode == 0
    tail = proc.stdout.strip().splitlines()[-12:]
    report = {
        "ok": passed,
        "stage": "tests",
        "model_type": spec.name,
        "class": _camel(spec.name),
        "source": str(src_path.relative_to(ROOT)),
        "tests": str(test_path.relative_to(ROOT)),
        "n_tests": len(spec.tests),
        "n_invariants": len(spec.invariants),
        "pytest": tail,
    }
    if passed and register:
        mod = importlib.import_module(f"gemini_model.generated.{spec.name}")
        mod = importlib.reload(mod)
        COMPONENT_REGISTRY[spec.name] = getattr(mod, _camel(spec.name))
        report["registered_in_gemini_registry"] = True
    elif not passed:
        for p in (src_path, test_path):  # never leave an untested model (or an orphan test) behind
            if p in previous:
                p.write_text(previous[p])
            else:
                p.unlink(missing_ok=True)
        report["registered_in_gemini_registry"] = False
        report["hint"] = (
            "Fix the equations or the expected test values and call generate_model again."
        )
    return report


def run_model(model_type: str, inputs: dict, parameters: dict | None = None) -> dict:
    """Evaluate any registered GEMINI component (incl. generated ones) once."""
    if model_type not in COMPONENT_REGISTRY:
        raise ValueError(
            f"Unknown model '{model_type}'. Generate it first or pick one of "
            f"{sorted(COMPONENT_REGISTRY)}"
        )
    m = COMPONENT_REGISTRY[model_type]()
    if parameters:
        m.update_parameters(parameters)
    m.calculate_output(inputs)
    return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in m.get_output().items()}


def load_generated():
    """Register previously generated models (called at import of the tools)."""
    if not GEN_PKG.exists():
        return
    for f in GEN_PKG.glob("*.py"):
        if f.stem == "__init__":
            continue
        try:
            mod = importlib.import_module(f"gemini_model.generated.{f.stem}")
            COMPONENT_REGISTRY.setdefault(f.stem, getattr(mod, _camel(f.stem)))
        except Exception:  # a broken file must not break the agent
            continue


_ = math  # keep import (used in generated code namespace)
