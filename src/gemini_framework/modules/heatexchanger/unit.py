"""Heat exchanger unit (placeholder for heat exchanger modules)."""

from gemini_framework.abstract.unit_abstract import UnitAbstract
from gemini_framework.framework.data_filtering import DataFiltering


class HeatExchangerUnit(UnitAbstract):
    """Heat exchanger unit container for exchanger modules."""

    def __init__(self, unit_id, unit_name, plant):
        """Initialize heat exchanger unit."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)
        self.modules["preprocessor"].append(DataFiltering(self))
