"""One call of a plant: the values of its steps while ``Plant.forward`` goes through them."""

from gemini._utils.mappings import get_nested
from gemini._utils.strings import split_path
from gemini.plants._utils import delays, loops, targets
from gemini.plants._utils.plan import Loop, Solve


class Call:
    """The results of one plant call so far, and how to call the next step."""

    def __init__(self, plant, inputs, inlets, state, plan):
        """Start the call of ``plant`` on ``inputs`` and ``inlets`` from ``state``, by ``plan``."""
        self.plant = plant
        self.inputs = inputs
        self.inlets = inlets
        self.state = state
        self.plan = plan
        self.nodes = plan.nodes
        self.results = {}
        self.offers = {}
        self.tears = {}
        self.overrides = {}

    def value(self, source):
        """Return what a source of ``Step.arguments`` holds now."""
        kind = source[0]
        if kind == "many":
            return [self.value(item) for item in source[1]]
        if kind == "inlet":
            return self.inlets[source[1]]
        if kind == "delayed":
            return delays.read(self, source[1])
        if kind == "tear":
            return self.tears[source[1]]
        if kind == "offer":
            return self.offers[source[1]][source[2]]
        if kind == "drawn":
            return self.results[source[1]].inlets[source[2]]
        return self.results[source[1]].outlets[source[2]]

    def outlet(self, end):
        """Return the value of the outlet ``end``, ``(path, port)``, in the last call."""
        return self.results[end[0]].outlets[end[1]]

    def _is_known(self, source):
        kind = source[0]
        if kind == "offer":
            return source[1] in self.offers
        return kind == "inlet" or (kind == "step" and source[1] in self.results)

    def known_arguments(self, step):
        """Return the arguments of ``step`` that exist already: what comes from outside a loop."""
        return {
            port: self.value(source)
            for port, source in step.arguments.items()
            if self._is_known(source)
        }

    def call(self, step, trial=False):
        """Call one step; a trial is recorded by no running call."""
        arguments = {port: self.value(source) for port, source in step.arguments.items()}
        state = get_nested(self.state, tuple(step.path.split(".")))
        if step.offer:
            self.offers[step.path] = step.module._offered(arguments, state)
            return
        arguments |= self.overrides.get(step.path, {})
        if step.path in self.plan.stateful:
            arguments["state"] = state
        call = step.module._trial if trial else step.module
        self.results[step.path] = call(**arguments)

    def execute(self, item):
        """Call one item of the plan: a step, a loop or a constraint."""
        if isinstance(item, Loop):
            loops.close(self, item)
        elif isinstance(item, Solve):
            targets.solve(self, item)
        else:
            self.call(item)

    def read(self, path):
        """Return the value at a dotted path, an output or a port field of a step or a declaration.

        ``riser.bottomhole_pressure`` is an output, ``riser.wellhead_out.p`` a field of a port, and
        what names no step is a parameter, control or boundary of the plant or of a child.
        """
        owner, name = split_path(path)
        if owner in self.results:
            return self.results[owner].outputs[name]
        step, port = split_path(owner)
        if step in self.results:
            result = self.results[step]
            ports = result.outlets if port in result.outlets else result.inlets
            return getattr(ports[port], name)
        if step in self.nodes and port in self.plan_arguments(step):
            return getattr(self.value(self.plan_arguments(step)[port]), name)
        module = self.plant.get_submodule(owner)
        if module is self.plant and name in self.inputs:
            return self.inputs[name]
        if name in module._controls or name in module._boundaries:
            return module._input_value(name)
        return getattr(module, name)

    def plan_arguments(self, path):
        """Return the arguments of the step at ``path``."""
        return self.plan.arguments[path]
