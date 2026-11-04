"""Fixes and additions for GEMINI (TNO): pump similarity law, injector friction sign, heat pump with a brine floor.

Importing this package puts GEMINI's development tree first on sys.path: GEMINI_DEV_SRC if set, else the repository's own
src/ when this package sits inside it, else ~/src/gemini-dev/src.
"""
import os
import sys

_REPO_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), *[".."] * 5, "src")   # <gemini repo>/src when inside the repo
_IN_REPO = os.path.isdir(os.path.join(_REPO_SRC, "gemini_model"))
DEV_SRC = os.environ.get("GEMINI_DEV_SRC") or (os.path.abspath(_REPO_SRC) if _IN_REPO else os.path.expanduser("~/src/gemini-dev/src"))
if DEV_SRC not in sys.path:
    sys.path.insert(0, DEV_SRC)

import gemini_model  # noqa: E402  (binds the package now, whatever is inserted on sys.path later)

_dev_pkg = os.path.join(DEV_SRC, "gemini_model")
if os.path.isdir(_dev_pkg) and _dev_pkg not in gemini_model.__path__:
    gemini_model.__path__.append(_dev_pkg)   # submodules missing from an already imported release resolve from the dev tree
