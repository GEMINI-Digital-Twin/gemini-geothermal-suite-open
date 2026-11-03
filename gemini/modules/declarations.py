"""Declarations registered by :class:`gemini.modules.Module`.

A data type says what a value is; a role says how a computation graph treats it. ``Parameter`` is
calibratable design data; a ``Constant`` is fixed by default and can be released for sensitivity
studies (defined in ``gemini.ops`` because physics uses it, for example
``physics.constants.ESP_REFERENCE_FREQUENCY``); a ``State`` is carried from step to step. Each
numeric parameter and each constant a traced call uses is one named graph input, never a literal.
"""

import numbers
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from functools import lru_cache, partial
from typing import Annotated, Any

import numpy as np
from pydantic import Field, TypeAdapter
from pydantic import ValidationError as PydanticError

from gemini import ops, units
from gemini._utils.strings import did_you_mean, join_names
from gemini.errors import DefinitionError, PhysicsError, ValidationError
from gemini.streams import kinds as streams
from gemini.streams.energy import Energy
from gemini.streams.flows import Stream
from gemini.streams.fluid import Fluid
from gemini.units.quantities import Power


class _Unset:
    """Type of the ``UNSET`` sentinel; copying or pickling returns the same object."""

    def __repr__(self):
        """Return ``UNSET``."""
        return "UNSET"

    def __copy__(self):
        """Return the sentinel itself."""
        return self

    def __deepcopy__(self, memo):
        """Return the sentinel itself."""
        return self

    def __reduce__(self):
        """Pickle as a reference to the module-level ``UNSET``."""
        return "UNSET"


UNSET = _Unset()


_NUMPY_KINDS = {float: np.float64, bool: np.bool_}

_MISS = object()
"""Result of a quick check that cannot decide; the full validation then runs."""

_PLAIN_KEYS = {
    "type",
    "minimum",
    "exclusiveMinimum",
    "maximum",
    "exclusiveMaximum",
    "quantity",
    "unit",
}


def _exact(kind, optional, value):
    """Return ``value`` when it is exactly a ``kind`` (or ``None`` if optional), else ``_MISS``.

    An ``np.float64`` or ``np.bool_`` of the eager scope converts to its Python kind.
    """
    if type(value) is kind or (value is None and optional):
        return value
    if type(value) is _NUMPY_KINDS.get(kind):
        return kind(value)
    return _MISS


def _bounded_float(ge, gt, le, lt, optional, value):
    """Return ``value`` when it is a ``float`` within every bound (NaN never is), else ``_MISS``."""
    if type(value) is np.float64:
        value = float(value)
    if type(value) is not float:
        return None if value is None and optional else _MISS
    if (
        (ge is None or value >= ge)
        and (gt is None or value > gt)
        and (le is None or value <= le)
        and (lt is None or value < lt)
    ):
        return value
    return _MISS


def _miss(value):
    return _MISS


def _quick_check(schema, limits):
    """Return the cheap check of the common case of a declared kind, from its JSON schema.

    Only a plain number, flag or text (or one of them or ``None``) has one: it accepts the value
    exactly as validation would, unchanged, and returns ``_MISS`` for everything else. The
    check is a ``functools.partial`` of module functions, so a declaration still copies and
    pickles.
    """
    variants = schema.get("anyOf", [schema])
    values = [variant for variant in variants if variant.get("type") != "null"]
    if len(values) != 1 or set(values[0]) - _PLAIN_KEYS:
        return _miss
    optional = len(values) < len(variants)
    kind = values[0].get("type")
    if kind == "number" and limits:
        bounds = (limits.get(key) for key in ("ge", "gt", "le", "lt"))
        return partial(_bounded_float, *bounds, optional)
    exact = {"number": float, "boolean": bool, "string": str}.get(kind)
    return partial(_exact, exact, optional) if exact else _miss


_BOUND_FAILURES = {"greater_than", "greater_than_equal", "less_than", "less_than_equal"}


def _failure_code(cause):
    """Return the ``gm.errors.CODES`` entry of a failed validation: unit, bound or other value."""
    if isinstance(cause, ValidationError) and cause.code == "invalid_unit":
        return "invalid_unit"
    if isinstance(cause, PydanticError) and any(
        item["type"] in _BOUND_FAILURES for item in cause.errors()
    ):
        return "out_of_bounds"
    return "invalid_value"


@lru_cache(maxsize=None)
def _built(kind, bounds):
    """Return the Pydantic validator of ``kind`` with its bounds, and its JSON schema metadata.

    A plant declares the same few kinds hundreds of times, and building one costs a millisecond.
    """
    limits = dict(bounds)
    adapter = TypeAdapter(Annotated[kind, Field(**limits)] if limits else kind)
    return (adapter, *_schema_metadata(adapter))


_LIMIT_KEYS = {"minimum": "ge", "exclusiveMinimum": "gt", "maximum": "le", "exclusiveMaximum": "lt"}


def _limits(schema):
    """Return the ``ge``/``gt``/``le``/``lt`` bounds of the value (or list item) in ``schema``."""
    value_schema = _value_schema(schema)
    return {key: value_schema[name] for name, key in _LIMIT_KEYS.items() if name in value_schema}


def _value_schema(schema):
    """Return the schema of the non-null variant of ``schema``, or of its list items."""
    variants = schema.get("anyOf", [schema])
    value_schema = next((value for value in variants if value.get("type") != "null"), schema)
    return value_schema.get("items", value_schema)


def _schema_metadata(adapter):
    """Return the JSON schema of ``adapter`` and the quantity, unit and additivity of its value.

    Optional kinds describe the non-null variant, and lists describe their items.
    """
    schema = adapter.json_schema()
    value_schema = _value_schema(schema)
    quantity = value_schema.get("quantity")
    return schema, quantity, value_schema.get("unit")


_IMMUTABLE = (float, int, bool, str, type(None))


class Declaration:
    """Validated metadata attached to one module instance."""

    section = "declaration"
    _validated_default = _MISS

    def __init__(self, type, *, default=UNSET, description=None, **bounds):
        """Build validation metadata for one declared value of ``type``."""
        self.type = type
        self.default = default
        self.description = description
        self.bounds = dict(bounds)
        self.name = None
        self.owner = None
        built = _built(type, tuple(sorted(bounds.items())))
        self._adapter, self.schema, self.quantity, self.unit = built
        self._limits = None
        self._quick = _quick_check(self.schema, self.limits())

    @property
    def path(self):
        """Return the declaration's fully qualified module path."""
        if self.owner is None or self.name is None:
            return self.name or "<unbound>"
        return f"{self.owner.path}.{self.name}"

    def limits(self):
        """Return the numeric bounds the value must satisfy, as ``ge``/``gt``/``le``/``lt``.

        They are read once from the quantity metadata and the declared ``bounds`` (both are in the
        schema, the stricter wins) and apply to each item of a list. A kind without bounds, such
        as a flag or a text, gives an empty mapping.
        """
        if self._limits is None:
            self._limits = _limits(self.schema)
        return self._limits

    def value_type(self):
        """Return the JSON type of the value (of each list item): ``number``, ``integer``, ...

        ``None`` for a kind without a schema, such as ``Any``.
        """
        return _value_schema(self.schema).get("type")

    def _options(self):
        """Return the allowed values of a ``Literal`` kind in declared order, else ``None``."""
        value_schema = _value_schema(self.schema)
        if "const" in value_schema:
            return (value_schema["const"],)
        options = value_schema.get("enum")
        return None if options is None else tuple(options)

    def accepts_none(self):
        """Return whether the declared kind is ``X | None``."""
        return any(variant.get("type") == "null" for variant in self.schema.get("anyOf", ()))

    def bind(self, owner, name):
        """Attach this declaration to a module and local name."""
        self.owner, self.name = owner, name
        return self

    def prime_default(self):
        """Validate the default once, when the module registers it, so a call writes nothing."""
        if self.default is not UNSET and self._validated_default is _MISS:
            self._validated_default = self.validate(deepcopy(self.default))

    def default_value(self):
        """Return the default as a fresh value, validated at registration."""
        validated = self._validated_default
        if validated is _MISS:
            validated = self.validate(deepcopy(self.default))
        if type(validated) in _IMMUTABLE:
            return validated
        return deepcopy(validated)

    def validate(self, value):
        """Convert public units and validate the resulting SI value.

        A plain value of the declared kind inside its bounds (an exact ``float``, ``bool`` or
        ``str``, or ``None`` for an optional kind) returns unchanged without units or Pydantic;
        any other value, and every failure, takes the full path below. An ``np.float64`` or
        ``np.bool_`` converts to ``float`` or ``bool`` first, and a ``Failed`` raises its error.
        """
        accepted = self._quick(value)
        if accepted is not _MISS:
            return accepted
        value = ops.scope.plain(value)
        try:
            value = units.value_in_si(value, self.unit, self.path, self.quantity)
            return self._adapter.validate_python(value)
        except (TypeError, ValueError, PydanticError, PhysicsError) as exc:
            raise ValidationError(
                f"{self.path}: invalid {self.section} value {value!r}"
                + (f"; expected {self.unit}" if self.unit else "")
                + f" ({exc})",
                code=_failure_code(exc),
            ) from exc


class Parameter(Declaration):
    """Design data fixed during a run, with optional dated values."""

    section = "parameter"

    def __init__(
        self,
        type,
        *,
        default=UNSET,
        shape=None,
        calibratable=False,
        structural=False,
        case=None,
        description=None,
        **bounds,
    ):
        """Create design data with optional shape, bounds and calibration metadata.

        ``case`` is the path of the case value that sets this parameter, such as
        ``"site.ground.gradient"``: a plant dict refuses it, and a run takes it from the
        case.

        A ``structural`` parameter decides the shape of the computation (a loop count, a value
        that changes a ``Fluid``): a trace reads it as a plain value and its value is a guard of
        the graph cache, never a graph input.
        """
        super().__init__(type, default=default, description=description, **bounds)
        self.shape = shape
        self.calibratable = calibratable
        self.structural = structural
        self.case = case
        self.value = UNSET
        self._history: list[tuple[datetime | None, Any]] = []
        if default is not UNSET:
            self.value = self.validate(deepcopy(default))
            self._history.append((None, deepcopy(self.value)))
        self.prime_default()

    @property
    def history(self):
        """Project the owner's dated snapshots onto this parameter."""
        if self.owner is None or not getattr(self.owner, "_param_history", None):
            return deepcopy(self._history)
        return [
            (snapshot.valid_from, self.validate(snapshot.params[self.name]))
            for snapshot in self.owner._param_history
            if self.name in snapshot.params
        ]

    @property
    def initialized(self):
        """Whether the parameter currently contains a value."""
        return self.value is not UNSET

    def validate(self, value):
        """Validate the value and its optional outer shape."""
        value = super().validate(value)
        if self.shape is not None and value is not None:
            actual = (len(value),) if hasattr(value, "__len__") else ()
            if actual != self.shape:
                raise ValidationError(f"{self.path}: shape = {actual}; expected {self.shape}")
        return value

    def set(self, value, *, explicit=True):
        """Validate and store a current parameter value."""
        self.value = self.validate(value)
        if explicit and self.owner is not None:
            self.owner._param_overrides[self.name] = deepcopy(self.value)
        return self.value


class Port(Declaration):
    """A port of a module: what it takes (``Direction.IN``) or gives (``Direction.OUT``).

    A port carries a stream of a ``fluid`` (a ``gm.Fluid`` preset such as ``Fluid.WATER``,
    compared by its family; ``Fluid.ANY`` takes any) or a power of an ``energy`` (a
    ``gm.streams.Energy`` preset such as ``Energy.ELECTRICITY``; ``Energy.ANY`` takes any):
    exactly one of the two. A stream port also has a ``phase`` and a ``level`` (the temperature
    role of its circuit), ``ANY`` when not given, and may state ``temperature`` and ``pressure``
    ranges ``(low, high)`` in SI that it is meant for, which
    ``Plant.check(results=...)`` checks a run against. gemini's
    own modules state every field, so that a connection is checked precisely.

    ``generic`` names a type variable shared by ports of one module: a pipe's ``fluid_in`` and
    ``fluid_out`` are both ``"T"``, so they carry the same fluid, which the plant infers from the
    connections. ``flow`` says who decides what the port carries: ``Flow.DRAWN``, the taker (a
    grid, a power inlet the module computes), or ``Flow.IMPOSED``, the giver; without it a single
    power inlet and an outlet that feeds many ports are drawn, the rest imposed. ``many`` lets
    several ports connect: the value is the list of what they give. ``required`` is whether the
    port must be connected. ``offered`` (outlets only) says the value exists before the other
    modules run, which ``Module._offer`` gives.

    A stream port has no JSON schema, quantity or unit; a power port has the unit W. ``kind``
    is the label of the port before 0.6.0, which descriptions keep.
    """

    def __init__(
        self,
        direction,
        *,
        fluid=None,
        energy=None,
        phase=streams.Phase.ANY,
        level=streams.Level.ANY,
        generic=None,
        many=False,
        flow=None,
        required=True,
        temperature=None,
        pressure=None,
        offered=False,
        description=None,
    ):
        """Declare a port of a ``fluid`` or of an ``energy``; see the class for the rest."""
        self.direction = _member(streams.Direction, direction, "direction")
        if (fluid is None) == (energy is None):
            raise DefinitionError(
                f"Port: fluid = {fluid!r}, energy = {energy!r}; expected exactly one: a fluid "
                "for a stream port (Fluid.ANY for any), an energy for a power port (Energy.ANY)"
            )
        stream = fluid is not None
        if stream and not isinstance(fluid, (Fluid, type(Fluid.ANY))):
            raise DefinitionError(
                f"Port: fluid = {fluid!r}; expected a gm.Fluid such as Fluid.WATER or Fluid.ANY"
            )
        own = {"phase": phase, "level": level, "temperature": temperature, "pressure": pressure}
        if not stream and (
            phase != "any" or level != "any" or temperature is not None or pressure is not None
        ):
            raise DefinitionError(f"Port: a power port has no phase, level or ranges; got {own}")
        if offered and self.direction is not streams.Direction.OUT:
            raise DefinitionError("Port: offered is for an outlet; this port is an inlet")
        self.flow = _member(streams.Flow, flow or _flow(self.direction, stream, many), "flow")
        if many and self.direction is streams.Direction.OUT and self.flow is not streams.Flow.DRAWN:
            raise DefinitionError("Port: an outlet that feeds many ports has its flow drawn")
        self.fluid = fluid
        self.energy = None if stream else _form(energy)
        self.phase = _member(streams.Phase, phase, "phase") if stream else None
        self.level = _member(streams.Level, level, "level") if stream else None
        self.generic = generic
        self.many = many
        self.required = required
        self.temperature = None if temperature is None else tuple(temperature)
        self.pressure = None if pressure is None else tuple(pressure)
        self.offered = offered
        self.carries_stream = stream
        self.type = Stream if stream else Power
        self.default = UNSET
        self.description = description
        self.bounds = {}
        self.name = None
        self.owner = None
        self._limits = None
        self.schema, self.quantity, self.unit = {}, None, None
        if not stream:
            self.quantity, self.unit = "power", "W"

    @property
    def section(self):
        """Return ``"inlet"`` or ``"outlet"``, the section of the port in a module."""
        return "inlet" if self.direction is streams.Direction.IN else "outlet"

    @property
    def drawn(self):
        """Return whether the taker decides what the port carries."""
        return self.flow is streams.Flow.DRAWN

    @property
    def gives(self):
        """Return whether a call computes this inlet and nobody supplies it: a drawn power."""
        return self.direction is streams.Direction.IN and self.drawn and not self.carries_stream

    @property
    def kind(self):
        """Return the label of the port before 0.6.0, ``None`` for one of any fluid."""
        if self.generic is not None:
            return None
        return streams.label(
            self.carries_stream,
            self.phase,
            self.value_of("fluid"),
            self.level,
            self.value_of("energy"),
        )

    def value_of(self, name):
        """Return the text of field ``name`` that connections compare, ``None`` if it has none.

        The fluid compares by its family (``Fluid.family``), ``"any"`` when the port takes any.
        """
        if name == "fluid":
            if not self.carries_stream:
                return None
            return self.fluid.family
        if name == "energy":
            return None if self.carries_stream else self.energy.name
        value = getattr(self, name)
        return None if value is None else value.value

    def fields(self):
        """Return the fields of the port as keyword arguments of ``Port``, without its direction.

        A stream port gives its phase, fluid and level, a power port its energy.
        """
        own = (
            {
                "phase": self.phase,
                "fluid": self.fluid,
                "level": self.level,
                "temperature": self.temperature,
                "pressure": self.pressure,
            }
            if self.carries_stream
            else {"energy": self.energy}
        )
        return own | {
            "flow": self.flow,
            "generic": self.generic,
            "many": self.many,
            "required": self.required,
            "description": self.description,
        }

    def validate(self, value):
        """Return the value of the port; a ``many`` port holds a list of them."""
        if self.many:
            return [self._item(item) for item in value]
        return self._item(value)

    def _item(self, value):
        """Return a stream, or a number: a mapping of fields builds a stream."""
        if not self.carries_stream:
            return self._power(value)
        if isinstance(value, self.type):
            return value
        if isinstance(value, Mapping):
            return self.type(**value)
        raise ValidationError(
            f"{self.path}: invalid {self.section} value {value!r}; expected a {self.type.__name__}"
        )

    def _power(self, value):
        """Return a power [W]: a quantity or a number; an array over rows passes unchanged."""
        if isinstance(value, ops.Symbolic) or (isinstance(value, np.ndarray) and value.ndim):
            return value
        value = units.value_in_si(ops.scope.plain(value), self.unit, self.path, self.quantity)
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise ValidationError(f"{self.path}: value = {value!r}; expected a power [W]")
        return float(value)


def _flow(direction, stream, many):
    """Return the flow of a port that states none: drawn or imposed.

    The taker draws a single power inlet and an outlet that feeds many ports; the giver imposes
    the rest.
    """
    if direction is streams.Direction.OUT:
        return streams.Flow.DRAWN if many else streams.Flow.IMPOSED
    return streams.Flow.DRAWN if not stream and not many else streams.Flow.IMPOSED


def _carried(port):
    """Return ``"stream"`` or ``"power"``, what a port carries."""
    return "stream" if port.carries_stream else "power"


def _form(value):
    """Return the ``Energy`` preset of a form or its name, or raise ``DefinitionError``."""
    try:
        return Energy.of(value)
    except ValidationError as error:
        raise DefinitionError(f"Port: {error}") from None


def _member(enum, value, name):
    """Return ``value`` as a member of ``enum``, or raise ``DefinitionError`` naming ``name``."""
    try:
        return enum(value)
    except ValueError:
        choices = [item.value for item in enum]
        raise DefinitionError(
            f"Port: {name} = {value!r}; expected one of {join_names(choices)}"
            f"{did_you_mean(str(value), choices)}"
        ) from None


def mismatch(source, target):
    """Return why the outlet ``source`` cannot feed the inlet ``target``, or ``None`` if it can.

    The one rule of a connection: an outlet to an inlet, a stream to a stream or a power to a
    power, and each of phase,
    fluid (by family), level and energy equal or ``ANY`` on one side. A generic port compares as
    ``ANY`` here; the plant checks what its type variable becomes (``gemini.plants._utils.ports``).
    """
    if (
        source.direction is not streams.Direction.OUT
        or target.direction is not streams.Direction.IN
    ):
        return "expected an outlet to an inlet"
    if source.carries_stream != target.carries_stream:
        return f"{_carried(source)} to {_carried(target)}"
    for name in ("phase", "fluid", "level", "energy"):
        first, second = source.value_of(name), target.value_of(name)
        if first is None or second is None or first == second or "any" in (first, second):
            continue
        return f"{name} {first} to {second}"
    return None


class Control(Declaration):
    """Operating command that an optimiser or agent may change."""

    section = "control"


class Boundary(Declaration):
    """External operating condition that the system cannot set.

    ``case`` is the path of the case value that gives this boundary, such as
    ``"demand.cooling.indoor_temperature"``: a plant dict refuses it, and a run takes it from the
    case unless the plan gives the boundary at each step.
    """

    section = "boundary"

    def __init__(self, type, *, case=None, **kwargs):
        """Create a boundary of ``type``, optionally given by the case at ``case``."""
        super().__init__(type, **kwargs)
        self.case = case


class State(Declaration):
    """Value a stateful module carries from one time step to the next; it has no default.

    The case states where a run starts (``case.initial_state``): ``forward`` and ``update`` take
    the value in their ``state`` argument and ``update`` returns the value at the end of the step.
    ``default`` is accepted only for a module not yet converted to that contract, and a converted
    module that gives one is refused when it is built.
    """

    section = "state"

    def __init__(self, type, *, default=UNSET, description=None, **bounds):
        """Declare a carried value, with a default only while its module is not converted."""
        super().__init__(type, default=default, description=description, **bounds)
        self.prime_default()


class Output(Declaration):
    """Computed value recorded for one call."""

    section = "output"

    def __init__(self, type, *, soft_sensor=False, description=None):
        """Declare a computed value and its recording semantics."""
        super().__init__(type, description=description)
        self.soft_sensor = soft_sensor
        self.formula = None

    @classmethod
    def _combination(cls, formula, description):
        output = cls(Any, description=description)
        output.formula = formula
        return output

    @classmethod
    def difference(cls, first, second, *, description=None):
        """Declare ``first - second`` of two paths of a plant, such as ``"riser.wellhead_out.T"``.

        A path is an output or a port field of a child, or a bare name for an earlier output of the
        plant. The plant gives the output the kind of its paths.
        """
        return cls._combination(("difference", first, second), description)

    @classmethod
    def ratio(cls, numerator, denominator, *, description=None):
        """Declare ``numerator / denominator`` of two paths of a plant; zero gives ``None``."""
        return cls._combination(("ratio", numerator, denominator), description)

    @classmethod
    def sum(cls, first, second, *others, description=None):
        """Declare the sum of two or more paths of a plant."""
        return cls._combination(("sum", first, second, *others), description)
