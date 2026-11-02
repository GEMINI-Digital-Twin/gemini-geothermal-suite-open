"""The transition from the old module contract: the set of classes not yet converted."""

import inspect

import gemini as gm
from gemini.modules import unconverted
from gemini.modules.control import PIDController
from gemini.modules.module import Module
from gemini.modules.pumps import ESP


def registered():
    """Return the registered module classes by name."""
    return {gm.modules.get(name).__name__: gm.modules.get(name) for name in gm.modules.names()}


def test_a_class_is_unconverted_exactly_when_its_forward_has_the_old_signature():
    """The signature decides, and the set names those classes and no others."""
    old = {name for name, cls in registered().items() if cls._unconverted}
    assert old == unconverted.OLD_STYLE_MUST_BECOME_EMPTY
    for name, cls in registered().items():
        signature = tuple(inspect.signature(cls.forward).parameters)
        assert cls._unconverted == (signature == ("self", "inlets")), name


def test_a_converted_class_is_not_in_the_set():
    """ESP and PIDController are the worked examples: converted, so never in the set."""
    assert not ESP._unconverted and not PIDController._unconverted
    assert not {"ESP", "PIDController"} & unconverted.OLD_STYLE_MUST_BECOME_EMPTY
    assert not Module._unconverted and not gm.plants.Plant._unconverted


def test_every_plant_class_is_converted():
    """A plant never writes its forward, so no plant class is unconverted."""
    assert not [name for name in gm.plants.names() if registered()[name]._unconverted]


def test_an_unconverted_child_reads_its_state_from_an_unconverted_composite():
    """A composite whose forward cannot pass a state hands the child its entry of the tree."""
    from gemini.modules.callrecord import CallRecord

    class Parent(Module):
        """A composite with the old forward."""

        def forward(self, inlets):
            """Never run."""

    parent, child = Parent(), ESP()
    parent.child = child
    record = CallRecord(
        module=parent, inputs={}, outputs={}, parent=None, state={"child": {"count": 1.0}}
    )
    assert unconverted.inherited_state(child, record) == {"count": 1.0}
    assert unconverted.inherited_state(child, None) is None
