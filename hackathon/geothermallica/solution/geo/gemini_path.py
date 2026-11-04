"""Put the GEMINI source tree with our five models first on sys.path.

Order: GEMINI_DEV_SRC if set, else <repo>/src when this solution sits inside the GEMINI fork,
else ~/src/gemini-geothermallica/src.
"""
import os
import sys
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parents[4] / "src"   # <gemini repo>/src when inside the fork
_DEFAULT = _REPO_SRC if (_REPO_SRC / "gemini_model").is_dir() else Path("~/src/gemini-geothermallica/src").expanduser()
DEV_SRC = os.path.expanduser(os.environ.get("GEMINI_DEV_SRC") or str(_DEFAULT))
if DEV_SRC not in sys.path:
    sys.path.insert(0, DEV_SRC)

try:
    import gemini_model.heatpump.heatpump_lift  # noqa: F401,E402
except ImportError as err:
    raise ImportError(f"GEMINI tree {DEV_SRC} has no geothermallica models; point GEMINI_DEV_SRC at the fork "
                      "(github.com/barteksarwa/gemini-geothermal-suite-open, branch geothermallica)") from err
