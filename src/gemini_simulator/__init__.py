"""Offline plant simulator built on top of gemini_model components.

This package provides a small, explicit simulation engine built around
explicit, user-declared component-to-component connections executed in
declared order, adapted to work with ``gemini_model``'s
``calculate_output(u, x)`` signature.

Plant topologies are described by an explicit-connections JSON project
file (components + named port-to-port connections), loaded via
:mod:`gemini_simulator.project_loader`, so different plants are just
different JSON files -- no topology is inferred or hardcoded.
"""
