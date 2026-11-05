"""Hashes that say which inputs, code and defaults a cached result was made with.

The run ledger (:mod:`gemini_agent.memory`) and the benchmark oracle
(:mod:`gemini_agent.bench.oracle`) reuse earlier results. A result may only be
reused when it was made from the same demand (and weather) profile, the same
physics code and data files, and the same default assumptions. Otherwise a rerun
on new inputs, for example a judge's own demand files, could silently return
stale numbers.
"""

import hashlib
import inspect
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

_SRC = Path(__file__).resolve().parents[1]  # src/
CODE_PACKAGES = ("gemini_design", "gemini_model", "gemini_simulator")
# agent-side module whose code changes a run's gate verdict
AGENT_MODULES = ("physics_gate.py",)


HASHED_SUFFIXES = (".py", ".json", ".csv", ".jl", ".txt")


def _files(pkg):
    """Code and data files of a package, sorted by POSIX path (same order on Windows)."""
    root = _SRC / pkg
    files = [
        p
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix in HASHED_SUFFIXES
    ]
    return sorted(files, key=lambda p: p.relative_to(_SRC).as_posix())


@lru_cache(maxsize=1)
def code_hash():
    """Hash of the physics code and its data files (prices, Fimbul table and cache).

    Covers every file in ``gemini_design``, ``gemini_model`` and ``gemini_simulator``
    (Python and data, not docs), the physics gate and the agent-side design builder.
    """
    from gemini_agent.tools import make_design, split_overrides

    h = hashlib.sha256()
    for pkg in CODE_PACKAGES:
        for path in _files(pkg):
            h.update(path.relative_to(_SRC).as_posix().encode())
            h.update(path.read_bytes().replace(b"\r\n", b"\n"))  # same hash on Windows
    for name in AGENT_MODULES:
        h.update(name.encode())
        h.update((_SRC / "gemini_agent" / name).read_bytes().replace(b"\r\n", b"\n"))
    for fn in (make_design, split_overrides):
        h.update(inspect.getsource(fn).encode())
    return h.hexdigest()[:12]


def defaults_hash():
    """Hash of the brief values and default assumptions in effect (CHALLENGE, ASSUMPTIONS)."""
    from gemini_design.challenge import ASSUMPTIONS, CHALLENGE

    text = json.dumps({"c": CHALLENGE, "a": ASSUMPTIONS}, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def demand_hash(demand):
    """Hash of a demand table: dates, heating and cooling MW and any weather columns."""
    if demand is None:
        return None
    frame = pd.DataFrame(demand).reset_index(drop=True)
    h = hashlib.sha256()
    for col in sorted(frame.columns, key=str):
        h.update(str(col).encode())
        values = frame[col]
        if pd.api.types.is_datetime64_any_dtype(values):
            h.update("|".join(values.dt.strftime("%Y-%m-%d")).encode())
        elif pd.api.types.is_numeric_dtype(values):
            h.update(values.astype(float).round(6).to_numpy().tobytes())
        else:
            h.update("|".join(values.astype(str)).encode())
    return h.hexdigest()[:12]
