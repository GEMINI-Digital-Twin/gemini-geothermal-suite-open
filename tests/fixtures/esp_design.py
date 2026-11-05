"""The ESP values that were defaults before they became a design decision."""

ESP_DESIGN = {
    "esp.pump_type": "unspecified",
    "esp.motor_efficiency": 1.0,
    "esp.minimum_flow": {"value": 0, "unit": "m3/s"},
    "esp.maximum_flow": {"value": 1, "unit": "m3/s"},
    "esp.best_efficiency_flow": {"value": 0.04, "unit": "m3/s"},
    "esp.drift_threshold": 0.1,
    "esp.correction_factors": [1.0, 0.0],
}
"""What a designed doublet leaves to its plant, under ``esp.``: no flow window, 0.04 m3/s best flow.

The setting depth is not here: the design derives it.
"""

ESP_MODULE = {name.removeprefix("esp."): value for name, value in ESP_DESIGN.items()} | {
    "setting_depth": {"value": 0, "unit": "m"}
}
"""The same values for an ESP set on its own, with the setting depth it had by default."""


ESP_PARAMS = ESP_MODULE | {
    "pump_type": "HC27000",
    "stage_count": 12,
    "head_coefficients": [
        83.08389282,
        -0.000460444,
        -1.19e-07,
        1.69e-11,
        -6.36e-16,
        6.69e-21,
    ],
    "power_coefficients": [
        10.02089977,
        -0.000160233,
        6.52e-08,
        -2.13e-12,
        1.71e-17,
        1.38e-23,
    ],
}
"""An ESP set on its own that runs: the design values and the curves of a HC27000 pump."""
