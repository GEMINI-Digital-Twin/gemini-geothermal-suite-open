"""Uncertainty and techno-economics layer for the GEMINI GeoHackathon designs.

Built on ``gemini_design``: it samples subsurface, demand, price and cost
parameters (each with a stated distribution and public source), re-runs
the full 365-day dispatch of a design for every sample, prices the result
with a sourced cost model, and reports the probability of meeting demand,
levelised-cost and CO2 distributions, tornado sensitivities and pairwise
design comparisons. ``gemini_uncertainty.tool`` exposes it as one agent tool.
"""
