"""The values of a module tree: parameters, controls and boundaries, their validity and snapshots.

``ModuleValues`` is the part of ``Module`` that sets and reads design values, says what the tree
still lacks, and saves and restores parameter snapshots; the work is in ``modules/_utils``.
"""

from pydantic_core import to_jsonable_python

from gemini._utils.strings import did_you_mean, join_names, join_path, snake_case
from gemini.errors import ValidationError
from gemini.modules._utils import description, design
from gemini.streams.fluid import Fluid


class ModuleValues:
    """Setting, checking and saving the values of a module and its children."""

    def _set_inputs(self, mapping):
        """Persist validated controls and boundaries addressed by relative dotted path."""
        declarations = self.inputs()
        pending = []
        for path, value in mapping.items():
            if path not in declarations:
                raise ValidationError(
                    f"{self.path}: unknown control/boundary path {path!r}; valid: "
                    f"{join_names(declarations)}{did_you_mean(path, declarations)}",
                    code="unknown_name",
                )
            declaration = declarations[path]
            pending.append((declaration.owner, declaration.name, declaration.validate(value)))
        for owner, name, value in pending:
            owner._input_values[name] = value
        return self

    def _missing_design(self):
        """Return the names of what this module's design lacks; a class with such a rule says."""
        return []

    def _missing_designs(self):
        """Return the dotted paths of what the designs of this module tree lack."""
        return [
            join_path(path, name)
            for path, module in self.named_modules()
            for name in module._missing_design()
        ]

    def _check_design(self):
        """Raise ``missing_value`` for each design value the tree lacks, before a run starts."""
        missing = self._missing_designs()
        if missing:
            raise self._missing_error(missing)

    def _missing_error(self, paths):
        """Return the one ``missing_value`` error that lists every path with its meaning."""
        items = [
            description.missing_item(description.missing_entry(path, self.get(path)))
            for path in paths
        ]
        listed = "; ".join(f"{item['path']}: {item['message']}" for item in items)
        return ValidationError(
            f"{self.path}: uninitialized parameters: {listed}",
            path=items[0]["path"],
            code="missing_value",
            problems=items,
        )

    def _missing_paths(self):
        """Return the dotted paths of what the tree lacks: design values, then parameters."""
        uninitialized = [name for name, value in self.named_parameters() if not value.initialized]
        return list(dict.fromkeys(self._missing_designs() + uninitialized))

    def check(self):
        """Return the issues of the tree, an empty list when it can run; it never raises.

        One ``missing`` issue per unset parameter, with its path (dotted, from this module), its
        quantity, the units a value may be given in and what it means. Design values a module still
        waits for come first.
        """
        return [description.missing_issue(path, self.get(path)) for path in self._missing_paths()]

    def _prepare(self):
        """Reject uninitialized parameters, before any call."""
        missing = self._missing_paths()
        if missing:
            raise self._missing_error(missing)

    @property
    def is_initialized(self):
        """Whether every parameter in this module tree has a value."""
        return not self._missing_paths()

    def _override_params(self, values):
        """Set parameters by local or dotted path as overrides, which win over every date."""
        for name, value in values.items():
            declaration = self.get(name)
            declaration.owner._set_parameter(declaration.name, value)
        return self

    def _set_parameter(self, name, value):
        """Set one own parameter as an explicit override; a deriving module derives from it."""
        if self._derives_params():
            self._set_si_params("", {name: value})
            return
        self._parameters[name].set(value)

    def _derives_params(self):
        """Return whether this module derives its children's values; only a plant may."""
        return False

    def describe(self):
        """Return the plain description of this module: see ``modules.md``."""
        return description.describe(self)

    def parameter_schema(self):
        """Return the JSON Schema of the parameters of this module."""
        return description.parameter_schema(self)

    def validate_params(self, params, on_error="raise"):
        """Check ``params`` without changing the module: ``[]``, or every problem.

        The values are those ``set_params`` takes, so a bare number for a value with a dimension
        is an ``invalid_value`` problem.
        """
        return description.validate_params(self, params, on_error)

    def _params_at(self, at):
        """Return the complete validated parameter mapping active at an instant.

        ``at=None`` selects the latest snapshot. Explicit overrides win over every snapshot.
        """
        selected = design.snapshot_at(self, at)
        values = selected.params | self._param_overrides
        return {name: self._parameters[name].validate(value) for name, value in values.items()}

    def _root_inputs(self):
        """Return the stated fields of the root inlets; only a plant states them."""
        return {}

    def _has_input_value(self, name):
        """Return whether control or boundary ``name`` has a persisted value."""
        return name in self._input_values

    def _apply_params_at(self, at):
        """Apply dated parameter snapshots recursively while retaining explicit overrides."""
        for module in self.modules():
            for name, value in module._params_at(at).items():
                module._parameters[name].set(value, explicit=False)

    def state_dict(self):
        """Return JSON-safe parameter and fluid snapshots for the complete tree."""
        return {
            path: {
                "type": snake_case(module.name),
                "params": {
                    name: to_jsonable_python(parameter.value)
                    for name, parameter in module._parameters.items()
                    if parameter.initialized
                },
                "fluid": module._fluid.model_dump(mode="json"),
            }
            for path, module in self.named_modules()
        }

    def set_state_dict(self, state, strict=True):
        """Validate snapshots before applying any of them.

        With ``strict`` the snapshot paths must equal the tree's module paths; otherwise only the
        modules named in ``state`` are filled and unknown paths are rejected.
        """
        modules = dict(self.named_modules())
        missing, unexpected = modules.keys() - state.keys(), state.keys() - modules.keys()
        if unexpected or (strict and missing):
            raise ValidationError(
                f"{self.path}: state paths differ; missing={missing}, unexpected={unexpected}",
                code="invalid_format",
            )
        pending = []
        for path, entry in state.items():
            module = modules[path]
            values = {
                name: module.get(name).validate(value) for name, value in entry["params"].items()
            }
            pending.append((module, values, Fluid._of(entry["fluid"])))
        for module, values, fluid in pending:
            for name, value in values.items():
                module._parameters[name].set(value, explicit=False)
            object.__setattr__(module, "_fluid", fluid)
        return self

    def set_params(self, path, params, valid_from=None):
        """Store validated parameters of the module at ``path`` as a dated snapshot.

        The snapshot is the values in force at ``valid_from`` merged with ``params``; without a
        date the undated base entry and the current values change. Names may be dotted. A value
        with a dimension is a ``gm.units.Quantity`` or its ``{"value", "unit"}`` dict, converted
        to SI after its unit is checked against the declared quantity; a bare number for it
        raises ``ValidationError`` (``invalid_value``) naming the path, the quantity and the
        accepted units, zero included. A parameter without a dimension takes a plain number.
        Returns the module.

        This is the public door. It converts and hands over to ``_set_si_params``, the one
        private method that stores SI values: the engine, ``study``, ``size`` and the case
        call that one.
        """
        return self._set_si_params(path, design.in_si(self, path, params), valid_from)

    def _set_si_params(self, path, params, valid_from=None):
        """Store the SI values ``params`` of the module at ``path``; ``set_params`` calls this.

        Every route that sets parameters comes here. A plant class that derives its children's
        values overrides this method, not ``set_params`` (see ``modules.md``); a value for it, at
        any depth, reaches that override.
        """
        return design.set_params(self, path, params, valid_from)

    def params_at(self, path, time=None):
        """Return the parameter values of the module at ``path`` in force at ``time``."""
        return design.params_at(self, path, time)

    def param_history(self, path):
        """Return the dated parameter snapshots of the module at ``path``."""
        return design.param_history(self, path)

    def bindable(self, path):
        """Return what can be bound at ``path``, by section."""
        return design.bindable(self, path)

    def set_bindings(self, path, bindings):
        """Replace the bindings of the module at ``path``; units are checked. Returns the module."""
        return design.set_bindings(self, path, bindings)
