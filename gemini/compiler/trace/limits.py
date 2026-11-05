"""Declared bounds as graph checks: a traced call is not validated, so the graph checks them.

``check_declared_limits(module, call)`` adds one ``ops.check`` per bound (``Declaration.limits``)
of every control, boundary and output a traced call holds, each item of a list separately, with
``ValidationError`` as ``Declaration.validate`` raises on a plain call; ``check_state_limits`` does
the same for the next value of a state, which a plain step validates. A declared
``X | None`` lets NaN pass, which is how ``None`` is stored on arrays. Each check keeps its
``Declaration`` and the whole value among its message values (``declaration`` and ``whole``), so
an evaluation words the error of a failing row with ``declaration.validate``. ``certain`` marks the
checks of a trace on every output of its graph (in a scan, of its step), so a violated bound fails
the row even when the bad value does not reach the output through the arithmetic.
"""

import operator

from gemini import ops
from gemini._utils.mappings import get_nested
from gemini.errors import ValidationError

_COMPARISONS = {
    "ge": (operator.ge, ">="),
    "gt": (operator.gt, ">"),
    "le": (operator.le, "<="),
    "lt": (operator.lt, "<"),
}


def check_declared_limits(module, call):
    """Check the bounds of the controls, boundaries and outputs recorded in ``call``."""
    declarations = module._controls | module._boundaries | module._outputs
    for name, value in (call.inputs | call.kept_outputs()).items():
        declaration = declarations[name]
        if declaration.limits():
            _check_value(declaration, value)


def check_state_limits(module, advanced):
    """Check the bounds of the next value of every state of the tree of ``module``.

    ``advanced`` is the state tree one step gives; a state it does not hold is not checked.
    """
    for path, member in module.named_modules():
        keys = tuple(path.split(".")) if path else ()
        for name, declaration in member._states.items():
            if declaration.limits():
                _check_value(declaration, get_nested(advanced, (*keys, name)))


def _check_value(declaration, value):
    items = value if isinstance(value, (list, tuple)) else [value]
    for item in items:
        if item is None:
            continue
        for limit, bound in declaration.limits().items():
            compare, relation = _COMPARISONS[limit]
            held = compare(item, bound)
            if declaration.accepts_none():
                held = ops.logical_or(ops.isnan(item), held)
            ops.check(
                held,
                ValidationError,
                "{path}: invalid {section} value {value}; expected {relation} {bound}",
                path=declaration.path,
                section=declaration.section,
                value=item,
                relation=relation,
                bound=bound,
                declaration=declaration,
                whole=value,
            )


def certain(graph, checks, nodes=None):
    """Guard ``nodes`` with the ``checks`` of the level being traced, so each reaches them.

    ``nodes`` are the graph outputs unless given; in the body of a scan they are the values that
    fail a step. Only the checks recorded at the level of the graph being traced count: those of
    the outer graph, or of the running body.
    """
    alive = set(graph.checks)
    kept = [check for check in checks if check in alive and check.body is graph.body]
    nodes = graph.outputs.values() if nodes is None else nodes
    owned = {node for node in nodes if hasattr(node, "guards") and node.body is graph.body}
    for node in owned:
        node.guards.extend(check for check in kept if check not in node.guards)
