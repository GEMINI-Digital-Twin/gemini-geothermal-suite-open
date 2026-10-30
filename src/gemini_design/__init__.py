"""Heating and cooling plant design layer for the GEMINI GeoHackathon.

Built on top of ``gemini_model`` (component physics) and
``gemini_simulator`` (project JSON + connection solver). It provides the
deterministic, physics-checked tools an agent calls: load the challenge
inputs, size doublets at a chosen depth, dispatch the plant day by day
over a year, check the hard constraints, and price the result.
"""
