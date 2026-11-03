"""The module tree: children, paths and the listings of declarations below a module."""

from gemini._utils.strings import close_matches, did_you_mean, join_names, join_path, split_path
from gemini.errors import ValidationError


class ModuleTree:
    """Navigation of the children of a module and listings of the declarations of the tree."""

    def named_children(self):
        """Iterate immediate children in insertion order."""
        yield from self._children.items()

    def children(self):
        """Iterate immediate child modules."""
        yield from self._children.values()

    def named_modules(self, prefix=""):
        """Walk self and descendants once using dotted paths."""
        seen = set()
        waiting = [(prefix, self)]
        while waiting:
            path, module = waiting.pop()
            if id(module) in seen:
                continue
            seen.add(id(module))
            yield path, module
            below = [(join_path(path, name), child) for name, child in module.named_children()]
            waiting.extend(reversed(below))

    def modules(self):
        """Walk self and all unique descendants."""
        for _, module in self.named_modules():
            yield module

    def get_submodule(self, path):
        """Resolve a dotted descendant path; the empty path denotes self."""
        module = self._find_submodule(path)
        if module is None:
            raise ValidationError(
                f"{self.path}: unknown module path {path!r}"
                f"{did_you_mean(path, dict(self.named_modules()))}",
                code="unknown_name",
            )
        return module

    def _find_submodule(self, path):
        """Return the descendant at a dotted path, or ``None`` when there is none."""
        module = self
        for part in path.split(".") if path else ():
            module = module._children.get(part)
            if module is None:
                return None
        return module

    @property
    def is_leaf(self):
        """Whether this module owns no child modules."""
        return not self._children

    def _named(self, registry_name, recurse):
        for path, module in self.named_modules() if recurse else [("", self)]:
            for name, declaration in getattr(module, registry_name).items():
                yield join_path(path, name), declaration

    def _section(self, registry_name, recurse):
        return dict(self._named(registry_name, recurse))

    def parameters(self, recurse=True):
        """Iterate parameter declarations of this module and, by default, its descendants."""
        for _, parameter in self._named("_parameters", recurse):
            yield parameter

    def named_parameters(self, recurse=True):
        """Iterate ``(dotted path, parameter)`` pairs relative to this module."""
        yield from self._named("_parameters", recurse)

    def controls(self, recurse=True):
        """Return controllable input declarations by dotted path relative to this module."""
        return self._section("_controls", recurse)

    def boundaries(self, recurse=True):
        """Return external boundary declarations by dotted path relative to this module."""
        return self._section("_boundaries", recurse)

    def inputs(self, recurse=True):
        """Return controls followed by boundaries, by dotted path relative to this module."""
        return self.controls(recurse) | self.boundaries(recurse)

    def states(self, recurse=True):
        """Return state declarations by dotted path relative to this module."""
        return self._section("_states", recurse)

    def outputs(self, recurse=True):
        """Return computed output declarations by dotted path relative to this module."""
        return self._section("_outputs", recurse)

    def soft_sensors(self, recurse=True):
        """Return outputs marked as inferred measurements, by dotted path."""
        return {name: value for name, value in self.outputs(recurse).items() if value.soft_sensor}

    def inlets(self):
        """Return this module's own inlet declarations; a child's ports are internal wiring."""
        return dict(self._inlets)

    def outlets(self):
        """Return this module's own outlet declarations; a child's ports are internal wiring."""
        return dict(self._outlets)

    def get(self, path):
        """Return the declaration at a dotted path, whatever its kind."""
        module_path, name = split_path(path)
        declarations = self.get_submodule(module_path)._declarations()
        if name not in declarations:
            raise ValidationError(
                f"{self.path}: unknown name {path!r}; valid: {join_names(declarations)}"
                f"{did_you_mean(name, declarations)}",
                suggestions=close_matches(name, declarations),
                code="unknown_name",
            )
        return declarations[name]

    def _descendant_path(self, module):
        """Return the dotted path of ``module`` below this one, or ``None`` outside the tree."""
        return next((path for path, item in self.named_modules() if item is module), None)

    def _root(self):
        """Return the module at the top of the tree this module belongs to."""
        module = self
        while module._parent is not None:
            module = module._parent
        return module
