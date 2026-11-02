"""What each plant class contains and what a study may do with it, found from the code."""

from gemini._utils import registry
from gemini.modules.grids import CoolingGrid, HeatingGrid
from gemini.plants._utils import leaves
from gemini.plants.doublet import Doublet
from gemini.plants.roles import roles_of


def _count(plant, cls):
    """Return how many modules of class ``cls`` the plant has below its root."""
    return sum(isinstance(module, cls) for path, module in plant.named_modules() if path)


def _schedulable(plant):
    """Whether ``gm.schedule`` plans the plant: it has a doublet below its root.

    The schedule gives the flow of each ``Doublet`` that is a child of the plant, and raises
    ``invalid_design`` for more than one ``HeatingGrid`` or ``CoolingGrid``. A plant that is a
    doublet itself, or has none, gets no flow.
    """
    heating, cooling = _count(plant, HeatingGrid), _count(plant, CoolingGrid)
    return bool(_count(plant, Doublet)) and max(heating, cooling) <= 1


def _ranges(plant):
    """Return the paths of the leaves a plant file may give a ``range`` for a study to search.

    These are ``size.doublets`` when the class takes that structural size, then every leaf of
    ``params`` that holds a number: a parameter, a control or a boundary of any module.
    """
    found = ["size.doublets"] if "doublets" in (getattr(plant, "_size", None) or {}) else []
    return found + leaves.numeric_paths(plant)


def capabilities():
    """Return what each plant class contains, plans and lets a study search.

    Every registered plant class is built at its smallest size and read. For each, the dict holds:

    - ``roles``: the roles (``gm.plants.roles()``) of which it has a unit;
    - ``schedulable``: whether ``gm.schedule`` can plan it;
    - ``ranges``: every leaf of the plant file that may state a ``range``: ``size.doublets`` when
      its class takes a structural size of that name, then ``params.<path>`` for each parameter,
      control and boundary that is a number (``params.depth``, ``params.doublet.nominal_flow``).

    Returns
    -------
    dict
        ``{plant class name: {"roles": list, "schedulable": bool, "ranges": list}}``.
    """
    result = {}
    for name in registry.names("plants"):
        plant = registry.get(name)()
        roles = {
            role for path, module in plant.named_modules() for role in roles_of(plant, path, module)
        }
        result[name] = {
            "roles": sorted(roles),
            "schedulable": _schedulable(plant),
            "ranges": _ranges(plant),
        }
    return result
