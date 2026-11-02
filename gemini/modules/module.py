"""Equipment modules: declarations and children registered in ``__init__``, called with inlets.

A module registers what ``__init__`` assigns: ``Parameter``, ``Inlet``, ``Control``, ``Boundary``,
``State``, ``Output`` and ``Outlet`` declarations go to ordered registries and ``Module`` values
become children with dotted paths. A module is written as two pure methods:
``forward(self, inputs, inlets, state) -> (outputs, outlets)`` and, if it has states,
``update(self, inputs, inlets, outlets, state, dt) -> state``. They write nothing to ``self``, which
holds the parameters only. Calling a module validates the inlets, resolves the controls and
boundaries into ``inputs``, runs the forward pre-hooks, ``forward``, the check of the returned keys
and the forward hooks, then returns a ``ModuleResult``.

The values of one call live in a ``CallRecord`` (``gemini.modules.callrecord``), the only per-call
state. The parts of a module that are separate jobs are in their own files: the arguments of a call
(``callargs``), the state tree and the step (``states``), the display (``display``), the path of a
class (``classpath``).
"""

import inspect
from collections.abc import Mapping
from copy import deepcopy

from pydantic_core import to_jsonable_python

from gemini import ops
from gemini._utils.hooks import RemovableHandle, has_signature
from gemini._utils.registry import register
from gemini._utils.strings import (
    did_you_mean,
    first_paragraph,
    join_names,
    join_path,
    snake_case,
)
from gemini.errors import DefinitionError, ValidationError
from gemini.errors.lookup import UnknownMember
from gemini.modules.bindings import DatedParams
from gemini.modules.callargs import CallArguments
from gemini.modules.callrecord import (
    CallRecord,
    ScalarParameters,
    active_call,
    current_call,
    has_arrays,
    in_trial,
    no_outputs,
    numpy_ports,
    output_rows,
    outputs_enabled,
    plain_outlet,
    recorded_output,
    restored,
    row_output,
    scalar_output,
)
from gemini.modules.declarations import (
    UNSET,
    Boundary,
    Control,
    Declaration,
    Inlet,
    Outlet,
    Output,
    Parameter,
    State,
)
from gemini.modules.display import describe, display
from gemini.modules.results import ModuleResult
from gemini.modules.states import Stateful
from gemini.modules.tree import ModuleTree
from gemini.modules.values import ModuleValues
from gemini.ops import kernels
from gemini.streams.fluid import Fluid
from gemini.streams.ports import Ports
from gemini.units import bare

_REGISTRIES = (
    (Parameter, "_parameters"),
    (Inlet, "_inlets"),
    (Control, "_controls"),
    (Boundary, "_boundaries"),
    (State, "_states"),
    (Output, "_outputs"),
    (Outlet, "_outlets"),
)


def _describe_unknown_member(name, module):
    """Name the module path and the closest child, declaration or port for a missing attribute.

    Reads only the instance dictionary, so it also works before ``super().__init__()``.
    """
    registries = module.__dict__
    candidates = list(registries.get("_children", ()))
    for _, registry in _REGISTRIES:
        candidates.extend(registries.get(registry, ()))
    path = registries.get("_path") or module.name
    return f"{path}: unknown member {name!r}{did_you_mean(name, candidates)}"


class _FolderCategory:
    """The ``category`` of a class: the folder of the package that holds its file.

    ``gemini/modules/pumps/esp.py`` gives ``pumps`` and ``gemini/plants/doublet.py`` gives
    ``plants``, so a shipped class never declares it. A class from outside has no such folder and
    is ``None`` until it assigns ``category`` itself, which replaces this descriptor; a subclass of
    a shipped class states its own too.
    """

    def __get__(self, instance, owner):
        """Return the folder of ``owner``, or ``None`` for a file outside the folders."""
        if owner.__module__.startswith("gemini.plants."):
            return "plants"
        if not owner.__module__.startswith(f"{__package__}."):
            return None
        folder, _, file = owner.__module__.removeprefix(f"{__package__}.").partition(".")
        return folder if file and not folder.startswith("_") else None


class Module(ModuleTree, ModuleValues, CallArguments, Stateful):
    """Base class discovering declarations and child modules assigned in ``__init__``.

    Subclasses call ``super().__init__()`` first, then assign declarations and children in the
    documented section order. ``name`` is the snake_case class name; ``path`` is the dotted
    position in the tree, or the name for a standalone module; ``category`` is the folder of the
    class.
    """

    repr_fields = ()
    offer_inlets = ()
    operating_limits = ()
    """``(output name, side, parameter name)`` of each limit; side is ``"min"`` or ``"max"``."""
    plant_role = None
    """The role this class alone gives in a plant, or ``None``; see ``plants.roles()``."""
    _derived_params = frozenset()
    category = _FolderCategory()
    abstract = True

    def __init_subclass__(cls, **kwargs):
        """Register a class that has a category, unless its own body says ``abstract = True``."""
        super().__init_subclass__(**kwargs)
        if cls.category is not None and not cls.__dict__.get("abstract", False):
            register(cls)

    def __init__(self):
        """Create the ordered registries and the run-owned metadata."""
        for _, registry in _REGISTRIES:
            object.__setattr__(self, registry, {})
        object.__setattr__(self, "_children", {})
        object.__setattr__(self, "_pre_hooks", {})
        object.__setattr__(self, "_hooks", {})
        object.__setattr__(self, "_input_values", {})
        object.__setattr__(self, "_path", "")
        object.__setattr__(self, "_parent", None)
        object.__setattr__(self, "_fluid", None)
        object.__setattr__(self, "bindings", {})
        object.__setattr__(self, "boundary", {})
        object.__setattr__(self, "_param_history", [DatedParams(params={})])
        object.__setattr__(self, "_param_overrides", {})

    @property
    def name(self):
        """Return the snake_case class name, for example ``heat_exchanger``."""
        return snake_case(type(self).__name__)

    @property
    def _type_label(self):
        """Return the name ``repr`` shows for this module."""
        return type(self).__name__

    @property
    def path(self):
        """Return the assigned tree path or standalone derived name."""
        return self._path or self.name

    @property
    def fluid(self):
        """Return the fluid this module's streams carry; ``missing_value`` while none is set.

        The fluid is a case input (``site.fluid``) or an entry of the plant's ``fluids``.
        """
        if self._fluid is None:
            raise ValidationError(
                f"{self.path}.fluid: no value; expected a fluid from the case (site.fluid) "
                "or the plant's fluids",
                code="missing_value",
            )
        return self._fluid

    @fluid.setter
    def fluid(self, value):
        """Set and validate the module fluid; ``state_dict`` saves it.

        Assignment is an author-level tool, so a mapping holds SI numbers, as ``state_dict`` saves.
        """
        self._set_own_fluid(value)

    def _set_own_fluid(self, value):
        """Set the fluid of this module alone."""
        object.__setattr__(self, "_fluid", Fluid._of(value))

    def __setattr__(self, name, value):
        """Register declarations and children, or assign declared values.

        Assigning a declared value from outside a call, ``esp.frequency = Quantity(50, "Hz")``,
        takes a quantity or its dict: a bare number for a value with a dimension is
        ``invalid_value``. Inside a call the value is SI, as in ``forward``; ``gemini`` assigns SI
        values outside a call with ``_assign_si``.
        """
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        if "_parameters" not in self.__dict__:
            if isinstance(value, (Declaration, Module)):
                raise DefinitionError(
                    f"{type(self).__name__}.__init__ must call super().__init__() before "
                    f"assigning {name!r}"
                )
            object.__setattr__(self, name, value)
            return
        if isinstance(value, Declaration):
            self._register_declaration(name, value)
        elif isinstance(value, Module):
            self._add_module(name, value)
        else:
            self._assign_value(name, value)

    def _register_declaration(self, name, declaration):
        existing = self._declarations().get(name)
        if existing is not None and existing is not declaration:
            raise DefinitionError(f"{self.path}.{name}: declaration is already registered")
        registry = next(
            getattr(self, registry)
            for kind, registry in _REGISTRIES
            if isinstance(declaration, kind)
        )
        if isinstance(declaration, State) and declaration.default is not UNSET:
            raise DefinitionError(f"{self.path}.{name}: a state has no default")
        declaration.prime_default()
        registry[name] = declaration.bind(self, name)
        if isinstance(declaration, Parameter) and declaration.initialized:
            initial = self._param_history[0].params
            initial[name] = to_jsonable_python(deepcopy(declaration.value))

    def _assign_value(self, name, value):
        declaration = (
            self._parameters.get(name) or self._controls.get(name) or self._boundaries.get(name)
        )
        if declaration is not None and active_call(self) is None:
            bare.refuse(f"{self.path}.{name}", value, declaration.unit, declaration.quantity)
        self._assign_si(name, value)

    def _assign_si(self, name, value):
        """Assign ``value`` to the declaration or attribute ``name``; a number is SI."""
        if name in self._parameters:
            self._parameters[name].owner._set_parameter(name, value)
            return
        inputs = self._controls | self._boundaries
        if name in inputs:
            self._refuse_in_call(name, "a control or boundary is assigned before a run")
            self._set_input(name, inputs[name].validate(value))
            return
        if name in self._outputs:
            self._refuse_in_call(name, "an output is returned by forward, never assigned", True)
            self._record_output(name, value)
            return
        if name in self._states:
            raise DefinitionError(f"{self.path}.{name}: a state changes only in update")
        if name in self._declarations():
            raise DefinitionError(f"{self.path}.{name}: cannot replace a declaration")
        self._children.pop(name, None)
        object.__setattr__(self, name, value)

    def _refuse_in_call(self, name, reason, always=False):
        """Refuse an assignment a converted module makes in a call, or one of an output outside."""
        if always or active_call(self) is not None:
            raise DefinitionError(f"{self.path}.{name}: {reason}")

    def _set_input(self, name, value):
        call = active_call(self)
        target = call.inputs if call is not None else self._input_values
        target[name] = value

    def _record_output(self, name, value):
        call = active_call(self)
        if call is None:
            raise DefinitionError(f"{self.path}.{name}: outputs may only be assigned in forward")
        if call.trace is not None or not call.recording:
            call.outputs[name] = value
            return
        declaration = self._outputs[name]
        rows = output_rows(value)
        if rows is not None:
            for item in rows:
                declaration.validate(row_output(declaration, item))
            call.outputs[name] = value
            return
        call.outputs[name] = declaration.validate(scalar_output(declaration, value))

    def _add_module(self, name, module):
        """Register an immediate child and reject ambiguous names or ownership cycles."""
        if not isinstance(module, Module):
            raise DefinitionError(f"{self.path}.{name}: child must be a Module")
        if not name or "." in name or name.startswith("_"):
            raise DefinitionError(f"{self.path}: invalid child name {name!r}")
        if name in self._declarations():
            raise DefinitionError(f"{self.path}: child name {name!r} conflicts with a declaration")
        if hasattr(type(self), name):
            raise DefinitionError(f"{self.path}: child name {name!r} shadows a module attribute")
        if any(item is self for item in module.modules()):
            raise DefinitionError(f"{self.path}.{name}: module ownership cannot contain a cycle")
        self._children[name] = module
        object.__setattr__(self, name, module)
        object.__setattr__(module, "_parent", self)
        module._set_path(join_path(self._path, name))

    def _set_path(self, path):
        object.__setattr__(self, "_path", path)
        for declaration in self._declarations().values():
            declaration.bind(self, declaration.name)
        for name, child in self.named_children():
            child._set_path(join_path(path, name))

    def _declarations(self):
        result = {}
        for _, registry in _REGISTRIES:
            result.update(getattr(self, registry))
        return result

    def __getattr__(self, name):
        """Resolve parameter values, current input and output values and port declarations.

        Called only for names that are not ordinary attributes. Controls and boundaries resolve
        to the value of the running call, then the persisted value, then the declared default.
        States resolve to the value at the start of the running step, else the initial state.
        Outputs resolve to the value recorded in the running call, otherwise to their
        declaration, as do inlets and outlets.
        """
        registries = self.__dict__
        if name in registries.get("_parameters", {}):
            call = active_call(self)
            if call is not None and call.parameters is not None:
                return call.parameters[name]
            return self._parameter_value(name)
        if name in registries.get("_controls", {}) or name in registries.get("_boundaries", {}):
            self._refuse_read(name, "forward and update take a control or boundary from inputs")
            return self._input_value(name)
        if name in registries.get("_states", {}):
            raise DefinitionError(f"{self.path}.{name}: forward and update take a state from state")
        if name in registries.get("_outputs", {}):
            call = active_call(self)
            if call is not None and name in call.outputs:
                self._refuse_read(name, "an output is a local value of forward, not read from self")
                return recorded_output(call, call.outputs[name])
            return self._outputs[name]
        for registry in ("_inlets", "_outlets"):
            if name in registries.get(registry, {}):
                return registries[registry][name]
        raise UnknownMember(name, self, _describe_unknown_member)

    def _refuse_read(self, name, reason):
        """Refuse a read of a control, boundary or output from self inside a call."""
        if active_call(self) is not None:
            raise DefinitionError(f"{self.path}.{name}: {reason}")

    def _parameter_value(self, name):
        parameter = self._parameters[name]
        if not parameter.initialized:
            root = self._root()
            raise root._missing_error(root._missing_paths())
        return parameter.value

    def _input_value(self, name):
        call = active_call(self)
        if call is not None and name in call.inputs:
            return call.inputs[name]
        if name in self._input_values:
            return self._input_values[name]
        declaration = (self._controls | self._boundaries)[name]
        if declaration.default is not UNSET:
            return declaration.default_value()
        raise ValidationError(
            f"{declaration.path}: {declaration.section} {name!r} has no value "
            f"[{declaration.unit or '-'}]",
            code="missing_value",
        )

    def forward(self, inputs, inlets, state):
        """Return ``(outputs, outlets)`` of one step; subclasses implement this.

        Pure: it writes nothing to ``self``, which holds the parameters only. ``inputs`` are the
        controls and boundaries of the call by name, ``inlets`` its ports and ``state`` the
        states the step starts from. ``outputs`` has a key for each declared output and
        ``outlets`` one for each outlet the module gives and each inlet it draws, no more and no
        fewer.
        """
        raise NotImplementedError(f"{type(self).__name__} has no forward method")

    def _offer(self, inputs, inlets, state):
        """Return the ``offered`` outlets; a module that declares one overrides this.

        It runs before the other modules and reads only controls, boundaries, parameters and
        the inlets named in ``offer_inlets``.
        """
        raise NotImplementedError(f"{type(self).__name__} offers nothing")

    def _offer_values(self, call, inlets):
        """Return what ``_offer`` gives in the running ``call``, the one way to ask for it."""
        return self._offer(call.inputs, inlets, call.state)

    def _offered(self, inlets=None, state=None):
        """Return the values of the ``offered`` outlets, for a plant to pass on before they run.

        ``state`` is the state tree of the call the offer belongs to.
        """
        self._prepare()
        parent = current_call.get()
        ports = Ports(inlets or {}, path=self.path)
        if parent is not None and parent.trace is not None:
            return parent.trace.offer(self, ports, parent)
        with ops.scope.Scope(self._scalar_mode(), has_arrays(ports, {})) as scope:
            call = self._eager_call(
                self._resolve_inputs({}), parent, self._call_state(state), scope.wrapping
            )
            token = current_call.set(call)
            try:
                offered = self._offer_values(call, numpy_ports(ports) if scope.wrapping else ports)
            finally:
                current_call.reset(token)
        return {name: plain_outlet(value) for name, value in offered.items()}

    def __call__(self, *args, **kwargs):
        """Apply controls and boundaries, run hooks and ``forward``, and validate outlets.

        A stateful module, and a plant with one below it, takes the keyword ``state``: its state
        tree. The result holds the state the call started from.
        """
        state = kwargs.pop("state", None)
        return self._run(args, kwargs, state)

    def _run(self, args, kwargs, state):
        """Evaluate one call from the state tree ``state``."""
        self._prepare()
        parent = current_call.get()
        inlets, supplied = self._split_call_args(args, kwargs, state)
        if parent is not None and parent.trace is not None:
            return parent.trace.child(self, inlets, supplied, parent)
        inputs = self._resolve_inputs(supplied)
        own_state = self._call_state(state)
        with ops.scope.Scope(self._scalar_mode(), has_arrays(inlets, inputs)) as scope:
            call = self._eager_call(inputs, parent, own_state, scope.wrapping)
            token = current_call.set(call)
            try:
                scoped = numpy_ports(inlets) if scope.wrapping else inlets
                outlets = self._evaluate(inlets, scoped, call)
            finally:
                current_call.reset(token)
        result = ModuleResult.of(
            self,
            call.kept_outputs(),
            outlets,
            self._settled_inlets(inlets, call),
            ops.scope.plain(dict(call.inputs)),
            call.call_records,
            own_state,
        )
        if parent is not None:
            parent.call_records.append((self._relative_path(parent.module), result))
        return result

    def _eager_call(self, inputs, parent, state, wrapping):
        """Return the call record of an eager call; ``wrapping`` gives physics NumPy scalars.

        Wrapped controls, boundaries, states and (read on demand) parameters are what ``forward``
        sees, so a plain operator on them is silent like the ops; results hold plain values.
        """
        if wrapping:
            inputs = {name: ops.scope.wrap(value) for name, value in inputs.items()}
            state = ops.scope.wrap(state)
        return CallRecord(
            module=self,
            inputs=inputs,
            outputs={},
            recording=outputs_enabled(),
            parent=parent,
            state=state,
            parameters=ScalarParameters(self) if wrapping else None,
            wrapping=wrapping,
        )

    def _scalar_mode(self):
        """Return ``WRAP`` to give physics NumPy scalars in an eager call, else ``PLAIN``.

        NOTE(refactor): the ESP overrides it for float32 precision, whose arithmetic an
        ``np.float64`` scalar would change; no other module does.
        """
        return kernels.WRAP

    def _evaluate(self, inlets, scoped, call):
        """Run pre-hooks, ``forward``, the check of its keys and forward hooks of one call.

        Hooks see the plain ``inlets``; ``forward`` sees ``scoped``.
        """
        state = call.state if call.state is not None else {}
        for hook in tuple(self._pre_hooks.values()):
            self._replace_inputs(call, hook(self, dict(call.inputs), inlets, state))
        outputs, returned = self._forward(scoped, call, state)
        self._check_outlet_names(returned)
        given = {name: returned[name] for name in self._given_outlets()}
        taken = {name: scoped[name] for name in self._drawn_outlets() if name in scoped}
        if call.trace is None:
            outlets = self._check_outlets(restored(given, scoped, inlets), taken)
            call.drawn = self._checked_drawn(returned)
        else:
            outlets = Ports({name: (given | taken)[name] for name in self._outlets}, path=self.path)
            call.drawn = {name: returned[name] for name in self._drawn_inlets()}
        self._record_outputs(outputs, call)
        if call.recording:
            self._output_step(inlets, outlets, call)
        return outlets

    def _forward(self, scoped, call, state):
        """Return ``(outputs, outlets)`` of ``forward`` on the values of ``call``."""
        returned = self.forward(call.inputs, scoped, state)
        try:
            outputs, outlets = returned
        except (TypeError, ValueError) as error:
            raise DefinitionError(f"{self.path}: forward must return (outputs, outlets)") from error
        return outputs, outlets

    def _record_outputs(self, outputs, call):
        """Check the keys of the returned outputs and record them in the call, validated."""
        if not isinstance(outputs, dict):
            raise DefinitionError(f"{self.path}: forward must return (outputs, outlets) as dicts")
        if call.recording:
            expected = list(self._outputs)
            missing = [name for name in expected if name not in outputs]
            extra = [name for name in outputs if name not in expected]
            if missing or extra:
                key = (missing or extra)[0]
                raise DefinitionError(
                    f"{self.path}: forward returned the outputs {sorted(outputs)}; "
                    f"{'missing' if missing else 'extra'} key {key!r}; "
                    f"valid names: {join_names(expected)}"
                )
        for name, value in outputs.items():
            self._record_output(name, value)

    def _replace_inputs(self, call, replaced):
        """Replace controls and boundaries of ``call`` by what a pre-hook returned."""
        if replaced is None:
            return
        if not isinstance(replaced, Mapping):
            raise DefinitionError(
                f"{self.path}: a forward pre-hook returns None or a mapping of controls and "
                f"boundaries, got {type(replaced).__name__}"
            )
        declared = self._controls | self._boundaries
        for name, value in replaced.items():
            if name not in declared:
                raise DefinitionError(
                    f"{self.path}: pre-hook returned {name!r}; valid names: {join_names(declared)}"
                )
            call.inputs[name] = declared[name].validate(value)

    def _output_step(self, inlets, outlets, call):
        """Finish the outputs after ``forward``, the one sequence of an eager and a traced call.

        Forward hooks see the plain ``inlets``; a mapping a hook returns replaces outputs. In a
        trace the hook goes through ``call.trace``, which tells whether it writes an output.
        """
        state = call.state if call.state is not None else {}
        for hook in tuple(self._hooks.values()):
            arguments = (self, dict(call.inputs), inlets, state, dict(call.outputs), outlets)
            if call.trace is None:
                replaced = hook(*arguments)
            else:
                replaced = call.trace.hook(self, hook, arguments, call)
            if replaced is not None and not isinstance(replaced, Mapping):
                raise DefinitionError(
                    f"{self.path}: a forward hook returns None or a mapping of outputs, "
                    f"got {type(replaced).__name__}"
                )
            for name, value in (replaced or {}).items():
                if name not in self._outputs:
                    raise DefinitionError(
                        f"{self.path}: forward hook returned {name!r}; "
                        f"valid outputs: {join_names(self._outputs)}"
                    )
                self._record_output(name, value)
        self._check_outputs(call.outputs)

    def _relative_path(self, owner):
        prefix = owner._path + "." if owner._path else ""
        return self._path.removeprefix(prefix) or self.name

    def _check_outputs(self, recorded):
        missing = sorted(self._outputs.keys() - recorded.keys())
        if missing:
            raise DefinitionError(f"{self.path}: outputs left unassigned: {missing}")

    def _trial(self, *args, **kwargs):
        """Return the result of one call that no running call records, outputs not validated.

        A plant that closes a loop or solves a constraint evaluates trial passes with it, then
        calls each module once with the converged inlets, so its outputs and balances see only
        that call. Pre-hooks run and forward hooks do not. A stateful module would evaluate at its
        initial states, so it is refused.
        """
        if self.stateful:
            raise ValidationError(
                f"{self.path}: stateful = True; expected a stateless module for a trial call",
                code="invalid_design",
            )
        token, trial = current_call.set(None), in_trial.set(True)
        try:
            with no_outputs():
                return self(*args, **kwargs)
        finally:
            in_trial.reset(trial)
            current_call.reset(token)

    def _offers(self):
        """Return whether the ``offered`` outlets exist as this module is set; some may not."""
        return True

    def _loop_start(self, inputs, port, entering):
        """Return the first guess [K] of the temperature on outlet ``port`` of a closed loop.

        ``inputs`` are the controls and boundaries of this module and ``entering`` lists the streams
        that reach it from outside the loop. A module that can guess overrides this; the plan then
        prefers to tear that outlet.
        """
        return None

    def _loop_limits(self, inlets):
        """Return the ``(lower, upper)`` temperatures [K] a loop through this module must keep.

        ``inlets`` are the inlets that come from outside the loop. ``None`` is no limit.
        """
        return None, None

    def _iterates(self):
        """Return whether a call of this module closes a loop or solves a constraint."""
        return False

    def register_forward_pre_hook(self, fn):
        """Call ``fn(module, inputs, inlets, state)`` before each forward evaluation.

        A mapping the hook returns replaces those controls and boundaries for the call; the
        hook changes nothing else.
        """
        self._check_hook_signature(fn, ("module", "inputs", "inlets", "state"), "forward pre-hook")
        return RemovableHandle(self._pre_hooks, fn)

    def register_forward_hook(self, fn):
        """Call ``fn(module, inputs, inlets, state, outputs, outlets)`` after ``forward``.

        A mapping the hook returns replaces those outputs of the call; the hook changes nothing
        else.
        """
        self._check_hook_signature(
            fn, ("module", "inputs", "inlets", "state", "outputs", "outlets"), "forward hook"
        )
        return RemovableHandle(self._hooks, fn)

    def _check_hook_signature(self, fn, expected, kind):
        if not has_signature(fn, expected):
            actual = tuple(inspect.signature(fn).parameters)
            raise DefinitionError(
                f"{self.path}: {kind} signature must be ({', '.join(expected)}); "
                f"got ({', '.join(actual)})"
            )

    def health(self, result, measured):
        """Compare one call's ``ModuleResult`` with measured outputs; ``None`` means not assessed.

        Equipment with a diagnostic model overrides this; the engine calls it after each replayed
        twin with the bound measurements of that tick.
        """
        return None

    def _extra_repr(self):
        """Display up to four initialized scalar parameters."""
        parts = []
        for name in self.repr_fields or tuple(self._parameters):
            parameter = self._parameters.get(name)
            if parameter is None or not parameter.initialized:
                continue
            value = parameter.value
            if isinstance(value, (dict, list, tuple)) or value is None:
                continue
            parts.append(f"{name}={display(value, parameter.unit or '', parameter.quantity)}")
            if len(parts) == 4:
                break
        return ", ".join(parts)

    def __repr__(self):
        """Render a compact recursive module tree."""
        extra = self._extra_repr()
        if not self._children:
            return f"{self._type_label}({extra})"
        rows = [f"{self._type_label}({extra}"]
        for name, child in self.named_children():
            rows.append("  (" + name + "): " + repr(child).replace("\n", "\n  "))
        return "\n".join(rows + [")"])

    @classmethod
    def help(cls):
        """Return the class description and its declarations for interactive use."""
        lines = [first_paragraph(inspect.getdoc(cls) or cls.__name__)]
        module = cls()
        for title, registry in (
            ("Parameters", module._parameters),
            ("Inlets", module._inlets),
            ("Controls", module._controls),
            ("Boundaries", module._boundaries),
            ("States", module._states),
            ("Outputs", module._outputs),
            ("Outlets", module._outlets),
        ):
            if registry:
                lines.append(f"\n{title}:")
                lines.extend(f"  {name}: {describe(value)}" for name, value in registry.items())
        return "\n".join(lines)
