"""What may connect to what in a plant: the one rule, generic letters, checks and suggestions."""

import pytest

import gemini as gm
from gemini.errors import ValidationError
from gemini.modules import Direction, Port
from gemini.modules.exchangers import HeatExchanger
from gemini.modules.grids import GasGrid, HeatingGrid
from gemini.modules.heating import Boiler
from gemini.modules.piping import Pipe
from gemini.plants import Match, Suggestion
from gemini.streams import Energy, Fluid


@pytest.fixture
def plant():
    """Return a plant of an exchanger, a boiler, a pipe, a gas grid and heat users, unconnected."""
    built = gm.Plant("demo")
    built.hx, built.boiler, built.pipe = HeatExchanger(), Boiler(), Pipe()
    built.gas, built.users = GasGrid(), HeatingGrid()
    return built


def test_a_port_of_any_fluid_takes_any_stream():
    """``Fluid.ANY`` takes any fluid; power and stream fields do not mix."""
    port = Port(Direction.IN, fluid=Fluid.ANY)
    assert (port.phase, port.fluid, port.level, port.kind) == ("any", Fluid.ANY, "any", None)
    assert Port(Direction.IN, energy=Energy.ANY).drawn
    with pytest.raises(gm.errors.DefinitionError, match="power port has no phase"):
        Port(Direction.IN, energy=Energy.ANY, phase="gas")


def test_gas_cannot_enter_a_pipe_of_liquid_and_the_error_says_why(plant):
    """The phase differs; the error names both ends, their fields and the ports that fit."""
    with pytest.raises(ValidationError) as caught:
        plant.connect("gas.gas_out", "pipe.fluid_in")
    assert caught.value.code == "stream_mismatch"
    assert "phase gas to liquid" in str(caught.value)
    assert "boiler.fuel_in" in caught.value.suggestions


def test_power_cannot_enter_a_stream_port(plant):
    """Electricity is a power, the exchanger takes a stream."""
    plant.add("ElectricityGrid", "grid")
    with pytest.raises(ValidationError, match="power to stream"):
        plant.connect("grid.power_out", "hx.cold_in")


def test_a_generic_letter_carries_what_it_was_connected_to(plant):
    """Hot water into the cold side makes its outlet hot water too: gas is then refused there."""
    plant.connect(plant.boiler.fluid_out, plant.hx.cold_in)
    assert [item.path for item in plant.suggest(plant.hx.cold_out)][:1] == ["boiler.fluid_in"]
    assert plant.check() == [] or all(item.code != "generic_conflict" for item in plant.check())


def test_a_generic_conflict_is_an_issue_of_the_plant(plant):
    """One letter asked to carry chilled and hot water through the module is reported."""
    plant.add("CoolingGrid", "cold")
    plant.connect("users.return_out", "hx.cold_in")
    plant.connect("hx.cold_out", "cold.supply_in")
    codes = {item.code for item in plant.check()}
    assert "generic_conflict" in codes


def test_suggest_puts_exact_matches_first_and_the_loop_partner_on_top(plant):
    """After the supply leg, the return of the users goes back to the same side of the exchanger."""
    plant.connect(plant.hx.cold_out, plant.users.supply_in)
    found = plant.suggest(plant.users.return_out)
    assert isinstance(found[0], Suggestion) and found[0].path == "hx.cold_in"
    assert found[0].closes_loop and found[0].match is Match.EXACT
    assert found[0].exact == ["phase", "fluid", "level"] and found[0].loose == []
    assert found[0].to_dict()["port"] == "hx.cold_in"
    loose = [item for item in found if item.match is Match.LOOSE]
    assert loose and all(item.loose for item in loose)
    assert all(
        item.match is Match.EXACT for item in plant.suggest(plant.users.return_out, loose=False)
    )
    assert len(plant.suggest("users.return_out", limit=1)) == 1


def test_connect_takes_a_suggestion(plant):
    """The suggestion itself names the port to connect."""
    plant.connect(plant.hx.cold_out, plant.users.supply_in)
    plant.connect(plant.users.return_out, plant.suggest(plant.users.return_out)[0])
    assert {"source": "users.return_out", "target": "hx.cold_in"} in plant._connections


def test_suggest_of_a_module_or_of_the_plant_lists_each_free_port(plant):
    """A module gives each of its free ports, no argument every required port left open."""
    by_port = plant.suggest(plant.boiler)
    assert {port.name for port in by_port} == {
        "fluid_in",
        "fuel_in",
        "fluid_out",
        "flue_out",
        "loss_out",
    }
    assert [item.path for item in by_port[plant.boiler.fuel_in]] == ["gas.gas_out"]
    everything = plant.suggest()
    assert plant.boiler.fuel_in in everything and plant.users.supply_in in everything
    plant.connect("gas.gas_out", "boiler.fuel_in")
    assert plant.boiler.fuel_in not in plant.suggest()


def test_suggest_with_free_false_also_lists_connected_ports(plant):
    """A connected inlet is listed again when ``free`` is off."""
    plant.connect("gas.gas_out", "boiler.fuel_in")
    assert plant.suggest("gas.gas_out") == []
    assert [item.path for item in plant.suggest("gas.gas_out", free=False)] == ["boiler.fuel_in"]


def test_every_shipped_plant_has_no_port_issue():
    """Every plant class at every size connects as its fields allow."""
    from gemini.plants._utils import connections

    for name in gm.plants.names():
        cls = gm.plants.get(name)
        sizes = [{}] + (
            [{"doublets": n} for n in (2, 3)] if hasattr(cls, "maximum_doublets") else []
        )
        for size in sizes:
            assert (
                connections.issues(type(cls)(**size) if not isinstance(cls, type) else cls(**size))
                == []
            )


def test_a_run_outside_the_range_of_a_port_is_a_warning(plant):
    """``check(results=...)`` warns for a port whose temperature left its range, never refuses."""
    from gemini.plants._utils import connections

    class Run:
        def to_frame(self):
            import pandas as pd

            return pd.DataFrame({"boiler.fluid_out.temperature": [350.0, 400.0, 380.0]})

    plant.boiler.fluid_out.temperature = (300.0, 390.0)
    found = connections.out_of_range(plant, Run())
    assert [(item.path, item.kind, item.code) for item in found] == [
        ("boiler.fluid_out", "warning", "out_of_range")
    ]
    assert found[0].is_warning and "on 1 steps" in found[0].message
