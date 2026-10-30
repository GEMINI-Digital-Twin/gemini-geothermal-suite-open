"""Agentic geothermal heating-and-cooling design workflow on top of GEMINI (SPE GeoHackathon 2026)."""

import sys
from pathlib import Path

# Make GEMINI's src/ importable when run from the repository root without PYTHONPATH.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
