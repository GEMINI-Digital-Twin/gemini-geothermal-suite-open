"""Shared settings: folder paths, the fixed reservoir and fluid inputs of the challenge brief, and the plot style.

Every constant below comes from the SPE GeoHackathon 2026 challenge brief.
"""
import geo.gemini_path  # noqa: F401  (puts the GEMINI tree with our models first on sys.path)
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOLUTION = HERE.parent
PROJECT = SOLUTION.parent
DATA = PROJECT / "data" / "raw" / "challenge_20261028"   # the challenge input files (daily demand CSVs)
FIG = SOLUTION / "explore" / "figures"

from geo.InitParams import COLORS, fig_width, fig_height  # noqa: E402  (applies the house style)
import matplotlib.pyplot as plt  # noqa: E402

# fixed inputs, all from the challenge brief
DEPTH_M = 2500.0             # reservoir midpoint depth, m (true vertical depth)
GRADIENT_C_PER_KM = 30.0     # geothermal gradient, C per km
T_SURFACE_C = 12.0           # surface temperature, C
P_RES_BAR = 250.0            # reservoir pressure at DEPTH_M, bar
PERM_MD = 200.0              # reservoir permeability, mD
THICKNESS_M = 100.0          # reservoir thickness, m
RHO = 1030.0                 # brine density, kg/m3
MU_PA_S = 0.40e-3            # brine viscosity, Pa s
Q_MIN_M3H, Q_MAX_M3H = 50.0, 300.0   # allowed flow per doublet, m3/h
DT_BRINE_MAX_K = 40.0        # largest allowed cooling of the brine, K
T_SUPPLY_HEAT_C = 100.0      # district-heating supply temperature, C
T_SUPPLY_COLD_C = 20.0       # district-cooling supply temperature, C


def t_reservoir_c(depth_m=DEPTH_M):
    """Reservoir temperature at depth_m from the surface temperature and the gradient, C."""
    return T_SURFACE_C + GRADIENT_C_PER_KM * depth_m / 1000.0


def save(fig, name):
    """Save fig as PDF and 300 dpi PNG in the figures folder; returns nothing."""
    FIG.mkdir(exist_ok=True)
    fig.savefig(FIG / f"{name}.pdf")
    fig.savefig(FIG / f"{name}.png", dpi=300)
    print("saved", FIG / f"{name}.pdf")
