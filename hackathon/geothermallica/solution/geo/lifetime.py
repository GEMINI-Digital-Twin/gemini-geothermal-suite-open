"""Doublet lifetime: years until the cold front reaches the producer (thermal breakthrough), and the pressure from neighbouring doublets.

Breakthrough: Gringarten-Sauty formula as in Wallmeier et al. 2025, Stanford report SGP-TR-229, eq. 9,
https://pangea.stanford.edu/ERE/db/GeoConf/papers/SGW/2025/Wallmeier.pdf
Interference: steady line sources as in DoubletCalc 1.4, eq. 7 (TNO 2014, report R11396),
https://acc.nlog.nl/sites/default/files/6ab98fc3-1ca1-4bbe-b0a2-c5a9658a3597_doubletcalc%20v143%20manual.pdf
Parameter sources are in the inline comments. t_bt_yr() returns years; interference_bar() a list of bar, one per injector.
"""
import math

from geo.common import MU_PA_S, PERM_MD, RHO, THICKNESS_M

# ThermoGIS = TNO's geothermal resource tool; its default properties: https://pythermogis-15909e.ci.tno.nl/theory/utcprops/contents/
SPACING_M = 1500.0                 # producer-to-injector distance at reservoir level, m; source: ThermoGIS default well_distance
PHI = 0.20                         # porosity; assumed, no source
RHO_C_ROCK = 2700.0 * 1000.0       # rock heat capacity per volume, J/m3/K: ThermoGIS default density x specific heat
RHO_C_WATER = RHO * 4000.0         # brine heat capacity per volume, J/m3/K: brief density x 4 000 J/kg/K (assumed)
YEAR_S = 365.25 * 24 * 3600        # seconds per year
T_BT_MIN_YR = 30.0                 # shortest acceptable breakthrough time, years; assumed (ThermoGIS uses 1 % cooling at 50 years)
BASIS = ("t_BT = pi H L^2 (rho c)_a / (3 Q rho_w c_w), Gringarten-Sauty via Wallmeier et al. 2025 eq. 9 [L]; phi 0.20 [A], rock 2 700 kg/m3 "
         "x 1 000 J/kg/K and L 1 500 m ThermoGIS defaults [L], WNB practice 1 000-1 500 m (Willems 2017) [L]; interference = steady line "
         "sources, DoubletCalc 1.4 eq. 7 form, injectors on one line D apart, producers L away [L, A]; k 200 mD, H 100 m, mu 0.40 mPa s [D]")


def rho_c_aquifer(phi=PHI):
    """Heat capacity per volume of the water-filled rock, J/m3/K."""
    return phi * RHO_C_WATER + (1 - phi) * RHO_C_ROCK


def t_bt_yr(q_m3h, spacing_m=SPACING_M, h_m=THICKNESS_M, phi=PHI):
    """Thermal breakthrough time (t_BT): first arrival of the cold front at the producer, years."""
    return math.pi * h_m * spacing_m ** 2 * rho_c_aquifer(phi) / (3 * q_m3h / 3600 * RHO_C_WATER) / YEAR_S


def spacing_for_yr(years, q_m3h, h_m=THICKNESS_M, phi=PHI):
    """Well spacing that gives a breakthrough time of `years`, m."""
    return SPACING_M * math.sqrt(years / t_bt_yr(q_m3h, SPACING_M, h_m, phi))


def interference_bar(n, q_m3h, spacing_m=SPACING_M, doublet_spacing_m=None):
    """Extra pressure at each injector from the other n-1 doublets in a row, bar (one value per injector)."""
    d = spacing_m if doublet_spacing_m is None else doublet_spacing_m
    unit = q_m3h / 3600 * MU_PA_S / (2 * math.pi * PERM_MD * 9.869e-16 * THICKNESS_M) / 1e5
    return [sum(unit * math.log(math.hypot(spacing_m, (i - j) * d) / (abs(i - j) * d)) for j in range(n) if j != i) for i in range(n)]
