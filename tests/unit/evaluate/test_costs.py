"""Costs: capex, opex, annualised cost, levelised costs, NPV and payback."""

import pytest

import gemini as gm
from gemini._utils.jsonable import to_plain
from gemini.case._utils.kinds import EQUIPMENT_KINDS
from gemini.engine.apply import apply_case
from gemini.evaluate._utils import cost
from gemini.modules import CoolingGrid, Module
from gemini.physics import pumps
from gemini.streams.fluid import BRINE
from gemini.units import SECONDS_PER_YEAR, Quantity
from tests.fixtures.cases import FINANCE, costed_economics, make_case
from tests.fixtures.costed_plants import (
    HOURS,
    cooling_plant,
    day,
    heating_cooling_plant,
    heating_plant,
)
from tests.fixtures.designs import with_values
from tests.fixtures.errors import raises
from tests.fixtures.esp_design import ESP_DESIGN
from tests.fixtures.result_tables import make_results

ALL = dict(
    drilling=Quantity(1000.0, "currency/m"),
    production_pump=Quantity(0.5, "currency/W"),
    injection_pump=Quantity(0.4, "currency/W"),
    circulation_pump=Quantity(0.2, "currency/W"),
    heat_pump=Quantity(0.67, "currency/W"),
    boiler=Quantity(0.06, "currency/W"),
    electric_boiler=Quantity(0.03, "currency/W"),
    chp=Quantity(0.95, "currency/W"),
    absorption_chiller=Quantity(0.3, "currency/W"),
    adsorption_chiller=Quantity(0.35, "currency/W"),
    compression_chiller=Quantity(0.25, "currency/W"),
    heat_exchanger=Quantity(100.0, "currency/(W/K)"),
    cooler=Quantity(0.1, "currency/W"),
    pipe=Quantity(300.0, "currency/m"),
    thermal_storage=Quantity(50.0, "currency/m3"),
    ice_storage=Quantity(40.0, "currency/m3"),
    degasser=Quantity(1e6, "currency"),
    flare=Quantity(1e5, "currency"),
    gas_makeup=Quantity(2e4, "currency"),
)


"""A factor for every kind."""


def priced(kind, params, capex=ALL):
    """Return the capex of one module in a plant of its own, its ports aside."""
    plant = gm.Plant("One")
    plant.add(kind, name="unit", params=params)
    return gm.evaluate.capex(plant, make_case(economics={"capex": capex}))


@pytest.mark.parametrize(
    "kind, params, expected",
    [
        ("HeatPump", {"mode": "heating", "capacity": {"value": 10, "unit": "MW"}}, 0.67e7),
        ("HeatPump", {"mode": "cooling", "capacity": {"value": 10, "unit": "MW"}}, 0.25e7),
        ("Boiler", {"capacity": {"value": 10, "unit": "MW"}}, 0.06e7),
        ("ElectricBoiler", {"capacity": {"value": 10, "unit": "MW"}}, 0.03e7),
        ("CHP", {"electric_capacity": {"value": 1, "unit": "MW"}}, 0.95e6),
        ("AdsorptionChiller", {"capacity": {"value": 2, "unit": "MW"}}, 0.35 * 2e6),
        ("Cooler", {"capacity": {"value": 3, "unit": "MW"}}, 0.1 * 3e6),
        ("Pipe", {"length": {"value": 120, "unit": "m"}}, 300 * 120),
        ("ThermalStorage", {"volume": {"value": 200, "unit": "m3"}}, 50 * 200),
        ("Degasser", {}, 1.0e6),
        ("Flare", {}, 1e5),
        ("GasMakeup", {}, 2e4),
    ],
    ids=[
        "heat_pump",
        "compression_chiller",
        "boiler",
        "electric_boiler",
        "chp",
        "adsorption_chiller",
        "cooler",
        "pipe",
        "thermal_storage",
        "degasser",
        "flare",
        "gas_makeup",
    ],
)
def test_equipment_costs_come_from_its_design(kind, params, expected):
    """A factor times a capacity, a length or a volume, or a fixed item."""
    assert priced(kind, params).value == pytest.approx(expected)


def test_the_exchanger_and_the_absorption_chiller_cost_by_their_size():
    """Conductance and capacity."""
    exchanger = dict(thermal_conductance={"value": 1e6, "unit": "W/K"})
    assert priced("HeatExchanger", exchanger).value == pytest.approx(1e8)
    chiller = dict(capacity={"value": 1e7, "unit": "W"})
    assert priced("AbsorptionUnit", chiller).value == pytest.approx(3e6)


def test_a_circulation_pump_costs_by_its_shaft_power_at_the_nominal_flow():
    """Hydraulic power over the efficiency, at the flow and the rise of the design."""
    plant = gm.Plant("One")
    pump = plant.add(
        "CirculationPump",
        name="unit",
        params={
            "flow": {"value": 50, "unit": "kg/s"},
            "pressure_rise": {"value": 3, "unit": "bar"},
            "loop_pressure": {"value": 5, "unit": "bar"},
            "efficiency": 0.6,
        },
    )
    pump.fluid = BRINE
    density = pump.fluid.properties(0, 0).rho_l
    power = 50 / density * 3e5 / 0.6
    result = gm.evaluate.capex(plant, make_case(economics={"capex": ALL}))
    assert result.value == pytest.approx(0.2 * power)


def test_a_centrifugal_pump_costs_by_its_shaft_power_at_the_best_efficiency_flow():
    """The head of the curve at the best-efficiency flow, over the best efficiency."""
    params = {
        "head_coefficients": [3e5, -1e5, -2e6],
        "rated_frequency": {"value": 50, "unit": "Hz"},
        "best_efficiency": 0.7,
        "best_efficiency_flow": {"value": 0.1, "unit": "m3/s"},
        "motor_efficiency": 0.95,
    }
    head = 3e5 - 1e5 * 0.1 - 2e6 * 0.1**2
    expected = 0.2 * 0.1 * head / 0.7
    assert priced("CentrifugalPump", params).value == pytest.approx(expected)


DESIGN = {
    "depth": {"value": 2500, "unit": "m"},
    "gradient": {"value": 30, "unit": "K/km"},
    "surface_temperature": {"value": 12, "unit": "degC"},
    "permeability": {"value": 200, "unit": "mD"},
    "thickness": {"value": 100, "unit": "m"},
    "well_diameter": {"value": 0.244, "unit": "m"},
}


PUMP = {
    "nominal_flow": {"value": 300, "unit": "m3/h"},
    "pump_efficiency": 0.7,
    "nominal_wellhead_pressure": {"value": 10, "unit": "bar"},
} | ESP_DESIGN


def test_a_doublet_pays_for_its_wells_by_the_metre_and_its_pump_by_its_power():
    """The wells together are two depths; the pump is its shaft power at the nominal flow."""
    plant = gm.Plant("One")
    plant.add("Doublet", name="unit", params=DESIGN | PUMP)
    with_values(plant)
    case = make_case(economics={"capex": ALL})
    result = gm.evaluate.capex(plant, case)
    head = apply_case(plant, case).unit.esp.head_coefficients
    power = 300 / 3600 * pumps.head(0.0, 60.0, 1, head) / 0.7
    drilling = sum(
        item.value for item in result.parts["modules"].values() if item.parts["kind"] == "drilling"
    )
    assert drilling == pytest.approx(2 * 2500 * 1000.0)
    assert result.parts["modules"]["unit"].value == pytest.approx(0.5 * power)
    assert result.value == pytest.approx(2 * 2500 * 1000.0 + 0.5 * power)


def test_a_doublet_without_a_nominal_flow_cannot_price_its_pump():
    """Nothing is estimated: the error names the missing design value."""
    plant = gm.Plant("One")
    plant.add("Doublet", name="unit", params=DESIGN)
    with raises(gm.errors.ValidationError, "missing_value", match="nominal_flow"):
        gm.evaluate.capex(plant, make_case(economics={"capex": ALL}))


def test_the_capex_is_the_sum_of_the_modules_with_their_kinds_and_price_year():
    """Per module a value with its kind; the total, the currency and the price year."""
    case = make_case(economics={"capex": ALL, "price_year": 2015, "currency": "EUR"})
    result = gm.evaluate.capex(heating_plant(), case)
    assert to_plain(result) == {
        "value": 1e6,
        "unit": "currency",
        "modules": {"heat": {"value": 1e6, "unit": "currency", "kind": "degasser"}},
        "price_year": {"value": 2015, "unit": "-"},
    }


def test_a_plant_without_equipment_has_no_capex_with_a_reason():
    """The grids are not equipment: nothing is invented."""
    case = make_case(economics={"capex": ALL})
    result = gm.evaluate.capex(heating_plant(costed=False), case, on_error="record")
    assert result.value is None
    assert result.reason == cost.NO_COST
    assert result.unit == "currency"
    with raises(gm.errors.ValidationError, "no_value"):
        gm.evaluate.capex(heating_plant(costed=False), case)


def test_a_factor_the_case_lacks_is_missing_assumption_naming_the_kind():
    """A degasser without a factor: the error names its path, the record says why."""
    case = make_case(economics={"capex": {"boiler": Quantity(0.06, "currency/W")}})
    recorded = gm.evaluate.capex(heating_plant(), case, on_error="record")
    assert recorded.value is None and "economics.capex.degasser" in recorded.reason
    with raises(
        gm.errors.ValidationError,
        "missing_assumption",
        match=r"economics\.capex\.degasser",
    ):
        gm.evaluate.capex(heating_plant(), case)


def test_a_case_without_economics_is_missing_assumption():
    """No economics, no capex."""
    with raises(gm.errors.ValidationError, "missing_assumption", match="economics"):
        gm.evaluate.capex(heating_plant(), make_case())


def test_every_kind_but_the_ice_storage_is_declared_by_a_module():
    """Only the ice storage has no module that declares its kind.

    A heat pump is a ``heat_pump`` or, in cooling mode, a ``compression_chiller``.
    """
    declared = {
        module_class.equipment_kind
        for module_class in _subclasses(Module)
        if isinstance(getattr(module_class, "equipment_kind", None), str)
    }
    declared |= {"heat_pump", "compression_chiller"}
    assert set(EQUIPMENT_KINDS) - declared == {"ice_storage"}


def _subclasses(root):
    """Return every subclass of ``root``, at any depth."""
    found = set()
    for sub in root.__subclasses__():
        found |= {sub} | _subclasses(sub)
    return found


GRID_PER_YEAR = 100.0 * SECONDS_PER_YEAR


"""Grid electricity [J/year] of 100 W drawn all year."""


def priced_opex(fixed=None, capex=True, **prices):
    """Return a case whose economics holds ``prices`` [currency/J, currency/kg] and fixed shares.

    The degasser costs 1000 and its fixed opex is 1 %/yr unless ``fixed`` says otherwise.
    """
    shares = {"degasser": Quantity(1, "%/yr")} if fixed is None else fixed
    economics = {"opex": {"fixed": shares}} if shares else {}
    for name, price in prices.items():
        economics = economics | _price(name, Quantity(price, _unit(name)))
    if capex:
        economics["capex"] = {"degasser": Quantity(1000.0, "currency")}
    return make_case(economics=economics)


def _price(name, price):
    """Return the part of the economics that holds the price ``name``."""
    if name in ("electricity", "gas"):
        return {"energy": {name: price}}
    if name == "co2":
        return {"carbon": {"price": price}}
    return {"opex": {"variable": {name: price}}}


def _unit(name):
    """Return the unit of a price: per joule, or per kilogram for a material."""
    return "currency/J" if name in ("electricity", "gas") else "currency/kg"


def test_opex_adds_the_fixed_share_and_the_energy_bill():
    """1 % of a capex of 1000 is 10 a year; the electricity at 2e-8 per joule."""
    result = gm.evaluate.opex(heating_plant(), priced_opex(electricity=2e-8), day())
    components = {name: item.value for name, item in result.parts["components"].items()}
    assert {item.unit for item in result.parts["components"].values()} == {"currency/yr"}
    assert components["fixed"] == pytest.approx(10.0)
    assert components["electricity"] == pytest.approx(2e-8 * GRID_PER_YEAR, rel=1e-12)
    assert components["fuel"] == 0.0
    assert "co2" not in components and "variable" not in components
    assert result.value == pytest.approx(sum(components.values()), rel=1e-12)
    assert result.unit == "currency/yr"


def test_fixed_opex_is_listed_by_kind():
    """Each kind of equipment has its share of its capex."""
    result = gm.evaluate.opex(heating_plant(), priced_opex(electricity=2e-8), day())
    assert {kind: item.value for kind, item in result.parts["fixed_by_kind"].items()} == {
        "degasser": pytest.approx(10.0)
    }


def test_each_kind_has_its_own_share():
    """A degasser at 1 %/yr of 1000 and a flare at 3 %/yr of 2000."""
    economics = {
        "capex": {"degasser": Quantity(1000.0, "currency"), "flare": Quantity(2000.0, "currency")},
        "opex": {"fixed": {"degasser": Quantity(1, "%/yr"), "flare": Quantity(3, "%/yr")}},
        "energy": {"electricity": Quantity(0.0, "currency/J")},
    }
    result = gm.evaluate.opex(
        heating_cooling_plant(), make_case(economics=economics), day(cold=1.0)
    )
    fixed = {kind: item.value for kind, item in result.parts["fixed_by_kind"].items()}
    assert fixed == {"degasser": pytest.approx(10.0), "flare": pytest.approx(60.0)}
    assert result.parts["components"]["fixed"].value == pytest.approx(70.0)


def test_a_share_the_case_lacks_is_missing_assumption_naming_the_kind():
    """The degasser has a capex but no fixed share: the user is asked."""
    with raises(
        gm.errors.ValidationError,
        "missing_assumption",
        match=r"economics\.opex\.fixed\.degasser",
    ):
        gm.evaluate.opex(heating_plant(), priced_opex(fixed={}, electricity=2e-8), day())


def test_opex_needs_the_price_of_an_energy_the_run_draws():
    """Electricity is drawn but has no price: the user is asked, not guessed for."""
    with raises(
        gm.errors.ValidationError,
        "missing_assumption",
        match=r"economics\.energy\.electricity",
    ):
        gm.evaluate.opex(heating_plant(), priced_opex(), day())


def test_opex_without_equipment_reports_only_the_bill():
    """No equipment: the value is null and says why; the bill is still given."""
    result = gm.evaluate.opex(
        heating_plant(costed=False), priced_opex(electricity=2e-8), day(), on_error="record"
    )
    assert result.value is None and result.reason == cost.NO_COST
    assert result.parts["components"]["electricity"].value == pytest.approx(
        2e-8 * GRID_PER_YEAR, rel=1e-12
    )


def test_a_price_profile_bills_the_hours_that_draw_power():
    """Power drawn only in the dear half of the day is billed at the dear price."""
    run = make_results({"grid": {"net_import": [0.0] * 12 + [100.0] * 12}})
    profile = priced_opex(electricity=[1e-8] * 12 + [3e-8] * 12)
    result = gm.evaluate.opex(heating_plant(costed=False), profile, run, on_error="record")
    assert result.parts["components"]["electricity"].value == pytest.approx(
        3e-8 * 100.0 * SECONDS_PER_YEAR / 2
    )


def test_a_co2_price_adds_one_component_per_year():
    """1 kg/s of CO2 for a day, scaled to a year, at 0.5 per kg."""
    run = make_results({"air": {"co2_emission": [1.0] * HOURS}})
    result = gm.evaluate.opex(
        heating_plant(costed=False), priced_opex(co2=0.5), run, on_error="record"
    )
    assert result.parts["components"]["co2"].value == pytest.approx(0.5 * SECONDS_PER_YEAR)
    assert result.parts["components"]["co2"].unit == "currency/yr"
    without = gm.evaluate.opex(heating_plant(costed=False), priced_opex(), run, on_error="record")
    assert "co2" not in without.parts["components"]


def test_a_co2_price_profile_follows_the_steps():
    """CO2 emitted only in the dear half of the day is billed at the dear price."""
    run = make_results({"air": {"co2_emission": [0.0] * 12 + [1.0] * 12}})
    profile = priced_opex(co2=[0.1] * 12 + [0.4] * 12)
    result = gm.evaluate.opex(heating_plant(costed=False), profile, run, on_error="record")
    assert result.parts["components"]["co2"].value == pytest.approx(
        0.4 * 1.0 * SECONDS_PER_YEAR / 2
    )


PRICES = make_case(
    economics=costed_economics(energy={"electricity": Quantity(2e-8, "currency/J")}, **FINANCE)
)


HEAT = 1000.0 * SECONDS_PER_YEAR


OPEX = 10.0 + 2e-8 * 100.0 * SECONDS_PER_YEAR


"""Yearly cost of the heating plant under ``PRICES``: the fixed opex and the electricity."""


def test_the_annualised_cost_is_capex_over_the_annuity_plus_opex():
    """``capex / A + opex``, with every part in the result."""
    factor = (1 - 1.05**-20) / 0.05
    result = gm.evaluate.annualised_cost(heating_plant(), PRICES, day())
    assert result.value == pytest.approx(1000.0 / factor + OPEX, rel=1e-12)
    assert result.unit == "currency/yr"
    assert to_plain(result.parts["capex"]) == {"value": 1000.0, "unit": "currency"}
    assert result.parts["opex"].value == pytest.approx(OPEX, rel=1e-12)
    assert to_plain(result.parts["annuity_factor"]) == {
        "value": pytest.approx(factor),
        "unit": "yr",
    }
    assert to_plain(result.parts["discount_rate"]) == {"value": 0.05, "unit": "-"}
    assert to_plain(result.parts["analysis_period"]) == {"value": 20, "unit": "yr"}


def test_lcts_without_energy_has_no_value():
    """No heat and no cold: a reason, as ``lcoh`` gives; raised by default."""
    idle = day(heat=0.0)
    recorded = gm.evaluate.lcts(heating_plant(), PRICES, idle, on_error="record")
    assert recorded.value is None and "neither heat nor cold" in recorded.reason
    assert recorded.unit == "currency/J"
    with raises(gm.errors.ValidationError, "no_value", match="neither heat nor cold"):
        gm.evaluate.lcts(heating_plant(), PRICES, idle)


@pytest.mark.parametrize("name", ["lcts", "annualised_cost"])
def test_no_equipment_has_no_value(name):
    """A plant without equipment: a reason, or the error."""
    function = getattr(gm.evaluate, name)
    plant = heating_plant(costed=False)
    recorded = function(plant, PRICES, day(), on_error="record")
    assert recorded.value is None and "no module of the plant is equipment" in recorded.reason
    with raises(gm.errors.ValidationError, "no_value", match="no module of the plant is equipment"):
        function(plant, PRICES, day())


def test_lcoh_is_discounted_cost_over_discounted_heat():
    """(capex + opex A) / (heat A) with the annuity factor of 5 % over 20 years."""
    factor = (1 - 1.05**-20) / 0.05
    result = gm.evaluate.lcoh(heating_plant(), PRICES, day())
    assert result.value == pytest.approx((1000.0 + OPEX * factor) / (HEAT * factor), rel=1e-12)
    assert result.unit == "currency/J"
    assert to_plain(result.parts["capex"]) == {"value": 1000.0, "unit": "currency"}
    assert result.parts["opex"].value == pytest.approx(OPEX, rel=1e-12)


def test_lcoh_at_zero_rate_spreads_the_cost_over_the_years():
    """Without discounting, the cost over the lifetime divided by the heat over the lifetime."""
    flat = make_case(
        economics=costed_economics(
            energy={"electricity": Quantity(2e-8, "currency/J")},
            discount_rate=0.0,
            analysis_period=Quantity(10, "yr"),
        )
    )
    result = gm.evaluate.lcoh(heating_plant(), flat, day())
    assert result.value == pytest.approx((1000.0 + OPEX * 10) / (HEAT * 10), rel=1e-12)


def test_a_missing_rate_is_asked_for():
    """No rate anywhere raises with the missing-value code."""
    bare = make_case(
        economics=costed_economics(
            energy={"electricity": Quantity(2e-8, "currency/J")},
            analysis_period=Quantity(20, "yr"),
        )
    )
    with raises(
        gm.errors.ValidationError,
        "missing_assumption",
        match=r"economics\.discount_rate",
    ):
        gm.evaluate.lcoh(heating_plant(), bare, day())


def test_null_with_a_reason_when_the_equipment_or_the_heat_is_missing():
    """No equipment, no heat delivered, or heat and cold together give no value."""
    unpriced = gm.evaluate.lcoh(heating_plant(costed=False), PRICES, day(), on_error="record")
    assert unpriced.value is None and "no module of the plant is equipment" in unpriced.reason
    idle = gm.evaluate.lcoh(heating_plant(), PRICES, day(heat=0.0), on_error="record")
    assert idle.reason == "the run delivers no heat"
    plant = heating_plant()
    plant._add_module("cool", CoolingGrid())
    both = gm.evaluate.lcoh(plant, PRICES, day(cold=100.0), on_error="record")
    assert both.value is None and "split of its cost" in both.reason
    with raises(gm.errors.ValidationError, "no_value", match="split of its cost"):
        gm.evaluate.lcoh(plant, PRICES, day(cold=100.0))


def test_lcoh_keeps_its_numbers():
    """One expression, one order of operations: bit for bit the lifetime cost over the energy."""
    factor = cost.annuity(0.05, 20)
    result = gm.evaluate.lcoh(heating_plant(), PRICES, day())
    capex, yearly, energy = (result.parts[name].value for name in ("capex", "opex", "energy"))
    assert result.value == (capex + yearly * factor) / (energy * factor)


def test_a_share_splits_the_cost_of_a_plant_with_two_products():
    """``heat_cost_share`` charges that part of the cost to heat and the rest to cold."""
    plant = heating_plant()
    plant._add_module("cool", CoolingGrid())
    run = day(cold=100.0)
    values = make_case(
        economics=costed_economics(
            energy={"electricity": Quantity(2e-8, "currency/J")},
            **FINANCE,
            accounting={"allocation": {"heat_cost_share": 0.8}},
        )
    )
    heat = gm.evaluate.lcoh(plant, values, run)
    cold = gm.evaluate.lcoc(plant, values, run)
    assert heat.value * heat.parts["energy"].value / 0.8 == pytest.approx(
        cold.value * cold.parts["energy"].value / 0.2
    )


def test_lcoc_divides_by_the_cold_delivered():
    """The cooling plant (2000, fixed opex 60 a year, 300 W of cold) over 10 years at 0 %."""
    values = make_case(
        economics=costed_economics(
            energy={"electricity": Quantity(2e-8, "currency/J")},
            discount_rate=0.0,
            analysis_period=Quantity(10, "yr"),
        )
    )
    result = gm.evaluate.lcoc(cooling_plant(), values, day(heat=None, cold=300.0))
    opex = 60.0 + 2e-8 * 100.0 * SECONDS_PER_YEAR
    expected = (2000.0 + opex * 10) / (300.0 * SECONDS_PER_YEAR * 10)
    assert result.value == pytest.approx(expected, rel=1e-12)


def both_products():
    """Return a heat plant that also has a cooling consumer."""
    plant = heating_plant()
    plant._add_module("cool", CoolingGrid())
    return plant


def test_lcts_is_the_cost_of_heat_and_cold_together():
    """``lcoh`` with the whole cost on the heat, spread over both products; no share needed."""
    plant, run = both_products(), day(cold=500.0)
    shared = make_case(
        economics=costed_economics(
            energy={"electricity": Quantity(2e-8, "currency/J")},
            **FINANCE,
            accounting={"allocation": {"heat_cost_share": 1.0}},
        )
    )
    lcoh = gm.evaluate.lcoh(plant, shared, run)
    result = gm.evaluate.lcts(plant, PRICES, run)
    heat, cold = result.parts["heat"].value, result.parts["cold"].value
    assert heat == pytest.approx(HEAT) and cold == pytest.approx(HEAT / 2)
    assert result.value == pytest.approx(
        lcoh.value * lcoh.parts["energy"].value / (heat + cold), rel=1e-12
    )
    assert (
        result.unit == "currency/J"
        and result.parts["heat"].unit == result.parts["cold"].unit == "J/yr"
    )
    assert result.parts["annualised_cost"].unit == "currency/yr"


def test_lcts_of_one_product_is_its_levelised_cost():
    """A plant that delivers only heat has the same cost per joule both ways."""
    expected = gm.evaluate.lcoh(heating_plant(), PRICES, day()).value
    result = gm.evaluate.lcts(heating_plant(), PRICES, day())
    assert result.value == pytest.approx(expected, rel=1e-12)
    assert result.parts["cold"].value == 0


def test_a_result_converts_to_the_eur_units_of_a_report():
    """An LCTS is in ``EUR/MWh`` and a capex in ``EUR`` with ``.to``, whatever the label."""
    lcts = gm.evaluate.lcts(heating_plant(), PRICES, day())
    assert lcts.to("EUR/MWh").value == pytest.approx(lcts.value * 3.6e9)
    capex = gm.evaluate.capex(heating_plant(), PRICES)
    assert capex.to("EUR").value == capex.value == 1000.0
    assert capex.to("MEUR").value == pytest.approx(1e-3)


SELLING = make_case(
    economics=costed_economics(
        energy={"electricity": Quantity(2e-8, "currency/J")},
        **FINANCE,
        revenue={"heat": Quantity(5e-8, "currency/J")},
    )
)


NET = 5e-8 * HEAT - OPEX


"""Yearly net cash flow of the heating plant when its heat sells at 5e-8 EUR/J."""


def test_npv_is_the_discounted_net_cash_flow_less_the_investment():
    """-capex + net * A with A the 5 % annuity over 20 years."""
    factor = (1 - 1.05**-20) / 0.05
    result = gm.evaluate.npv(heating_plant(), SELLING, day())
    assert result.value == pytest.approx(NET * factor - 1000.0, rel=1e-12)
    assert result.unit == "currency"
    assert result.parts["net_cash_flow"].value == pytest.approx(NET, rel=1e-12)
    assert result.parts["net_cash_flow"].unit == "currency/yr"


def test_a_missing_price_is_asked_for():
    """Heat is delivered but unpriced."""
    unpriced = make_case(
        economics=costed_economics(energy={"electricity": Quantity(2e-8, "currency/J")}, **FINANCE)
    )
    with raises(
        gm.errors.ValidationError,
        "missing_assumption",
        match=r"economics\.revenue\.heat",
    ):
        gm.evaluate.npv(heating_plant(), unpriced, day())


def test_a_plant_without_equipment_has_no_npv():
    """Null with the reason of the missing cost."""
    plant = heating_plant(costed=False)
    assert gm.evaluate.npv(plant, SELLING, day(), on_error="record").value is None
    with raises(gm.errors.ValidationError, "no_value", match="no module of the plant is equipment"):
        gm.evaluate.npv(plant, SELLING, day())


def test_a_heat_price_profile_is_integrated_over_the_run():
    """Half a day at 3e-8 and half at 7e-8 earns what a constant 5e-8 earns."""
    profile = make_case(
        economics=costed_economics(
            energy={"electricity": Quantity(2e-8, "currency/J")},
            **FINANCE,
            revenue={"heat": Quantity([3e-8] * 12 + [7e-8] * 12, "currency/J")},
        )
    )
    result = gm.evaluate.npv(heating_plant(), profile, day())
    expected = gm.evaluate.npv(heating_plant(), SELLING, day())
    assert result.value == pytest.approx(expected.value, rel=1e-12)


def test_payback_is_the_investment_over_the_net_cash_flow():
    """Simple payback in years, undiscounted."""
    result = gm.evaluate.payback(heating_plant(), SELLING, day())
    assert result.value == pytest.approx(1000.0 / NET, rel=1e-12)
    assert result.unit == "yr"


def test_payback_never_comes_when_revenue_does_not_cover_the_cost():
    """A heat price below the running cost gives null with the reason."""
    cheap = make_case(
        economics=costed_economics(
            energy={"electricity": Quantity(2e-8, "currency/J")},
            **FINANCE,
            revenue={"heat": Quantity(1e-9, "currency/J")},
        )
    )
    result = gm.evaluate.payback(heating_plant(), cheap, day(), on_error="record")
    assert result.value is None
    assert result.reason == "the yearly revenue does not exceed the yearly cost"


def test_the_price_of_heat_is_asked_for_when_heat_is_delivered():
    """Heat is delivered but unpriced: the user is asked."""
    unpriced = make_case(
        economics=costed_economics(energy={"electricity": Quantity(2e-8, "currency/J")}, **FINANCE)
    )
    with raises(
        gm.errors.ValidationError,
        "missing_assumption",
        match=r"economics\.revenue\.heat",
    ):
        gm.evaluate.payback(heating_plant(), unpriced, day())


def test_a_plant_without_equipment_has_no_payback():
    """Null with the reason of the missing cost."""
    plant = heating_plant(costed=False)
    recorded = gm.evaluate.payback(plant, SELLING, day(), on_error="record")
    assert "no module of the plant is equipment" in recorded.reason
    with raises(gm.errors.ValidationError, "no_value", match="no module of the plant is equipment"):
        gm.evaluate.payback(plant, SELLING, day())
