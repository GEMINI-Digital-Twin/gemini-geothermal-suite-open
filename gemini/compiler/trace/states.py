"""The states of a stepped trace: which values a scan carries, and how one step advances them.

A stateful module tree is traced as the body of a scan. Its state is the nested dict of the states
of its stateful modules by path (``modules/states.py``), plus, under the key ``previous`` of a plant,
the streams its state connections read from the step before (``DELAYED``). ``state_leaves`` lists
the leaves of that tree in a fixed order: each becomes a carry of the scan. ``state_tree`` builds the
tree of a step from the carries, ``advance`` gives the next state of a call recorded by the
trace (the traced counterpart of ``Stateful._advance``: the same walk, with ``update`` run on traced
values and its result not validated, as a traced output is not), and ``leaf_unit`` gives the unit
of a leaf.
"""

from gemini._utils.mappings import get_nested, set_nested
from gemini.errors import DefinitionError, ValidationError
from gemini.modules.callrecord import CallRecord, current_call
from gemini.streams.flows import STREAM_FIELDS

DELAYED = "delayed"
"""The kind of a plan source that reads the stream a connection held at the step before."""

PREVIOUS = "previous"
"""The key, in the state of a plant, of the streams its state connections carry."""


def state_leaves(module):
    """Return the leaves of the state tree of ``module`` as tuples of keys, in a fixed order."""
    leaves = []
    for path, member in module.named_modules():
        keys = tuple(path.split(".")) if path else ()
        leaves.extend((*keys, name) for name in member._states)
        for key in delayed_keys(member):
            leaves.extend((*keys, PREVIOUS, key, field) for field in STREAM_FIELDS)
    return leaves


def delayed_keys(module):
    """Return the keys, ``<source path>.<port>``, of the streams a plant reads from the last step."""
    plan = getattr(module, "_plan", None)
    if plan is None:
        return []
    keys = {}
    for arguments in plan.arguments.values():
        for source in arguments.values():
            if source[0] == DELAYED:
                keys[source[1]] = None
    return list(keys)


def leaf_unit(module, leaf):
    """Return the unit of a leaf of the state tree: that of the declared state, else SI."""
    if PREVIOUS in leaf:
        return dict(zip(STREAM_FIELDS, ("kg/s", "K", "Pa")))[leaf[-1]]
    owner = module.get_submodule(".".join(leaf[:-1]))
    return owner._states[leaf[-1]].unit


def state_tree(leaves, values):
    """Return the nested dict that holds ``values`` at the paths ``leaves``."""
    tree = {}
    for leaf, value in zip(leaves, values):
        set_nested(tree, leaf, value)
    return tree


def advance(trace, module, result, dt):
    """Return the next state tree of the call ``result`` of ``module``, on traced values.

    A module with states advances them with ``update``. A composite's state is the nested dict of
    what each stateful child it called advanced to; a plant adds the streams its state connections
    carry. A stateful child called twice in one step is refused, as ``Stateful._advance`` does.
    """
    if module._states:
        return _leaf(trace, module, result, dt)
    advanced, seen = {}, set()
    for path, child_result in result.call_records:
        child = module.get_submodule(path)
        if not child._has_state():
            continue
        if path in seen:
            raise ValidationError(
                f"{module.path}.{path}: stateful module called more than once in one step",
                code="invalid_design",
            )
        seen.add(path)
        set_nested(advanced, tuple(path.split(".")), advance(trace, child, child_result, dt))
    keys = delayed_keys(module)
    if keys:
        advanced[PREVIOUS] = {key: _previous(module, result, key) for key in keys}
    return advanced


def _previous(module, result, key):
    """Return the stream the source outlet ``key`` of a plant holds in the call ``result``."""
    path, _, port = key.rpartition(".")
    outlets = dict(result.call_records)[path].outlets[port]
    return {field: getattr(outlets, field) for field in STREAM_FIELDS}


def _leaf(trace, module, result, dt):
    """Return what ``update`` of the stateful ``module`` gives for the values of its call."""
    call = CallRecord(
        module=module,
        inputs=dict(result.inputs),
        outputs=dict(result.outputs),
        recording=False,
        parent=None,
        state=result.state,
        parameters=trace.parameters(module),
        trace=trace,
    )
    token = current_call.set(call)
    try:
        values = module.update(call.inputs, result.inlets, result.outlets, call.state, dt)
    finally:
        current_call.reset(token)
    return _checked(module, values)


def _checked(module, values):
    """Return the states ``update`` returned, or raise naming the module and the key."""
    if not isinstance(values, dict):
        raise DefinitionError(f"{module.path}: update must return a dict of states")
    missing = [name for name in module._states if name not in values]
    extra = [name for name in values if name not in module._states]
    if missing or extra:
        key = (missing or extra)[0]
        raise DefinitionError(
            f"{module.path}: update returned the states {sorted(values)}; "
            f"{'missing' if missing else 'extra'} key {key!r}; expected {sorted(module._states)}"
        )
    return {name: values[name] for name in module._states}


def next_values(leaves, current, advanced):
    """Return the next value of every leaf: what ``advanced`` holds, else the one it had."""
    return [get_nested(advanced, leaf, default=value) for leaf, value in zip(leaves, current)]
