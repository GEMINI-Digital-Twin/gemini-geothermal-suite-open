"""Split the body of a scan into what depends on the states and what does not.

A step of a stateful plant is mostly physics that never reads a state: the wells, the pumps, the
exchangers of the other loops. Those nodes have the same value whatever the states are, so they
are evaluated once, on all the rows at a time like a graph without a scan, and only the nodes that
depend on a carry run again at each row. A node depends on a carry when an operand does, when a
check that guards it does (its errors then change with the row), or, for a loop, when a node of its
body reads one from outside. ``split_of`` gives the two lists of nodes in creation order, the
nodes of the first part that the second reads (``frontier``: the row loop takes one row of each),
the checks the second part propagates and, for a node of the second part guarded by checks of the
first, those checks (``guards``: their errors are known before the loop and seed the node). The
Python backend does not split: it runs one row at a time, so every node is on the row side.
"""

from dataclasses import dataclass

from gemini.compiler.ir import Node


@dataclass(frozen=True, eq=False)
class Split:
    """The nodes of a scan body that run once, those that run at each row, and what links them."""

    once: tuple
    stepwise: tuple
    frontier: tuple
    checks: tuple
    dependent: frozenset
    guards: dict


def split_of(graph, body, partition):
    """Return the ``Split`` of ``body``; with ``partition`` false every node runs at each row."""
    if partition not in body.splits:
        body.splits[partition] = _split(graph, body, partition)
    return body.splits[partition]


def _split(graph, body, partition):
    if not partition:
        dependent = frozenset((*body.nodes, *body.carries))
        return Split((), tuple(body.nodes), (), tuple(body.checks), dependent, {})
    values, guards = _references(graph, body)
    dependent = set(body.carries)
    changed = True
    while changed:
        changed = False
        for node in body.nodes:
            if node not in dependent and any(
                item in dependent for item in (*values[node], *guards[node])
            ):
                dependent.add(node)
                changed = True
    once = tuple(node for node in body.nodes if node not in dependent)
    stepwise = tuple(node for node in body.nodes if node in dependent)
    needed = {item for node in stepwise for item in values[node] if item not in dependent}
    needed.update(item for item in body.images if _is_once(item, dependent, body))
    frontier = tuple(node for node in once if node in needed)
    checks = tuple(check for check in body.checks if check in dependent)
    seeded = {
        node: tuple(check for check in guards[node] if check not in dependent)
        for node in stepwise
        if any(check not in dependent for check in guards[node])
    }
    return Split(once, stepwise, frontier, checks, frozenset(dependent), seeded)


def _is_once(item, dependent, body):
    return isinstance(item, Node) and item.body is body and item not in dependent


def _references(graph, body):
    """Return what each node of ``body`` reads: its operands and a loop's free nodes, its guards."""
    inner = _free_nodes(graph, body)
    values, guards = {}, {}
    for node in body.nodes:
        items = [operand for operand in node.operands if isinstance(operand, Node)]
        if node.op == "fixed_point":
            items.extend(inner[node.attributes["body"]])
        values[node], guards[node] = items, list(node.guards)
    return values, guards


def _free_nodes(graph, body):
    """Return, for each loop body below ``body``, the nodes outside it that its nodes read."""
    below = [other for other in graph.bodies if other.parent is body]
    free = {}
    for loop in below:
        members = [node for node in graph.nodes if _within(node.body, loop)]
        owned = set(members)
        free[loop] = {
            operand
            for node in members
            for operand in (*node.operands, *node.guards)
            if isinstance(operand, Node) and operand not in owned
        }
        free[loop].update(
            image for image in loop.images if isinstance(image, Node) and image not in owned
        )
    return free


def _within(candidate, body):
    """Return whether ``candidate`` is ``body`` or a body below it."""
    while candidate is not None:
        if candidate is body:
            return True
        candidate = candidate.parent
    return False
