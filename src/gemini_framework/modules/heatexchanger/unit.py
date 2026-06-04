"""Heat exchanger unit (placeholder for heat exchanger modules)."""

from gemini_framework.abstract.unit_abstract import UnitAbstract


class HeatExchangerUnit(UnitAbstract):
    """Heat exchanger unit container for exchanger modules."""

    def __init__(self, unit_id, unit_name, plant):
        """Initialize heat exchanger unit."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)
