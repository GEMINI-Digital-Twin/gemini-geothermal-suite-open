"""Compare well pipe size and roughness for one doublet at fixed flows.

Uses GEMINI's well model with the challenge brine and the required 70% pump
efficiency. The flow is chosen and the required pumping is calculated, so the
demo ESP curve is not used.

Run from the project folder:
    PYTHONPATH=../src python cases/pipe_size_study.py
"""

from gemini_simulator.well_flow import _build_dpdt, _split_trajectory_at_depth

DEPTH_M = 2500.0
ESP_DEPTH_M = 650.0
RESERVOIR_PRESSURE_BAR = 250.0
INDEX_M3H_PER_BAR = 13.4  # Darcy estimate, see baseline_challenge.json
WELLHEAD_PRESSURE_BAR = 3.0
INJECTOR_INLET_PRESSURE_BAR = 1.45  # surface pressure in GEMINI's example
PUMP_EFFICIENCY = 0.7
TEMPERATURE_K = 333.15
RHO = 1030.0
VISCOSITY = 0.40e-3
CP = 4100.0
MAX_COOLING_C = 40.0

DIAMETERS_M = (0.15, 0.178, 0.20, 0.22, 0.25)
ROUGHNESS_M = (0.01, 0.0001)
FLOWS_M3H = (100.0, 200.0, 300.0)


def build_well(segments, roughness):
    """Return a GEMINI well model using the challenge brine properties."""
    well = _build_dpdt(segments, roughness=roughness)
    well.PVT.update_parameters({"RHOL": RHO, "VISL": VISCOSITY})
    return well


def walk(well, pressure_bar, flow_m3s, direction):
    """Return the pressure (bar) at the far end of a well section."""
    well.calculate_output(
        {
            "pressure": pressure_bar * 1e5,
            "temperature": TEMPERATURE_K,
            "temperature_ambient": TEMPERATURE_K,
            "flowrate": flow_m3s,
            "direction": direction,
        },
        None,
    )
    return well.get_output()["pressure_output"] / 1e5


def evaluate(diameter, roughness, flow_m3h):
    """Return pressures and pump power for one doublet at a fixed flow."""
    flow_m3s = flow_m3h / 3600.0
    segment = {"angle": 90.0, "depth": DEPTH_M, "diameter": diameter}
    top, bottom = _split_trajectory_at_depth([segment], ESP_DEPTH_M)

    bottomhole = RESERVOIR_PRESSURE_BAR - flow_m3h / INDEX_M3H_PER_BAR
    intake = walk(build_well(bottom, roughness), bottomhole, flow_m3s, "up")
    discharge = walk(build_well(top, roughness), WELLHEAD_PRESSURE_BAR, flow_m3s, "down")
    esp_mw = flow_m3s * (discharge - intake) * 1e5 / PUMP_EFFICIENCY / 1e6

    injector = build_well([segment], roughness)
    required_bottomhole = RESERVOIR_PRESSURE_BAR + flow_m3h / INDEX_M3H_PER_BAR
    no_pressure_bottomhole = walk(injector, 0.0, -flow_m3s, "down")
    injector_wellhead = max(0.0, required_bottomhole - no_pressure_bottomhole)
    boost = max(0.0, injector_wellhead - INJECTOR_INLET_PRESSURE_BAR)
    injector_mw = flow_m3s * boost * 1e5 / PUMP_EFFICIENCY / 1e6

    heat_mw = flow_m3s * RHO * CP * MAX_COOLING_C / 1e6
    return {
        "velocity": flow_m3s / (3.14159265 / 4 * diameter**2),
        "intake": intake,
        "esp_boost": discharge - intake,
        "esp_mw": esp_mw,
        "injector_wellhead": injector_wellhead,
        "injector_mw": injector_mw,
        "pump_share": (esp_mw + injector_mw) / heat_mw * 100,
    }


def main():
    """Print the study results as a table."""
    print(
        "ID m   rough mm  flow m3/h  v m/s  intake bar  ESP boost bar  ESP MW  "
        "inj WHP bar  inj MW  pumps % of heat"
    )
    for roughness in ROUGHNESS_M:
        for diameter in DIAMETERS_M:
            for flow in FLOWS_M3H:
                r = evaluate(diameter, roughness, flow)
                print(
                    f"{diameter:5.3f}  {roughness * 1000:7.1f}  {flow:9.0f}  "
                    f"{r['velocity']:5.2f}  {r['intake']:10.1f}  {r['esp_boost']:13.1f}  "
                    f"{r['esp_mw']:6.3f}  {r['injector_wellhead']:11.1f}  "
                    f"{r['injector_mw']:6.3f}  {r['pump_share']:15.1f}"
                )


if __name__ == "__main__":
    main()
