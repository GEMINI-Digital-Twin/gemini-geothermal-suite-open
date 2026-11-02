"""Lumped ice store: coil duty, piecewise exact phase segments, balances and limits."""

import math

import numpy as np
import pytest

import gemini as gm
from gemini import ops
from gemini.evaluate import call_energy_balance, call_mass_balance
from gemini.modules import Module
from gemini.modules.declarations import Inlet, Outlet
from gemini.modules.storage import IceStorage
from gemini.streams.flows import Stream
from gemini.streams.fluid import GLYCOL_30
from gemini.streams.ports import Ports
from tests.fixtures.designs import with_values
from tests.fixtures.equivalence import assert_close, assert_function_matches
from tests.fixtures.errors import raises
from tests.fixtures.reading import reading

MASS = 1000.0
UA = 2000.0
LATENT = MASS * 333550
"""Latent capacity [J] of the 1 t test store."""

RATE = 2.0 * 3841
"""Glycol capacity rate [W/K] of 2 kg/s of 30 % propylene glycol."""

EFFECTIVENESS = 1 - math.exp(-UA / RATE)
CONDUCTANCE = EFFECTIVENESS * RATE
FREEZING = 273.15
COLD = Stream(
    m_dot=gm.units.Quantity(2.0, "kg/s"),
    T=gm.units.Quantity(268.15, "K"),
    p=gm.units.Quantity(3e5, "Pa"),
    fluid=GLYCOL_30,
)
WARM = COLD._with_si(T=285.15)


EMPTY = {"ice_fraction": 0.0, "temperature": FREEZING}
"""An empty store at 0 degC: a state has no default, the call states it."""


def _store():
    """Return a 1 t store with a 2 kW/K coil."""
    return with_values(IceStorage()).set_params(
        "",
        {
            "water_mass": gm.units.Quantity(MASS, "kg"),
            "thermal_conductance": gm.units.Quantity(UA, "W/K"),
        },
    )


def test_a_call_from_an_empty_store_charges_it():
    """An empty store is all water at 0 degC; cold glycol is warmed by e (T_f - T_in)."""
    store = _store()
    result = store(fluid_in=COLD, state=EMPTY)
    out = reading(result)
    assert out.fluid_out_T == pytest.approx(268.15 + EFFECTIVENESS * 5)
    assert out.signed_duty == pytest.approx(-CONDUCTANCE * 5)
    assert out.stored_cold == 0 and out.is_empty and not out.is_full
    assert result.outlets.fluid_out.m_dot == COLD.m_dot and result.outlets.fluid_out.p == COLD.p
    assert out.heat_accumulation == pytest.approx(out.signed_duty)
    assert call_energy_balance(store, result)["relative_residual"] < 1e-12
    assert call_mass_balance(store, result)["residual"] == 0


def test_latent_steps_freeze_at_constant_duty():
    """Partly frozen, the store stays at 0 degC and x grows by -duty dt / (M L)."""
    store = _store()
    state, result = store.step(
        {"ice_fraction": 0.5, "temperature": FREEZING}, 3600, {"fluid_in": COLD}
    )
    assert result.outputs.stored_cold == pytest.approx(0.5 * LATENT)
    first = 0.5 + CONDUCTANCE * 5 * 3600 / LATENT
    assert state == {"ice_fraction": pytest.approx(first, rel=1e-14), "temperature": FREEZING}
    state, result = store.step(state, 3600, {"fluid_in": COLD})
    assert reading(result).signed_duty == pytest.approx(-CONDUCTANCE * 5)
    assert state["ice_fraction"] == pytest.approx(first + CONDUCTANCE * 5 * 3600 / LATENT)


def test_a_full_store_subcools_and_an_empty_store_warms():
    """A step that fills (empties) the store continues as sensible ice (water)."""
    store = _store()
    state, _ = store.step({"ice_fraction": 0.99, "temperature": FREEZING}, 3600, {"fluid_in": COLD})
    filled = 0.01 * LATENT / (CONDUCTANCE * 5)
    tau = MASS * 2096.8 / CONDUCTANCE
    assert state["ice_fraction"] == 1
    assert state["temperature"] == pytest.approx(268.15 + 5 * math.exp(-(3600 - filled) / tau))
    _, result = store.step(state, 60, {"fluid_in": COLD})
    assert result.outputs.is_full and result.outputs.stored_cold == pytest.approx(LATENT)

    state, _ = store.step({"ice_fraction": 0.01, "temperature": FREEZING}, 3600, {"fluid_in": WARM})
    emptied = 0.01 * LATENT / (CONDUCTANCE * 12)
    tau = MASS * 4219.9 / CONDUCTANCE
    assert state["ice_fraction"] == 0
    assert state["temperature"] == pytest.approx(285.15 - 12 * math.exp(-(3600 - emptied) / tau))


def test_sensible_stores_reach_freezing_then_change_phase():
    """Warm water cools to 0 degC before freezing; subcooled ice warms to 0 degC before melting."""
    store = _store()
    state, _ = store.step({"ice_fraction": 0, "temperature": 278.15}, 7200, {"fluid_in": COLD})
    reach = MASS * 4219.9 / CONDUCTANCE * math.log(10 / 5)
    assert state["temperature"] == FREEZING
    assert state["ice_fraction"] == pytest.approx(CONDUCTANCE * 5 * (7200 - reach) / LATENT)
    state, _ = store.step({"ice_fraction": 1, "temperature": 263.15}, 7200, {"fluid_in": WARM})
    reach = MASS * 2096.8 / CONDUCTANCE * math.log(22 / 12)
    assert state["temperature"] == FREEZING
    assert state["ice_fraction"] == pytest.approx(1 - CONDUCTANCE * 12 * (7200 - reach) / LATENT)


def test_stopped_glycol_leaves_the_store_unchanged():
    """Zero flow transfers no heat and keeps the state."""
    store = _store()
    start = {"ice_fraction": 0.3, "temperature": FREEZING}
    state, result = store.step(start, 3600, {"fluid_in": COLD._with_si(m_dot=0)})
    assert state == start and reading(result).signed_duty == 0
    assert result.outlets.fluid_out.T == COLD.T


def test_invalid_states_and_flows_raise():
    """A temperature that contradicts the phase, and reverse flow, are rejected."""
    store = _store()
    with raises(
        gm.errors.ValidationError, "invalid_design", match="ice_storage: temperature = 270"
    ):
        store.step({"ice_fraction": 0.5, "temperature": 270.0}, 60, {"fluid_in": COLD})
    with raises(gm.errors.ValidationError, "invalid_design", match="with ice_fraction = 0"):
        store.step({"ice_fraction": 0, "temperature": 270.0}, 60, {"fluid_in": COLD})
    with pytest.raises(gm.errors.PhysicsError, match="fluid_in.m_dot = -1"):
        store(fluid_in=COLD._with_si(m_dot=-1), state=EMPTY)
    with raises(gm.errors.ValidationError, "missing_value"):
        store(fluid_in=COLD)
    with pytest.raises(gm.errors.ValidationError):
        store.step({"ice_fraction": 1.5, "temperature": FREEZING}, 60, {"fluid_in": COLD})


class StoreLine(Module):
    """Two ice stores charged in series."""

    def __init__(self):
        """Declare the test composite."""
        super().__init__()

        # Modules
        self.first = _store()
        self.second = _store()

        # Inlets
        self.fluid_in = Inlet(Stream)

        # Outlets
        self.fluid_out = Outlet(Stream)

    def forward(self, inputs, inlets, state):
        """Pass the glycol through both stores."""

        # Modules
        first = self.first(fluid_in=inlets.fluid_in, state=state["first"])
        second = self.second(fluid_in=first.outlets.fluid_out, state=state["second"])

        # Outlets
        outlet = second.outlets.fluid_out

        outputs = dict()
        outlets = dict(fluid_out=outlet)
        return outputs, outlets


def _stream_gain(result):
    """Return the heat [W] the glycol takes from the stores of ``result``, negative when cooled."""
    return sum(reading(leaf).signed_duty for leaf in result.leaves().values())


def test_composite_step_freezes_both_stores():
    """A composite steps both stores; the upstream store sees colder glycol and freezes faster."""
    line = StoreLine()
    state, _ = line.step({"first": EMPTY, "second": EMPTY}, 1800, {"fluid_in": COLD})
    state, result = line.step(state, 1800, {"fluid_in": COLD})
    assert state["first"]["ice_fraction"] > state["second"]["ice_fraction"] > 0
    audit = call_energy_balance(line, result)
    assert audit["relative_residual"] < 1e-12
    assert audit["heat_accumulation"] == pytest.approx(_stream_gain(result), rel=1e-12)
    assert call_mass_balance(line, result)["residual"] == 0


STORE_STATES = [
    (0.0, 280.15, COLD),
    (0.0, 273.15, COLD),
    (0.4, 273.15, WARM),
    (0.4, 273.15, COLD),
    (1.0, 265.15, WARM),
    (1.0, 265.15, COLD),
    (0.0, 273.15, WARM),
    (0.0, 278.15, COLD._with_si(m_dot=0)),
]


def _forward(store, fraction, temperature, glycol):
    """Run the pure forward of ``store`` on a glycol stream and a store state."""
    state = {"ice_fraction": fraction, "temperature": temperature}
    return store.forward({}, Ports({"fluid_in": glycol._numpy()}), state)


def test_ice_storage_forward_matches_per_row():
    """Outputs and outlet on stacked states equal one forward per row."""
    store = _store()
    rows = [(x, t, g) for x, t, g in STORE_STATES if g.m_dot > 0]
    expected = [_forward(store, x, t, g) for x, t, g in rows]
    stacked = Stream._si(
        **{f: np.array([getattr(g, f) for _, _, g in rows]) for f in ("m_dot", "T", "p")},
        fluid=GLYCOL_30,
    )
    outputs, outlets = _forward(
        store, np.array([x for x, _, _ in rows]), np.array([t for _, t, _ in rows]), stacked
    )
    for name in outputs:
        assert_close(outputs[name], [e[0][name] for e in expected], name)
    assert_close(outlets["fluid_out"].T, [e[1]["fluid_out"].T for e in expected], "fluid_out")


@pytest.mark.parametrize("dt", [600, 20000, 400000])
def test_ice_storage_update_matches_per_row(dt):
    """The piecewise phase integration on stacked states equals one step per row, stopped too."""
    store = _store()

    @ops.physics
    def advance(fraction, temperature, m_dot, glycol_T, pressure):
        glycol = Stream._si(m_dot=m_dot, T=glycol_T, p=pressure, fluid=GLYCOL_30)
        state = {"ice_fraction": fraction, "temperature": temperature}
        states = store.update({}, Ports({"fluid_in": glycol._numpy()}), {}, state, dt)
        return states["ice_fraction"], states["temperature"]

    rows = [(x, t, g.m_dot, g.T, g.p) for x, t, g in STORE_STATES]
    assert_function_matches(advance, rows)
