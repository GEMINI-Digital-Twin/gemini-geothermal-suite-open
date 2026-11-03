"""Fixes and additions for GEMINI (TNO), written to be copied upstream.

GEMINI's surface models (heat pump, simulator) live only on the development branch, so this package puts
GEMINI_DEV_SRC (default ~/src/gemini-dev/src) first on sys.path. Import it before geo.well / geo.plant so
gemini_model loads from the development tree; esp.py and pressure_drop.py are identical in both trees.
"""
import os
import sys

_REPO_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), *[".."] * 5, "src")   # solution/ inside <gemini repo>/hackathon/<team>/
DEV_SRC = os.environ.get("GEMINI_DEV_SRC") or (os.path.abspath(_REPO_SRC) if os.path.isdir(os.path.join(_REPO_SRC, "gemini_model")) else os.path.expanduser("~/src/gemini-dev/src"))
if DEV_SRC not in sys.path:
    sys.path.insert(0, DEV_SRC)

import gemini_model  # noqa: E402  (binds the package now, whatever is inserted on sys.path later)

_dev_pkg = os.path.join(DEV_SRC, "gemini_model")
if os.path.isdir(_dev_pkg) and _dev_pkg not in gemini_model.__path__:
    gemini_model.__path__.append(_dev_pkg)   # if the open release was imported first, its missing submodules (heatpump) resolve from the development tree
