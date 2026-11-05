"""What the ports of a plant carry, what may connect to what, and what is left to connect.

Each port states its fields (``gemini.modules.declarations.Port``); a ``generic`` port of a module
takes its fields from what it is connected to, and every port of that module with the same letter
takes the same ones. ``inferred`` follows the connections of a plant to give each generic letter
its fields, and the conflicts where two connections ask for different ones. ``suggestions`` lists
the free ports a port may connect to, best first: the most fields equal (not through ``ANY`` or a
generic letter), then the port that closes a loop with a module already connected the other way.
No score or probability is given.
"""

from dataclasses import dataclass
from enum import StrEnum

from gemini.errors import ValidationError
from gemini.errors.base import Issue
from gemini.modules.declarations import Port, mismatch
from gemini.modules.module import Module
from gemini.plants._utils.plan import is_group, members, port_ends, split_end
from gemini.streams.kinds import Direction

STREAM_FIELDS = ("phase", "fluid", "level")
"""The fields that a connection of two stream ports compares."""
POWER_FIELDS = ("energy",)
"""The field that a connection of two power ports compares."""


def compared(declaration):
    """Return the fields a connection of ``declaration`` compares."""
    return STREAM_FIELDS if declaration.carries_stream else POWER_FIELDS


ANY = "any"


class Match(StrEnum):
    """How a suggested port matches: every field equal (``EXACT``) or some through ``ANY``."""

    EXACT = "exact"
    LOOSE = "loose"


@dataclass(frozen=True, eq=False)
class Suggestion:
    """A port that a port may connect to, and how it matches; no score or probability.

    ``port`` is the bound ``Port``: ``plant.connect(end, suggestion)`` takes the suggestion
    itself. ``exact`` lists the fields equal on both sides, ``loose`` those matched through
    ``ANY`` or a generic letter; ``match`` is ``EXACT`` when none is loose. ``closes_loop`` is
    true when the two modules are already connected the other way.
    """

    port: Port
    match: Match
    exact: list
    loose: list
    closes_loop: bool

    @property
    def path(self):
        """Return the ``"path.port"`` of the suggested port."""
        return self.port.path

    def to_dict(self):
        """Return the suggestion as plain JSON, the port as its ``"path.port"``."""
        return {
            "port": self.path,
            "match": self.match.value,
            "exact": list(self.exact),
            "loose": list(self.loose),
            "closes_loop": self.closes_loop,
        }


def leaf_ports(plant):
    """Return ``{(path, port): Port}`` of every port of the modules below ``plant``."""
    return {
        (path, name): declaration
        for path, module in members(plant)
        for side in ("inlets", "outlets")
        for name, declaration in getattr(module, side)().items()
    }


class _Letters:
    """The fields each generic letter of each module takes, found from the connections."""

    def __init__(self):
        self.parent, self.fields, self.conflicts = {}, {}, []

    def root(self, node):
        while self.parent.get(node, node) != node:
            node = self.parent[node]
        return node

    def merge(self, first, second, where):
        first, second = self.root(first), self.root(second)
        if first == second:
            return
        self.parent[second] = first
        for name, value in self.fields.pop(second, {}).items():
            self.give(first, name, value, where)

    def give(self, node, name, value, where):
        node = self.root(node)
        held = self.fields.setdefault(node, {})
        if value is None or value == ANY:
            return
        current = held.get(name)
        if current is None or current == ANY:
            held[name] = value
        elif current != value:
            self.conflicts.append((where, name, current, value))


def _node(path, declaration):
    """Return the node of a generic port, ``(path, letter)``, or ``None`` for a concrete one."""
    return None if declaration.generic is None else (path, declaration.generic)


def inferred(plant):
    """Return ``(fields, conflicts)``: the fields of each generic port, and where they disagree.

    ``fields`` is ``{(path, port): {field: value}}`` for every generic port that a connection gives
    a value; a ``conflict`` is ``(connection, field, first, second)``.
    """
    ports = leaf_ports(plant)
    letters = _Letters()
    for item in plant._connections:
        ends = [split_end(item["source"]), split_end(item["target"])]
        if any(end not in ports for end in ends):
            continue
        nodes = [_node(path, ports[(path, port)]) for path, port in ends]
        where = f"{item['source']} -> {item['target']}"
        if nodes[0] and nodes[1]:
            letters.merge(nodes[0], nodes[1], where)
        for node, other in ((nodes[0], ends[1]), (nodes[1], ends[0])):
            declaration = ports[other]
            if node is None or declaration.generic is not None:
                continue
            for name in compared(declaration):
                letters.give(node, name, declaration.value_of(name), where)
    found = {}
    for (path, port), declaration in ports.items():
        node = _node(path, declaration)
        if node is not None:
            found[(path, port)] = dict(letters.fields.get(letters.root(node), {}))
    return found, letters.conflicts


def effective(declaration, fields):
    """Return ``{field: value}`` the port carries: its own, a generic one's inferred over ANY."""
    own = {name: declaration.value_of(name) for name in compared(declaration)}
    return own | {name: value for name, value in fields.items() if own.get(name) == ANY}


def issues(plant):
    """Return the issues of the ports of ``plant``: generic conflicts and bad connections."""
    found, conflicts = inferred(plant)
    ports = leaf_ports(plant)
    listed = [
        Issue(
            where,
            "incompatible",
            f"{where}: a generic port takes {name} {first} and {second}; expected one {name} "
            "through the module",
            code="generic_conflict",
        )
        for where, name, first, second in conflicts
    ]
    for item in plant._connections:
        source, target = split_end(item["source"]), split_end(item["target"])
        if source not in ports or target not in ports:
            continue
        reason = _reason(ports[source], ports[target], found.get(source, {}), found.get(target, {}))
        if reason is not None:
            where = f"{item['source']} -> {item['target']}"
            listed.append(
                Issue(where, "incompatible", f"{where}: {reason}", code="stream_mismatch")
            )
    return listed


def _reason(source, target, source_fields, target_fields):
    """Return why ``source`` cannot feed ``target`` with what the plant infers, else ``None``."""
    reason = mismatch(source, target)
    if reason is not None or source.carries_stream != target.carries_stream:
        return reason
    first, second = effective(source, source_fields), effective(target, target_fields)
    for name in compared(source):
        if ANY not in (first[name], second[name]) and first[name] != second[name]:
            return f"{name} {first[name]} to {second[name]}"
    return None


def resolve(plant, value):
    """Return ``[(path, port, Port)]`` of a ``"path.port"``, a bound ``Port`` or a ``Module``.

    A module gives each of its ports; a string that names a module does too.
    """
    ports = leaf_ports(plant)
    if isinstance(value, Port):
        path = plant._descendant_path(value.owner)
        if path is None or (path, value.name) not in ports:
            raise ValidationError(f"{value.path}: not a port of {plant.path}", code="unknown_port")
        return [(path, value.name, value)]
    if isinstance(value, Module):
        path = plant._descendant_path(value)
        if path is None:
            raise ValidationError(
                f"{value.path}: not a module of {plant.path}", code="unknown_name"
            )
        return [(p, name, port) for (p, name), port in ports.items() if p == path]
    if not isinstance(value, str):
        raise ValidationError(f"{value!r}: expected 'path.port', a Port or a Module")
    module = plant._find_submodule(value) if value else None
    if module is not None and not is_group(module):
        return [(p, name, port) for (p, name), port in ports.items() if p == value]
    path, _, name = value.rpartition(".")
    if (path, name) not in ports:
        raise ValidationError(
            f"{value!r}: no port of that name in {plant.path}", code="unknown_port"
        )
    return [(path, name, ports[(path, name)])]


def free(plant, path, port, declaration):
    """Return whether the port takes another connection: a ``many`` one, or one with none yet."""
    if declaration.many:
        return True
    side = "inlets" if declaration.direction is Direction.IN else "outlets"
    return not plant._in_use(path, port, side)


def suggestions(plant, path, port, declaration, *, free_only=True, loose=True):
    """Return the ``Suggestion``s of the ports ``(path, port)`` may connect to, best first.

    ``free_only`` leaves out the ports already connected, ``loose`` keeps the matches through
    ``ANY`` or a generic letter. The order is fixed: exact matches first, then the most fields
    equal, then a port whose module is already connected to this one the other way (it closes
    the loop), then the order of the plant.
    """
    found, _ = inferred(plant)
    own = effective(declaration, found.get((path, port), {}))
    outlet = declaration.direction is Direction.OUT
    joined = {
        (split_end(item["source"])[0], split_end(item["target"])[0]) for item in plant._connections
    }
    names = compared(declaration)
    ranked = []
    for (other_path, other_port), other in leaf_ports(plant).items():
        if other_path == path or (free_only and not free(plant, other_path, other_port, other)):
            continue
        source, target = (declaration, other) if outlet else (other, declaration)
        if mismatch(source, target) is not None:
            continue
        theirs = effective(other, found.get((other_path, other_port), {}))
        if any(ANY not in (own[n], theirs[n]) and own[n] != theirs[n] for n in names):
            continue
        exact = [n for n in names if own[n] == theirs[n] and own[n] != ANY]
        missed = [n for n in names if n not in exact]
        if missed and not loose:
            continue
        back = (other_path, path) if outlet else (path, other_path)
        match = Match.LOOSE if missed else Match.EXACT
        item = Suggestion(other, match, exact, missed, back in joined)
        ranked.append(((bool(missed), -len(exact), back not in joined, len(ranked)), item))
    return [item for _, item in sorted(ranked, key=lambda pair: pair[0])]


def open_ports(plant):
    """Return ``[(path, port, Port)]`` of every required port with no connection and no name."""
    return [
        (path, port, declaration)
        for (path, port), declaration in leaf_ports(plant).items()
        if declaration.required
        and not declaration.many
        and free(plant, path, port, declaration)
        and not _named(plant, path, port, declaration)
    ]


def _named(plant, path, port, declaration):
    """Return whether the port is named as a port of the plant."""
    side = "inlets" if declaration.direction is Direction.IN else "outlets"
    return any((path, port) in port_ends(ends) for ends in plant._listed[side].values())


def names_module(plant, end):
    """Return whether ``end`` stands for a module (each of its ports), not one port."""
    if isinstance(end, Module):
        return True
    return isinstance(end, str) and bool(end) and plant._find_submodule(end) is not None


def out_of_range(plant, results):
    """Return a warning for each port whose temperature or pressure left its declared range."""
    frame = results.to_frame()
    found = []
    for (path, port), declaration in leaf_ports(plant).items():
        if not declaration.carries_stream:
            continue
        for name, limits in (
            ("temperature", declaration.temperature),
            ("pressure", declaration.pressure),
        ):
            column = f"{path}.{port}.{name}" if path else f"{port}.{name}"
            if limits is None or column not in frame:
                continue
            values = frame[column].to_numpy(dtype=float)
            outside = int(((values < limits[0]) | (values > limits[1])).sum())
            if outside:
                where = f"{path}.{port}" if path else port
                found.append(
                    Issue(
                        where,
                        "warning",
                        f"{where}: {name} outside [{limits[0]}, {limits[1]}] on {outside} steps; "
                        "expected it within the range the port declares",
                        code="out_of_range",
                    )
                )
    return found
