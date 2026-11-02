"""The case: the outside conditions over one period and the rules of third parties.

``gm.Case`` and the classes of its sections, in the order of ``case.json``: ``Time``, ``Site``
(``Ground``, ``Reservoir``, ``Fluid``, ``Air``), ``Demand`` (``Service``, ``CoolingService``),
``Utilities`` (``Electricity``, ``Gas``), ``Economics`` (its own file, ``economics.json``, with
``Capex``, ``Opex``, ``Energy``, ``Carbon``, ``Revenue``, ``Accounting``) and
``Requirement``. ``Range`` and ``Uncertainty`` are the shared objects of ``gemini.types.inputs``.
``roles()`` lists the roles and quantities a ``Requirement`` may name. The case sits above
``gm.plants`` and below ``gm.run``.
"""

from gemini.types.inputs import Range, Uncertainty

from .case import Case
from .demand import CoolingService, Demand, Service
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
from .roletable import roles
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
    "roles",
]
