"""Fimbul.jl reservoir simulation for the GeoHackathon design layer.

``simulate_doublet`` (fast, cached lookup; optional live Julia run) is the
tool the design agent calls; ``lifetime_performance`` feeds its production
temperature decline back into the annual runner; ``runner`` runs Fimbul.jl
itself.
"""

from gemini_design.fimbul.lifetime import lifetime_performance
from gemini_design.fimbul.lookup import simulate_doublet

__all__ = ["simulate_doublet", "lifetime_performance"]
