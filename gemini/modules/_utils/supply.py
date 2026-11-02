"""The margin a unit on a supply line states over the supply temperature of the case."""

from gemini.modules.declarations import Parameter
from gemini.types import TemperatureDifference


def supply_margin():
    """Return the parameter ``supply_margin`` of a unit that can sit on a supply line.

    A heating unit regulates its outlet to the supply temperature of ``demand.heating`` plus the
    margin, a cooling unit to the supply temperature of ``demand.cooling`` minus it; a run sets the
    ``temperature_setpoint`` from the case (``gm.run.apply_case``), so the supply temperature is
    written once, in the case. Empty on a unit that is on no supply line.
    """
    return Parameter(
        TemperatureDifference | None,
        default=None,
        description=(
            "Difference between the outlet setpoint and the supply temperature of the case, "
            "towards the safe side; empty on a unit that is on no supply line"
        ),
    )
