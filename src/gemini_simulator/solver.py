"""Explicit connection-based simulation engine.

Components are plain named objects, connections between them are
declared explicitly and executed in declared order (no topology
inference), and each timestep re-evaluates every connection in sequence.
The component call convention follows ``gemini_model``'s
``calculate_output(u, x)`` signature (explicit input dict and state, no
implicit ``self.input``/``self.output`` mutation), so the ``Solver``
itself owns and maintains the persistent per-component input dict (and
state, for dynamic components) between connection updates.
"""

from gemini_model.model_abstract import DynamicModel


class Solver:
    """Runs a network of gemini_model components wired by explicit connections."""

    def __init__(self, components):
        """Initialize the solver.

        Parameters
        ----------
        components: dict[str, Model]
            Mapping of component name to a gemini_model component instance.
        """
        self.components = components
        self.connections = []  # list of (pred_name, succ_name, pred_output_key, succ_input_key)
        self.inputs = {name: {} for name in components}
        self.states = {name: None for name in components}
        self.history = {name: {"input": [], "output": []} for name in components}

    def connect(self, predecessor, successor, predecessor_output, successor_input):
        """Declare that ``predecessor``'s output feeds one of ``successor``'s inputs.

        Parameters
        ----------
        predecessor, successor: str
            Names of components registered in ``self.components``.
        predecessor_output: str
            Key in the predecessor's output dict to read.
        successor_input: str
            Key in the successor's input dict to write.

        Notes
        -----
        Connections are executed in the order they are declared.
        Consecutive connections that share the same successor are grouped
        together: all of them write their value into the successor's
        input dict first, and the successor's ``calculate_output`` is
        only called once, after the whole group has been applied. This
        means a component with several inputs (e.g. an ``Adder`` or a
        ``HeatExchanger`` needing both ``pressure`` and ``temperature``)
        should have all of its incoming connections listed one after the
        other, so it is only evaluated once it has everything it needs.
        If connections to the same successor are not consecutive (an
        unrelated connection to a different successor is listed in
        between), each group is still evaluated separately in the order
        given -- use :meth:`set_boundary_input` for any input that has no
        predecessor connection at all (e.g. a fixed setpoint).
        """
        for name in (predecessor, successor):
            if name not in self.components:
                raise KeyError(f"Unknown component '{name}'. Register it before connecting.")
        self.connections.append((predecessor, successor, predecessor_output, successor_input))

    def set_boundary_input(self, component, key, value):
        """Set a fixed input value on a component (e.g. a boundary/source component).

        Use this for inputs that are not produced by any other component's
        output (e.g. a Reservoir's ambient temperature, or a fixed control
        setpoint), before calling :meth:`run`.
        """
        if component not in self.components:
            raise KeyError(f"Unknown component '{component}'.")
        self.inputs[component][key] = value

    def run(self, time_vector=None):
        """Run the solver over ``time_vector`` (defaults to a single steady-state step).

        For each timestep, every declared connection is processed in
        order: the predecessor's output is (re)calculated, the named
        output value is copied into the successor's persistent input
        dict, and the successor's output is (re)calculated. Any
        component that never appears in a connection (a "standalone"
        component driven entirely by :meth:`set_boundary_input` values,
        e.g. a unit fed only by fixed setpoints alongside the rest of the
        network) is still evaluated once per timestep from its current
        input dict, so it is not silently skipped. After all connections
        (and any standalone components) for a timestep are processed,
        dynamic components' state is advanced and a snapshot of every
        component's current input/output is recorded in ``self.history``.

        Parameters
        ----------
        time_vector: sequence, optional
            Simulation time points. Defaults to ``[0]`` for a single
            steady-state evaluation.

        Returns
        -------
        dict
            ``self.history``: per-component lists of input/output dict
            snapshots, one entry per timestep.
        """
        if time_vector is None:
            time_vector = [0]

        connected_names = {name for pred, succ, _, _ in self.connections for name in (pred, succ)}
        standalone_names = [name for name in self.components if name not in connected_names]

        for name, component in self.components.items():
            if isinstance(component, DynamicModel):
                self.states[name] = component.initialize_state(self.inputs[name])
            if hasattr(component, "set_time"):
                component.set_time(0)

        for t in time_vector:
            for name, component in self.components.items():
                if hasattr(component, "set_time"):
                    component.set_time(t)

            # Group consecutive connections that share the same successor so
            # the successor is only evaluated once all of them have been
            # applied (see Solver.connect docstring).
            i = 0
            n = len(self.connections)
            while i < n:
                _, succ_name, _, _ = self.connections[i]
                j = i
                while j < n and self.connections[j][1] == succ_name:
                    pred_name, _, out_key, in_key = self.connections[j]
                    predecessor = self.components[pred_name]
                    predecessor.calculate_output(self.inputs[pred_name], self.states[pred_name])
                    self.inputs[succ_name][in_key] = predecessor.output[out_key]
                    j += 1

                successor = self.components[succ_name]
                successor.calculate_output(self.inputs[succ_name], self.states[succ_name])
                i = j

            for name in standalone_names:
                component = self.components[name]
                component.calculate_output(self.inputs[name], self.states[name])

            for name, component in self.components.items():
                if isinstance(component, DynamicModel):
                    self.states[name] = component.update_state(self.inputs[name], self.states[name])
                self.history[name]["input"].append(dict(self.inputs[name]))
                self.history[name]["output"].append(dict(component.output))

        return self.history

    def get_output(self, component, key=None, timestep=-1):
        """Retrieve a recorded output value for a component at a given timestep.

        Parameters
        ----------
        component: str
            Component name.
        key: str, optional
            Output key to retrieve. If omitted, returns the whole output dict.
        timestep: int
            Index into the recorded history (defaults to the last timestep).
        """
        snapshot = self.history[component]["output"][timestep]
        return snapshot if key is None else snapshot[key]
