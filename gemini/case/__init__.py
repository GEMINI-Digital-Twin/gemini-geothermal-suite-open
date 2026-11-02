"""The case: the outside conditions over one period and the rules of third parties.

``gm.Case`` and the classes of its sections, in the order of ``case.json``: ``Time``, ``Site``
(``Ground``, ``Reservoir``, ``Fluid``, ``Air``), ``Demand`` (``Service``, ``CoolingService``),
``Utilities`` (``Electricity``, ``Gas``), ``Economics`` (its own file, ``economics.json``, with
``Capex``, ``Opex``, ``Energy``, ``Carbon``, ``Revenue``, ``Accounting``) and
``Requirement``. ``Range`` and ``Uncertainty`` are the shared objects of ``gemini.units.inputs``.
``gm.plants.roles()`` lists the roles and quantities a ``Requirement`` may name; the case reads
only that table of ``gm.plants`` and sits below ``gm.engine``.
"""

from gemini.units.inputs import Range, Uncertainty

from .case import Case
from .demand import CoolingService, Demand, Service
from .demand_frame import from_csv, from_values, profile_schema
from .economics import (
    Accounting,
    Capex,
    Carbon,
    DepthTable,
    Economics,
    Energy,
    Gwp,
    Opex,
    Revenue,
    Subsidy,
)
from .requirement import Requirement
from .site import Air, Fluid, Ground, Reservoir, Site
from .time import Time
from .utilities import Electricity, Gas, Utilities

__all__ = [
    "Case",
    "Time",
    "Site",
    "Ground",
    "Reservoir",
    "Fluid",
    "Air",
    "Demand",
    "Service",
    "CoolingService",
    "Utilities",
    "Electricity",
    "Gas",
    "Economics",
    "Capex",
    "DepthTable",
    "Opex",
    "Energy",
    "Carbon",
    "Revenue",
    "Subsidy",
    "Accounting",
    "Gwp",
    "Requirement",
    "Range",
    "Uncertainty",
    "from_csv",
    "from_values",
    "profile_schema",
]
