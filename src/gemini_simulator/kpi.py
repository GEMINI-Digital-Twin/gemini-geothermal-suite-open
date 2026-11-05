"""KPI helpers for doublet plant projects.

Provides plant-level post-processing for secondary outlet temperature,
thermal/electrical power balance, and emissions.

These functions are deliberately *not* wired as component outputs inside
the solver's connection graph, which keeps them free of the solver's own
per-timestep wiring/ordering concerns: each one only needs a solved
:class:`~gemini_simulator.solver.Solver` (or the handful of scalar
outputs read from it) plus the same-shape scalar values (flow rates,
valve fractions) used to build the project.

That said, this module is **not** topology-agnostic: it hardcodes the
specific component names used by
``simulator_examples/projects/doublet_plant.json`` (``"water_mixer"``,
``"filter_a"``, ``"heat_exchanger"``, ``"boiler"``, ``"chp"``). It only
works out of the box for a project built with exactly that layout (a
single heat exchanger + boiler/CHP secondary split, recombined by a
``water_mixer``). Other example projects with a different topology --
e.g. ``simulator_examples/projects/parallel_hex_plant.json`` (three
parallel heat exchangers named ``hex_1``/``hex_2``/``hex_3``, a
``hex_mixer``, no boiler/CHP at all) -- do **not** use this module; see
``simulator_examples/run_parallel_hex_plant_example.py``, which reads
its own KPIs directly off the solver instead. Adapting these helpers to
a new topology means either renaming your project's components to
match, or copying/adjusting the functions below for your own component
names.

Units at the KPI layer follow the project file's own convention (bar,
degC, m3/h were used for parameters; here power/emission outputs are SI:
Watt and kg/s) -- convert to e.g. MW / kg per day at the call site as
needed.
"""

FLUID_DENSITY = 1050.0  # kg/m3, default water density used in KPI heat-flow calculations
SPECIFIC_HEAT = 4200.0  # J/(kg.K), default water specific heat used in KPI heat-flow calculations
JOULE_PER_KWH = 3.6e6  # J per kWh, used to convert electricity emission factors (kg/kWh) to kg/J


def secondary_outlet_temperature(solver):
    """Return the combined secondary-network outlet temperature (degC).

    Reads the flow-weighted mix of the boiler's and CHP's water outlets
    directly from the project's ``water_mixer`` component (a
    :class:`~gemini_model.mixer.mixer.Mixer`), which already combines
    their outlet flows/temperatures using a mass-weighted average.

    Parameters
    ----------
    solver: gemini_simulator.solver.Solver
        A solver that has been ``.run()`` and includes a ``"water_mixer"``
        component recombining ``"boiler"`` and ``"chp"``'s water outlets
        (e.g. built via :func:`gemini_simulator.project_loader.load_project`
        from a project JSON file such as
        ``simulator_examples/projects/doublet_plant.json``).
    """
    return solver.get_output("water_mixer", "temperature")


def plant_thermal_power_w(solver, secondary_flow_m3s, secondary_temperature_in):
    """Return the net thermal power delivered by the secondary network (W).

    ``Q_s * rho * Cw * (T_s_out - T_s_in)``.
    """
    t_s_out = secondary_outlet_temperature(solver)
    return secondary_flow_m3s * FLUID_DENSITY * SPECIFIC_HEAT * (t_s_out - secondary_temperature_in)


def doublet_thermal_power_w(solver, primary_flow_m3s):
    """Return the thermal power extracted from the primary (doublet) flow.

    Computed across the heat exchanger (W):
    ``Q * rho * Cw * (T_filterA_out - T_hex_primary_out)``.
    """
    t_in = solver.get_output("filter_a", "temperature_out")
    t_out = solver.get_output("heat_exchanger", "primary_temperature_out")
    return primary_flow_m3s * FLUID_DENSITY * SPECIFIC_HEAT * (t_in - t_out)


def electricity_surplus_w(solver, esp_power_w=0.0, injector_pump_power_w=0.0):
    """Return the net *electrical* power balance of the plant (W).

    CHP generation minus ESP and injector pump consumption (excludes the
    secondary network's thermal power): ``E_CHP - E_ESP -
    E_InjectorPump``. ``esp_power_w``/``injector_pump_power_w`` are
    computed separately (e.g. from
    ``gemini_simulator.well_flow.producer_esp_power_w`` and
    ``gemini_model.injector_pump.injector_pump.InjectorPump``), since the
    well/reservoir network is not part of the surface-chain solver here.
    """
    chp_power_el = solver.get_output("chp", "power_el")
    return chp_power_el - esp_power_w - injector_pump_power_w


# Kept as an alias for any earlier callers; prefer electricity_surplus_w.
net_electrical_power_w = electricity_surplus_w


def power_total_w(power_plant_w, solver, esp_power_w=0.0, injector_pump_power_w=0.0):
    """Return the total plant power balance (W).

    Thermal power delivered by the secondary network, plus CHP
    electricity generated, minus ESP and injector pump electricity
    consumed: ``power_plant - E_ESP - E_InjectorPump + E_CHP``.
    """
    return power_plant_w + electricity_surplus_w(solver, esp_power_w, injector_pump_power_w)


def electrical_emission_kg_s(power_w, electricity_emission_factor_kg_per_kwh):
    """Return the CO2 emission rate (kg/s) of electricity.

    Associated with consuming/generating ``power_w`` (W) of electricity
    at a given emission factor (kg/kWh).
    """
    return electricity_emission_factor_kg_per_kwh / JOULE_PER_KWH * power_w


def esp_emission_kg_s(esp_power_w, chp_power_el_w, electricity_emission_factor_kg_per_kwh):
    """Return the CO2 emission rate (kg/s) of the ESP's electricity use.

    Net of on-site CHP generation used to offset it first:
    ``factor / 3.6E6 * (E_ESP - min(E_CHP, E_ESP))`` -- i.e. only the
    portion of the ESP's power draw *not* already covered by the CHP's
    own electricity generation is charged an emission (grid draw is
    assumed for that portion; onsite CHP generation is assumed
    emission-free here, since the CHP's gas emission is already
    accounted for separately via the CHP component's own emission output).
    """
    grid_power_w = max(0.0, esp_power_w - min(chp_power_el_w, esp_power_w))
    return electrical_emission_kg_s(grid_power_w, electricity_emission_factor_kg_per_kwh)


def total_emission_kg_s(solver, esp_emission_kg_s=0.0, injector_pump_emission_kg_s=0.0):
    """Return the total CO2 emission rate (kg/s).

    Boiler + CHP (gas) plus ESP and injector pump (electricity).
    """
    return (
        solver.get_output("boiler", "emission")
        + solver.get_output("chp", "emission")
        + esp_emission_kg_s
        + injector_pump_emission_kg_s
    )
