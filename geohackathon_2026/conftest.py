"""Let pytest find GEMINI and this project's modules without setting PYTHONPATH."""

import sys
from pathlib import Path

HERE = Path(__file__).parent
for folder in (HERE.parent / "src", HERE / "cases", HERE / "agent"):
    sys.path.insert(0, str(folder))
