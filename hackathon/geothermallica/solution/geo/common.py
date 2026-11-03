"""Shared bits: paths, challenge inputs, plot style."""
import geo.gemini_contrib  # noqa: F401  (GEMINI development tree first, or this repository's own src/ when solution/ sits inside it)
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOLUTION = HERE.parent
PROJECT = SOLUTION.parent
DATA = PROJECT / "data" / "raw" / "challenge_20261028"
FIG = SOLUTION / "explore" / "figures"

sys.path.insert(0, os.environ.get("GEMINI_SRC", os.path.expanduser("~/src/gemini-geothermal-suite-open/src")))

from geo.InitParams import COLORS, fig_width, fig_height  # noqa: E402  (applies the house style)
import matplotlib.pyplot as plt  # noqa: E402

# fixed inputs from the requirements PDF [D]
DEPTH_M = 2500.0
GRADIENT_C_PER_KM = 30.0
T_SURFACE_C = 12.0
P_RES_BAR = 250.0
PERM_MD = 200.0
THICKNESS_M = 100.0
RHO = 1030.0
MU_PA_S = 0.40e-3
Q_MIN_M3H, Q_MAX_M3H = 50.0, 300.0
DT_BRINE_MAX_K = 40.0
T_SUPPLY_HEAT_C = 100.0
T_SUPPLY_COLD_C = 20.0


def t_reservoir_c(depth_m=DEPTH_M):
    return T_SURFACE_C + GRADIENT_C_PER_KM * depth_m / 1000.0


def save(fig, name):
    FIG.mkdir(exist_ok=True)
    fig.savefig(FIG / f"{name}.pdf")
    fig.savefig(FIG / f"{name}.png", dpi=300)
    print("saved", FIG / f"{name}.pdf")
