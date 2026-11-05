"""A small storage plant: a hot water tank with a charge and a discharge circuit, over a day.

``buffer_plant`` is a plant of one ``ThermalStorage`` named ``tank`` whose three inlets and three
outlets are plant ports; ``buffer_plan`` is the run input (the columns are named after the plant
ports) and ``buffer_reference`` steps the exact solution of the tank by hand with plain NumPy.
"""

import numpy as np
import pandas as pd

import gemini as gm
from gemini.modules import Port
from gemini.modules.storage import ThermalStorage
from gemini.plants.plant import Plant
from gemini.streams.energy import Energy
from gemini.streams.fluid import BRINE, Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase
from tests.fixtures.sample_cases import RULES
from tests.fixtures import si

START = pd.Timestamp("2024-01-01", tz="UTC")
HOUR = 3600.0
PARAMS = dict(
    service="hot",
    volume=2.0,
    heat_loss_conductance=10.0,
    reference_temperature=313.15,
    charge_effectiveness=0.8,
    discharge_effectiveness=0.6,
)
CP = 4217.4
"""The heat capacity of ``BRINE`` at the pressures of the plan, as the fluid gives it."""
INITIAL = {"tank": {"temperature": 320.0}}
LOOP_START = 330.0


def buffer_plant():
    """Return the plant: a tank with the plant ports ``charge``, ``discharge`` and ``air``."""
    plant = gm.Plant("Buffer").set_params("", RULES)
    plant.add("ThermalStorage", "tank")
    for port in ("charge_in", "discharge_in", "air_in"):
        plant.connect(port, f"tank.{port}")
    for port in ("charge_out", "discharge_out", "loss_out"):
        plant.connect(f"tank.{port}", port)
    for module in plant.modules():
        module._set_own_fluid(BRINE)
    si.set_params(plant, "tank", PARAMS)
    return plant


def buffer_frame(rows=24, step="1h"):
    """Return the run input: charge and discharge flows and temperatures that change by the hour."""
    index = pd.date_range(START, periods=rows, freq=step)
    hours = np.arange(rows)
    frame = {
        "charge_in.m_dot": 1.0 + 0.5 * np.sin(hours / 3.0),
        "charge_in.T": 353.15 + 5.0 * np.cos(hours / 5.0),
        "charge_in.p": np.full(rows, 3e5),
        "discharge_in.m_dot": 0.5 + 0.25 * np.cos(hours / 4.0),
        "discharge_in.T": 313.15 + 2.0 * np.sin(hours / 6.0),
        "discharge_in.p": np.full(rows, 3e5),
        "air_in.m_dot": np.zeros(rows),
        "air_in.T": 288.15 + 3.0 * np.sin(hours / 12.0),
        "air_in.p": np.full(rows, 101325.0),
    }
    return pd.DataFrame(frame, index=index)


class GuessingTank(ThermalStorage):
    """A tank that guesses the temperature of a loop through it, where a state connection starts."""

    def _loop_start(self, inputs, port, entering):
        """Return the temperature a loop through the tank starts at."""
        return LOOP_START


class LaggedBuffer(Plant):
    """A tank whose charge circuit is fed with its own discharge outlet of the step before."""

    def __init__(self):
        """Declare the tank, the two plant inlets and the state connection."""
        super().__init__()

        # Modules
        self.tank = GuessingTank()

        # Inlets
        self.discharge_in = Port(
            Direction.IN, phase=Phase.LIQUID, fluid=Fluid.WATER, level=Level.HOT, flow=Flow.IMPOSED
        )
        self.air_in = Port(
            Direction.IN, phase=Phase.GAS, fluid=Fluid.AIR, level=Level.AMBIENT, flow=Flow.IMPOSED
        )

        # Outlets
        self.charge_out = Port(
            Direction.OUT, phase=Phase.LIQUID, fluid=Fluid.WATER, level=Level.HOT, flow=Flow.IMPOSED
        )
        self.loss_out = Port(Direction.OUT, energy=Energy.HEAT, flow=Flow.IMPOSED)

        # Connections
        self.connect("discharge_in", "tank.discharge_in")
        self.connect("air_in", "tank.air_in")
        self.connect("tank.charge_out", "charge_out")
        self.connect("tank.loss_out", "loss_out")
        self.connect("tank.discharge_out", "tank.charge_in", type="state")


def lagged_plant():
    """Return the lagged buffer with the parameters and the fluid of ``buffer_plant``."""
    plant = LaggedBuffer()
    for module in plant.modules():
        module._set_own_fluid(BRINE)
    return si.set_params(plant, "tank", PARAMS)


def lagged_frame(rows=24):
    """Return the run input of the lagged buffer: no charge circuit, it is the discharge outlet."""
    frame = buffer_frame(rows)
    return frame.drop(columns=[name for name in frame if name.startswith("charge_in")])


def buffer_reference(frame, lagged=False, start=INITIAL["tank"]["temperature"]):
    """Step the tank by hand: its temperature at the start of each step and its outlet temperatures.

    A row with a negative charge flow fails (reverse flow is not modelled): its values are NaN and
    the tank keeps its temperature. With ``lagged`` the charge circuit takes what the discharge
    circuit left at the step before (zero flow at ``LOOP_START`` at the first step).
    """
    params, hours = PARAMS, HOUR
    temperature = start
    previous = (0.0, LOOP_START)
    found = {"temperature": [], "charge_out": [], "discharge_out": []}
    for row in range(len(frame)):
        if lagged:
            charge_flow, charge_T = previous
        else:
            charge_flow, charge_T = (
                frame["charge_in.m_dot"].iloc[row],
                frame["charge_in.T"].iloc[row],
            )
        if charge_flow < 0 or frame["discharge_in.m_dot"].iloc[row] < 0:
            for values in found.values():
                values.append(np.nan)
            continue
        fluid = BRINE.properties(3e5, temperature)
        capacity = fluid.rho_l * fluid.cp_l * params["volume"]
        discharge_T = frame["discharge_in.T"].iloc[row]
        discharge_flow = frame["discharge_in.m_dot"].iloc[row]
        charge = params["charge_effectiveness"] * charge_flow * fluid.cp_l
        discharge = params["discharge_effectiveness"] * discharge_flow * fluid.cp_l
        loss = params["heat_loss_conductance"]
        total = charge + discharge + loss
        equilibrium = (
            charge * charge_T + discharge * discharge_T + loss * frame["air_in.T"].iloc[row]
        ) / total
        found["temperature"].append(temperature)
        found["charge_out"].append(
            charge_T - params["charge_effectiveness"] * (charge_T - temperature)
        )
        left = discharge_T - params["discharge_effectiveness"] * (discharge_T - temperature)
        found["discharge_out"].append(left)
        previous = (discharge_flow, left)
        temperature = equilibrium + (temperature - equilibrium) * np.exp(-total * hours / capacity)
    return {name: np.array(values) for name, values in found.items()} | {"final": temperature}


class FaultyTank(ThermalStorage):
    """A tank with a bug: it raises a plain exception when the charge flow is exactly 7 kg/s."""

    def forward(self, inputs, inlets, state):
        """Fail like a wrongly written module on one flow, else behave as the tank."""
        if inlets.charge_in.m_dot == 7.0:
            raise RuntimeError("bug in the tank")
        return super().forward(inputs, inlets, state)
