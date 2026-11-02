"""The state of a module tree: what a call starts from and how a step advances it.

A stateful module declares ``State`` values with no default. The state of a plant is the nested
dict of the states of its children, by child name; a stateless module has ``{}``. ``Stateful`` is
the part of ``Module`` that checks the state a call is given, reads the next state back from
``update`` and runs one step; ``nested`` and ``started`` build and merge such trees.
"""

from gemini import ops
from gemini._utils.mappings import set_nested
from gemini._utils.strings import did_you_mean, join_names, join_path
from gemini.errors import DefinitionError, ValidationError
from gemini.modules import unconverted
from gemini.modules.callrecord import current_call, has_arrays, numpy_ports


def nested(values):
    """Return the state tree of ``values``, a mapping of dotted module paths to their states."""
    tree = {}
    for path, states in values.items():
        if path:
            set_nested(tree, tuple(path.split(".")), dict(states))
        else:
            tree.update(states)
    return tree


def merged(start, advanced):
    """Return the tree ``start`` with the states of ``advanced`` in place of its own.

    Neither argument changes; a module that ``advanced`` lacks keeps the state it has in ``start``.
    """
    result = dict(start)
    for key, value in advanced.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merged(result[key], value)
        else:
            result[key] = value
    return result


class Stateful:
    """State checking, update and stepping of a module; mixed into ``Module``."""

    @property
    def stateful(self):
        """Whether the module declares states of its own."""
        return bool(self._states)

    def _has_state(self):
        """Return whether this module or a descendant declares states."""
        return any(module._states for module in self.modules())

    def initial_state(self):
        """Return the states of an unconverted tree at their defaults, ``None`` without states.

        A converted module has no default: its state comes from ``case.initial_state``, so asking
        for it without a state raises ``missing_value``.
        """
        if self._states:
            return self._call_state(None)
        states = {
            name: child_state
            for name, child in self.named_children()
            if (child_state := child.initial_state()) is not None
        }
        return states or None

    def _call_state(self, state):
        """Return the state a call starts from: the validated own states, else the given tree."""
        if not self._states:
            return dict(state) if state else {}
        if state is None:
            if self._unconverted:
                return unconverted.initial_states(self)
            raise self._missing_state(list(self._states))
        unknown = sorted(state.keys() - self._states.keys())
        if unknown:
            raise ValidationError(
                f"{self.path}: unknown state {unknown[0]!r}; valid: {join_names(self._states)}"
                f"{did_you_mean(unknown[0], self._states)}",
                code="unknown_name",
            )
        given = {name: self._states[name].validate(value) for name, value in state.items()}
        missing = [name for name in self._states if name not in given]
        if self._unconverted:
            return unconverted.initial_states(self) | given
        if missing:
            raise self._missing_state(missing)
        return {name: given[name] for name in self._states}

    def _missing_state(self, names):
        """Return the error for states a call was not given: the case states them."""
        return ValidationError(
            f"{self.path}: state {join_names(names)} has no value; expected it in "
            "case.initial_state, a state has no default",
            path=join_path("initial_state", self.path),
            code="missing_value",
        )

    def _probe_state(self):
        """Return a state for a probe that only needs forward to run: every state at zero."""
        if self._unconverted:
            return unconverted.initial_states(self) if self._states else {}
        return {name: 0.0 for name in self._states}

    def update(self, inputs, inlets, outlets, state, dt):
        """Return the next state of this module over ``dt`` seconds; a stateful module overrides.

        Pure: it writes nothing to ``self``. ``inputs`` are the controls and boundaries of the
        call, ``inlets`` and ``outlets`` its ports and ``state`` the state the call started from.
        It returns every key of the declared states, no more and no fewer.
        """
        raise NotImplementedError(f"{type(self).__name__} declares states without update")

    def _advance(self, result, dt):
        """Return the next state from the ``ModuleResult`` of a call.

        A module with states advances them with ``update``. A module without is a composite: its
        state is the nested dict of what each stateful child it called advanced to, by child name.
        """
        if self._states:
            return self._advance_leaf(result, dt)
        advanced, seen = {}, set()
        for path, child_result in result.call_records:
            child = self.get_submodule(path)
            if not child._has_state():
                continue
            if path in seen:
                raise ValidationError(
                    f"{self.path}.{path}: stateful module called more than once in one step",
                    code="invalid_design",
                )
            seen.add(path)
            set_nested(advanced, tuple(path.split(".")), child._advance(child_result, dt))
        return advanced

    def _advance_leaf(self, result, dt):
        """Run ``update`` on the values of a call, in the scope the call itself ran in."""
        inlets = result.inlets
        with ops.scope.Scope(self._scalar_mode(), has_arrays(inlets, result.inputs)) as scope:
            call = self._eager_call(result.inputs, None, result.state, scope.wrapping)
            call.outputs.update(result.outputs)
            token = current_call.set(call)
            try:
                scoped = numpy_ports(inlets) if scope.wrapping else inlets
                if self._unconverted:
                    values = unconverted.advance(self, scoped, result.outlets, dt)
                else:
                    values = self.update(call.inputs, scoped, result.outlets, call.state, dt)
            finally:
                current_call.reset(token)
        return self._checked_state(ops.scope.plain(values))

    def _checked_state(self, values):
        """Return the validated states ``update`` returned, or raise naming the key."""
        if not isinstance(values, dict):
            raise DefinitionError(f"{self.path}: update must return a dict of states")
        missing = [name for name in self._states if name not in values]
        extra = [name for name in values if name not in self._states]
        if missing or extra:
            key = (missing or extra)[0]
            raise DefinitionError(
                f"{self.path}: update returned the states {sorted(values)}; "
                f"{'missing' if missing else 'extra'} key {key!r}; "
                f"expected {join_names(self._states)}"
            )
        return {name: self._states[name].validate(values[name]) for name in self._states}

    def step(self, state, dt, inlets):
        """Advance every declared state over ``dt`` seconds; return ``(next_state, result)``.

        ``state`` is the tree of the states at the start, or ``None`` for an unconverted tree at its
        defaults. The call is ``self(inlets, state=state)`` and the next state is what ``update``
        of each stateful module returns for the values of its own call. A stateful descendant
        called twice in one step is refused.
        """
        if dt <= 0:
            raise ValidationError(
                f"{self.path}: dt = {dt} s; expected a positive step", code="invalid_design"
            )
        explicit = [
            path
            for path, module in self.named_modules()
            if path and module.stateful and not module._states
        ]
        if explicit:
            raise ValidationError(
                f"{self.path}: stateful descendants {', '.join(explicit)} need a step method "
                "on this composite that steps them",
                code="invalid_design",
            )
        start = state if state is not None else self.initial_state() or {}
        result = self._run((inlets,), {}, start)
        return merged(start, self._advance(result, dt)) or None, result
