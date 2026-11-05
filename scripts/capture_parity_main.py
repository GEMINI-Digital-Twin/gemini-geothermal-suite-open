"""Capture the parity outputs of ``origin/main`` into ``.tmp/parity/main.npz`` and ``main.json``.

    python scripts/capture_parity_main.py

Fetches ``origin/main``, checks it out as a detached worktree at ``.tmp/parity/main`` (the
working tree of this repository is never touched), runs ``scripts/parity/main_adapter.py`` there
with ``PYTHONPATH`` set to its ``src`` and writes the numbers of every case. The package
``gemini`` is not imported on that side. ``tests/e2e/test_parity_main.py`` compares the current
package against the capture.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.parity import cases, flatten  # noqa: E402

PARITY = ROOT / ".tmp/parity"
MAIN = PARITY / "main"


def git(*args, folder=ROOT):
    """Run git in ``folder`` and return its stripped output."""
    done = subprocess.run(
        ["git", "-C", str(folder), *args], check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def checkout_main():
    """Fetch ``origin/main`` and put it in the throw-away worktree; return its commit hash."""
    git("fetch", "origin", "main")
    sha = git("rev-parse", "FETCH_HEAD")
    if MAIN.exists():
        git("checkout", "--detach", "--force", sha, folder=MAIN)
    else:
        PARITY.mkdir(parents=True, exist_ok=True)
        git("worktree", "add", "--detach", str(MAIN), sha)
    return sha


def run_main(selected):
    """Run the cases through the adapter against the sources of the worktree."""
    stored, produced = PARITY / "cases.json", PARITY / "main_out.json"
    stored.write_text(json.dumps(selected))
    env = {**os.environ, "PYTHONPATH": str(MAIN / "src")}
    command = [sys.executable, str(ROOT / "scripts/parity/main_adapter.py"), stored, produced]
    subprocess.run([str(c) for c in command], check=True, cwd=MAIN, env=env)
    return json.loads(produced.read_text())


def version():
    """Return the version in ``pyproject.toml`` of the worktree."""
    for line in (MAIN / "pyproject.toml").read_text().splitlines():
        if line.startswith("version"):
            return line.split('"')[1]
    raise ValueError("no version in pyproject.toml of main")


def main():
    """Write ``main.npz`` (numeric leaves) and ``main.json`` (commit, version, inputs, text)."""
    sha = checkout_main()
    selected = cases.cases()
    outputs = run_main(selected)
    numbers, exact = {}, {}
    for name, result in outputs.items():
        for path, leaf in flatten.flat(result).items():
            if isinstance(leaf, np.ndarray):
                numbers[f"{name}{path}"] = leaf
            else:
                exact[f"{name}{path}"] = leaf
    np.savez(PARITY / "main.npz", **numbers)
    record = {"commit": sha, "version": version(), "cases": selected, "exact": exact}
    (PARITY / "main.json").write_text(json.dumps(record, indent=1))
    print(f"captured {len(outputs)} cases of main {record['version']} ({sha[:8]})")


if __name__ == "__main__":
    main()
