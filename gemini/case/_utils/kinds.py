"""The closed lists of the case: equipment kinds with their cost basis, and gas species."""

from gemini.physics import gas

EQUIPMENT_KINDS = {
    "drilling": ("money_per_length", "per metre of well"),
    "production_pump": ("money_per_power", "per W of shaft power at the nominal flow"),
    "injection_pump": ("money_per_power", "per W of shaft power at the nominal flow"),
    "circulation_pump": ("money_per_power", "per W of shaft power at the nominal flow"),
    "heat_pump": ("money_per_power", "per W of capacity"),
    "boiler": ("money_per_power", "per W of capacity"),
    "electric_boiler": ("money_per_power", "per W of capacity"),
    "chp": ("money_per_power", "per W of electric capacity"),
    "absorption_chiller": ("money_per_power", "per W of capacity"),
    "adsorption_chiller": ("money_per_power", "per W of capacity"),
    "compression_chiller": ("money_per_power", "per W of capacity"),
    "heat_exchanger": ("money_per_conductance", "per W/K of conductance"),
    "cooler": ("money_per_power", "per W of capacity"),
    "pipe": ("money_per_length", "per metre"),
    "thermal_storage": ("money_per_volume", "per m3"),
    "ice_storage": ("money_per_volume", "per m3"),
    "degasser": ("money", "fixed amount"),
    "flare": ("money", "fixed amount"),
    "gas_makeup": ("money", "fixed amount"),
}
"""Every equipment kind: ``{kind: (quantity of its capex factor, cost basis)}``.

The keys of ``economics.capex`` and ``economics.opex.fixed``. A module that is
equipment declares one of these kinds."""

CAPEX_BASES = {
    "production_pump": {"money": "per unit"},
    "pipe": {"money_per_power_length": "per W of nominal capacity and per metre"},
    "heat_exchanger": {"money_per_power": "per W of nominal duty"},
    "thermal_storage": {"money_per_energy": "per J of energy capacity"},
    "ice_storage": {"money_per_energy": "per J of energy capacity"},
}
"""The other cost bases of a kind besides ``EQUIPMENT_KINDS``: ``{kind: {quantity: basis}}``.

The unit of ``economics.capex.<kind>`` tells which basis a factor is on (EUR/(W/K) or EUR/W for a
heat exchanger, EUR/m or EUR/MW/m for a pipe). A basis per unit counts one per module; any other
needs the size of the module in that quantity (``Equipment.cost_size_of``)."""

PRICED_WHEN_GIVEN = ("ice_storage",)
"""The kinds priced only when the economics gives their capex: ``is_priced``.

A module of such a kind adds no capex and no fixed opex, and ``gm.check`` asks nothing for it, when
``economics.capex.<kind>`` is absent; given, it is priced as every kind (its fixed opex and its
size are then needed). ``IceStorage`` gained its kind after 0.5.0, so a case written before prices
it as before: not at all."""


def is_priced(kind, economics):
    """Return whether equipment of ``kind`` is priced by ``economics`` (``PRICED_WHEN_GIVEN``)."""
    if kind is None:
        return False
    if kind not in PRICED_WHEN_GIVEN:
        return True
    return economics.capex is not None and getattr(economics.capex, kind, None) is not None


BASIS_SIZES = {
    "money_per_power": "power",
    "money_per_energy": "energy",
    "money_per_volume": "volume",
    "money_per_length": "length",
    "money_per_conductance": "thermal_conductance",
    "money_per_power_length": "power",
}
"""For a cost per a quantity, the quantity of the size it multiplies (``cost_size_of``).

A cost per W and metre (a pipe) multiplies the power size times ``cost_size()``, the length."""

POWER_KINDS = tuple(
    kind
    for kind, (quantity, _) in EQUIPMENT_KINDS.items()
    if "money_per_power" in (quantity, *CAPEX_BASES.get(kind, ()))
)
"""The kinds whose modules have a size in power, the capacity of a fixed opex per W and year."""

PRODUCTS = {
    "boiler": "heat",
    "electric_boiler": "heat",
    "chp": "electricity",
    "heat_pump": "heat",
    "compression_chiller": "cold",
    "absorption_chiller": "cold, or heat in heat pump mode",
    "adsorption_chiller": "cold",
}
"""The kinds that produce an energy, with what they produce: the keys of ``opex.per_energy``.

A module of such a kind names the ports of its product (``Equipment.product``)."""

GRID_GAS_SPECIES = tuple(gas.SPECIES)
"""The species of ``utilities.gas.composition``: ``SPECIES`` of ``gemini.physics.gas``."""

GAS_SPECIES = tuple(name for name in gas.SPECIES if name in ("CH4", "CO2", "N2", "H2S"))
"""The species of ``site.fluid.dissolved_gas``: those of ``SPECIES`` of ``gemini.physics.gas`` a
reservoir brine carries, so a stream takes every species a case accepts."""
