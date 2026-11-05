"""Generate synthetic heating and cooling demand profiles.

Creates 365-day daily mean demand time series for heating (MWth) and
cooling (MWcool) representative of a Northern European district energy
system.  These are PLACEHOLDER profiles — replace with the official
challenge CSVs when available.

Output
------
heating_demand.csv : Day (1-365), Heating_MW
cooling_demand.csv : Day (1-365), Cooling_MW
"""

import numpy as np
import pandas as pd

np.random.seed(42)

days = np.arange(1, 366)

# --- Heating demand: sinusoidal seasonal profile ---
# Peak ~28 MW in winter (day ~15 = mid-Jan), minimum ~2 MW in summer
heating_base = 15.0 + 13.0 * np.cos(2 * np.pi * (days - 15) / 365)
heating_noise = np.random.normal(0, 1.0, 365)
heating = np.clip(heating_base + heating_noise, 0.5, 30.0)

# --- Cooling demand: inverse seasonal profile ---
# Peak ~8 MW in summer (day ~195 = mid-Jul), near zero in winter
cooling_base = 4.0 - 4.0 * np.cos(2 * np.pi * (days - 15) / 365)
cooling_noise = np.random.normal(0, 0.3, 365)
cooling = np.clip(cooling_base + cooling_noise, 0.0, 10.0)

df_heat = pd.DataFrame({"Day": days, "Heating_MW": np.round(heating, 3)})
df_cool = pd.DataFrame({"Day": days, "Cooling_MW": np.round(cooling, 3)})

df_heat.to_csv("heating_demand.csv", index=False)
df_cool.to_csv("cooling_demand.csv", index=False)

print(f"Heating: peak={heating.max():.1f} MW, min={heating.min():.1f} MW, annual={heating.sum():.0f} MWh-day")
print(f"Cooling: peak={cooling.max():.1f} MW, min={cooling.min():.1f} MW, annual={cooling.sum():.0f} MWh-day")
print("Written: heating_demand.csv, cooling_demand.csv")
