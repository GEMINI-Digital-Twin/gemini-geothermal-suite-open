"""The grid gas of the sample cases, for the tests that need a grid gas."""

GRID_COMPOSITION = {
    "CH4": 82.5204 / 100.0307,
    "C2H6": 3.9562 / 100.0307,
    "C3H8": 1.2752 / 100.0307,
    "CO2": 1.1916 / 100.0307,
    "N2": 11.0873 / 100.0307,
}
"""Mole fractions of grid gas: a measured analysis, ``utilities.gas.composition`` of the samples.

NGN Netzgesellschaft Niederrhein mbH, Gasbeschaffenheiten NKP07, January 2026 (published 19 March
2026): CH4 82.5204, C2H6 3.9562, C3H8 0.8211, CO2 1.1916, N2 11.0873 mol%, the published molar mass
18.7155 kg/kmol and CO2 factor 0.056474 t/GJ. The 0.4541 mol% of butanes and heavier is lumped into
C3H8, and the analysis, which sums to 100.0307 mol%, is scaled to one.
"""
