"""How a call is read: its inlets and its controls and boundaries, and the ports it gives back.

``CallArguments`` is the part of ``Module`` that validates what a caller supplies and what
``forward`` returns: the inlet ports, the keywords for controls and boundaries, the outlets and the
inlets a module draws. It reads the declarations of the module it is mixed into.
"""

from collections.abc import Mapping
from functools import partial

from gemini._utils.strings import did_you_mean, join_names
from gemini.errors import DefinitionError, PhysicsError, ValidationError
from gemini.modules.callrecord import plain_outlet
from gemini.streams.ports import Ports


class CallArguments:
    """Validation of the arguments of a call and of the ports a module returns."""

    def _settled_inlets(self, inlets, call):
        """Return the declared inlets of a call, each drawn one with the value the module drew."""
        values = {
            name: call.drawn[name] if name in call.drawn else inlets[name] for name in self._inlets
        }
        return Ports._trusted(values, self.path)

    def _given_outlets(self):
        """Return the outlets ``forward`` returns: all but those whose takers decide the flow."""
        return [name for name, port in self._outlets.items() if not port.drawn]

    def _drawn_outlets(self):
        """Return the outlets that receive what their takers drew."""
        return [name for name, port in self._outlets.items() if port.drawn]

    def _drawn_inlets(self):
        """Return the inlets whose value ``forward`` returns."""
        return [name for name, port in self._inlets.items() if port.drawn]

    def _fed_inlets(self):
        """Return the single stream inlets a caller supplies, in declaration order."""
        return {
            name: port for name, port in self._inlets.items() if not port.gives and not port.many
        }

    def _checked_drawn(self, returned):
        """Return what ``forward`` drew through its drawn inlets, validated."""
        return {
            name: self._inlets[name].validate(plain_outlet(returned[name]))
            for name in self._drawn_inlets()
        }

    def _split_call_args(self, args, kwargs, state=None):
        """Return validated inlet ``Ports`` and the supplied control/boundary keywords."""
        inlet_names = list(self._fed_inlets())
        ports = inlet_names + list(self._optional_ports())
        valid_names = ports + list(self._controls) + list(self._boundaries)
        self._check_keywords(kwargs, valid_names)
        if len(args) == 1 and isinstance(args[0], Mapping):
            inlet_values = self._mapping_inlets(args[0], kwargs)
        else:
            inlet_values = self._positional_inlets(args, kwargs)
        missing = [name for name in inlet_names if name not in inlet_values]
        if missing:
            raise ValidationError(
                f"{self.path}: missing required inlet(s) {', '.join(missing)}; "
                f"valid names: {join_names(inlet_names)}",
                code="invalid_call",
            )
        inlets = self._validated_ports(
            "inlet",
            self._call_ports(),
            self._with_optional_ports(inlet_values, state),
            partial(ValidationError, code="invalid_call"),
        )
        inputs = {
            name: kwargs[name] for name in self._controls | self._boundaries if name in kwargs
        }
        return inlets, inputs

    def _optional_ports(self):
        """Return the ports a call may leave out: ``many`` inlets and drawn outlets, by name."""
        many = {name: port for name, port in self._inlets.items() if port.many}
        return many | {name: self._outlets[name] for name in self._drawn_outlets()}

    def _call_ports(self):
        """Return every port a call holds a value for: fed inlets, then the optional ports."""
        return self._fed_inlets() | self._optional_ports()

    def _empty_ports(self, values=None, state=None):
        """Return what the optional ports hold when nothing is taken: no list items, the offer.

        ``values`` are the ports of the call, which the offer may read.
        """
        optional = self._optional_ports()
        empty = {name: [] for name, port in optional.items() if port.many}
        if len(empty) == len(optional):
            return empty
        fed = {name: (values or {})[name] for name in self.offer_inlets}
        return empty | {
            name: value for name, value in self._offered(fed, state).items() if name in optional
        }

    def _with_optional_ports(self, values, state=None):
        """Return ``values`` with the optional ports the call left out."""
        if all(name in values for name in self._optional_ports()):
            return values
        return self._empty_ports(values, state) | dict(values)

    def _check_keywords(self, kwargs, valid_names):
        unknown = [name for name in kwargs if name not in valid_names]
        if unknown:
            name = unknown[0]
            raise ValidationError(
                f"{self.path}: unexpected keyword {name!r}; valid names: {join_names(valid_names)}"
                f"{did_you_mean(name, valid_names)}",
                code="invalid_call",
            )

    def _mapping_inlets(self, mapping, kwargs):
        ports = self._call_ports()
        valid = join_names(ports)
        mixed = [name for name in ports if name in kwargs]
        if mixed:
            raise ValidationError(
                f"{self.path}: cannot mix inlet mapping with inlet keyword {mixed[0]!r}; "
                f"valid names: {valid}",
                code="invalid_call",
            )
        unknown = [name for name in mapping if name not in ports]
        if unknown:
            name = unknown[0]
            raise ValidationError(
                f"{self.path}: unknown inlet {name!r}; valid names: {valid}"
                f"{did_you_mean(name, ports)}",
                code="invalid_call",
            )
        return mapping

    def _positional_inlets(self, args, kwargs):
        inlet_names = list(self._fed_inlets())
        valid = join_names(inlet_names)
        if len(args) > len(inlet_names):
            raise ValidationError(
                f"{self.path}: expected at most {len(inlet_names)} positional inlet arguments, "
                f"got {len(args)}; valid names: {valid}",
                code="invalid_call",
            )
        values = dict(zip(inlet_names, args))
        duplicate = values.keys() & kwargs.keys()
        if duplicate:
            raise ValidationError(
                f"{self.path}: multiple values for inlet {next(iter(duplicate))!r}; "
                f"valid names: {valid}",
                code="invalid_call",
            )
        ports = self._call_ports()
        values.update({name: kwargs[name] for name in ports if name in kwargs})
        return values

    def _validated_ports(self, kind, declarations, values, error, prepare=lambda value: value):
        """Return the ``Ports`` of ``values`` validated by ``declarations``, else raise ``error``.

        ``kind`` is ``"inlet"`` or ``"outlet"`` in the message; ``prepare`` is applied to each value
        before it is validated.
        """
        validated = []
        for name, declaration in declarations.items():
            value = prepare(values[name])
            try:
                validated.append((name, declaration.validate(value)))
            except (TypeError, ValueError, PhysicsError) as exc:
                raise error(
                    f"{self.path}: invalid {kind} {name!r}; "
                    f"valid names: {join_names(declarations)}: {exc}"
                ) from exc
        return Ports(validated, path=self.path)

    def _check_outlet_names(self, returned):
        """Reject a ``forward`` result that is not a dict of what the module gives."""
        if not isinstance(returned, dict):
            raise DefinitionError(f"{self.path}: forward must return an outlet dict")
        expected = [*self._given_outlets(), *self._drawn_inlets()]
        missing = set(expected) - returned.keys()
        extra = returned.keys() - set(expected)
        if missing or extra:
            raise DefinitionError(
                f"{self.path}: outlet names missing={sorted(missing)}, extra={sorted(extra)}; "
                f"valid names: {join_names(expected)}"
            )

    def _check_outlets(self, given, taken):
        """Return the outlet ``Ports``: what ``forward`` gave and what its takers took."""
        return self._validated_ports(
            "outlet", self._outlets, given | taken, DefinitionError, plain_outlet
        )

    def _resolve_inputs(self, supplied):
        """Return validated controls and boundaries: supplied, persisted, then default values."""
        return {
            name: (
                declaration.validate(supplied[name])
                if name in supplied
                else self._input_value(name)
            )
            for name, declaration in (self._controls | self._boundaries).items()
        }
