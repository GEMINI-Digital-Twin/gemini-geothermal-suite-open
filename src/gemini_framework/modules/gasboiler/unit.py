"""Gas boiler unit (placeholder for gas boiler modules)."""

from gemini_framework.abstract.unit_abstract import UnitAbstract
from gemini_framework.framework.data_filtering import DataFiltering


class GasBoilerUnit(UnitAbstract):
    """Gas boiler unit container for boiler modules."""

    def __init__(self, unit_id, unit_name, plant):
        """Initialize gas boiler unit."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)
        self.modules["preprocessor"].append(DataFiltering(self))
