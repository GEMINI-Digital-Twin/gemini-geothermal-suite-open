"""Injection pump unit (placeholder for injection pump modules)."""

from gemini_framework.abstract.unit_abstract import UnitAbstract


class InjectionPumpUnit(UnitAbstract):
    """Injection pump unit container for pump modules."""

    def __init__(self, unit_id, unit_name, plant):
        """Initialize injection pump unit."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)
