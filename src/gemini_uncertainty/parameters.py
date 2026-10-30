"""Uncertain parameters: distributions, base values and their public sources.

Every parameter says where it acts (``challenge`` and ``assumptions``
are the ``gemini_design`` dicts, ``demand`` scales a profile, ``cost``
only enters the cost model) and why its range was chosen. Base values are
the distribution's median (normal, lognormal) or mode (triangular), so a
deterministic "sourced base case" is always available next to the
Monte Carlo spread.
"""

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import qmc

# Short citation keys used by PARAMETERS; full references in SOURCES.
SOURCES = {
    "brief": "SPE GeoHackathon 2026 challenge requirements (28 Oct 2026): 200 mD, 30 degC/km, "
    "100 m net reservoir, demand profiles for 2027.",
    "thermogis": "TNO pyThermoGIS documentation, cost model and default economic properties "
    "(well cost = 1.3 x (0.25 MEUR + 700 EUR/m x L + 0.2 EUR/m2 x L^2) per well; "
    "base-case permeability treated log-normally with P90/P50/P10 maps). "
    "https://pythermogis-15909e.ci.tno.nl/theory/utcprops/contents/ and "
    "https://pythermogis-15909e.ci.tno.nl/theory/economicmodel/cost_model/",
    "pbl_sde": "PBL, Eindadvies basisbedragen SDE++ 2025 (publication 5472), tables 3.1-3.2: "
    "geothermal WACC 7.2% nominal / 5.1% real, 2% inflation. "
    "https://www.pbl.nl/publicaties/eindadvies-basisbedragen-sde-2025",
    "tennet_2025": "TenneT, 'Rising electricity prices, increased electricity exports...' "
    "(30 Apr 2026): Dutch day-ahead price averaged EUR 87/MWh in 2025. "
    "https://www.tennet.eu/nl-en/news/rising-electricity-prices-increased-electricity-exports-"
    "and-stable-congestion-management-costs",
    "iea_2026": "IEA, Electricity 2026, Prices chapter: EU wholesale ~USD 95/MWh in 2025, "
    "2027 futures ~USD 85/MWh; EU ETS averaged ~EUR 75/t in 2025. "
    "https://www.iea.org/reports/electricity-2026/prices",
    "reuters_eua": "Reuters analyst poll (10 analysts) via SteelOrbis, 4 Feb 2026: EUA forecast "
    "EUR 92.65/t (2026) and EUR 107.29/t (2027). https://www.steelorbis.com/steel-news/"
    "latest-news/eu-carbon-prices-seen-rising-in-2026-27-volatility-to-persist-1433865.htm",
    "rabobank_ttf": "Rabobank TTF outlook via Tradingpedia, 8 Sep 2026: 2027 base case "
    "EUR 42/MWh, EUR 50-60/MWh in a supply-damage scenario. https://www.tradingpedia.com/"
    "2026/09/08/geopolitical-tensions-anchor-elevated-ttf-natural-gas-prices/",
    "cbs_ef": "CBS, Energie- en emissiefactoren elektriciteit, update 2024 (Dec 2025): "
    "Dutch electricity ~0.20 kg CO2/kWh in 2024 and falling. https://www.cbs.nl/nl-nl/"
    "achtergrond/2025/49/energie-en-emissiefactoren-elektriciteit-update-2024",
    "assumption": "Team engineering assumption (stated so it can be challenged).",
}


@dataclass(frozen=True)
class Parameter:
    """One uncertain input.

    ``dist`` is ``"triangular"`` (args: low, mode, high), ``"normal"``
    (mean, sd, low clip, high clip) or ``"lognormal"`` (median, P10, P90).
    """

    name: str
    label: str
    target: str  # "challenge", "assumptions", "demand" or "cost"
    dist: str
    args: tuple
    unit: str
    source: str
    note: str = ""

    def ppf(self, u):
        """Return the parameter value(s) at cumulative probability ``u``."""
        u = np.clip(np.asarray(u, dtype=float), 1e-9, 1 - 1e-9)
        if self.dist == "triangular":
            low, mode, high = self.args
            c = (mode - low) / (high - low)
            return stats.triang.ppf(u, c, loc=low, scale=high - low)
        if self.dist == "normal":
            mean, sd, low, high = self.args
            a, b = (low - mean) / sd, (high - mean) / sd
            return stats.truncnorm.ppf(u, a, b, loc=mean, scale=sd)
        if self.dist == "lognormal":
            median, p10, p90 = self.args
            sigma = math.log(p90 / p10) / (2 * stats.norm.ppf(0.9))
            return median * np.exp(sigma * stats.norm.ppf(u))
        raise ValueError(f"Unknown distribution '{self.dist}' for {self.name}")

    @property
    def base(self):
        """Return the base (most likely / median) value."""
        if self.dist == "triangular":
            return float(self.args[1])
        return float(self.args[0])

    def describe(self):
        """Return a one-line, unit-bearing description of the distribution."""
        p10, p90 = self.ppf([0.1, 0.9])
        return (
            f"{self.label}: {self.dist}{self.args}, base {self.base:g} {self.unit}, "
            f"P10-P90 {p10:.3g}-{p90:.3g} [{self.source}]"
        )


PARAMETERS = (
    # ---- subsurface
    Parameter(
        "permeability_md",
        "Permeability",
        "challenge",
        "lognormal",
        (200.0, 100.0, 400.0),
        "mD",
        "brief+thermogis",
        "Brief gives 200 mD; a factor-2 P10/P90 spread follows ThermoGIS's log-normal kH maps.",
    ),
    Parameter(
        "geothermal_gradient_c_per_km",
        "Temperature gradient",
        "challenge",
        "normal",
        (30.0, 1.5, 26.0, 34.0),
        "degC/km",
        "brief+assumption",
        "+-1.5 degC/km (1 sd) around the brief's 30 degC/km; at 3.1 km that is +-4.7 degC.",
    ),
    Parameter(
        "reservoir_thickness_m",
        "Net reservoir thickness",
        "challenge",
        "triangular",
        (80.0, 100.0, 120.0),
        "m",
        "brief+assumption",
        "Net-to-gross uncertainty of +-20%.",
    ),
    Parameter(
        "skin",
        "Well skin",
        "assumptions",
        "triangular",
        (-1.0, 0.0, 5.0),
        "-",
        "assumption",
        "Skewed to damage: completion/scaling can add skin, stimulation rarely beats -1.",
    ),
    # ---- demand
    Parameter(
        "heating_scale",
        "Heating demand scale",
        "demand",
        "normal",
        (1.0, 0.06, 0.85, 1.2),
        "x",
        "assumption",
        "Whole-profile multiplier: weather-year and connection-growth spread of 6% (1 sd).",
    ),
    Parameter(
        "cooling_scale",
        "Cooling demand scale",
        "demand",
        "normal",
        (1.0, 0.10, 0.75, 1.3),
        "x",
        "assumption",
        "Cooling varies more with summer weather than heating does with winter: 10% (1 sd).",
    ),
    # ---- prices and emission factors
    Parameter(
        "electricity_wholesale_eur_per_mwh",
        "Electricity wholesale",
        "cost",
        "triangular",
        (60.0, 85.0, 130.0),
        "EUR/MWh",
        "tennet_2025+iea_2026",
        "NL day-ahead EUR 87/MWh in 2025, 2027 futures ~USD 85/MWh. Import price = wholesale "
        "+ grid/tax adder; CHP export earns 90% of wholesale (heat-led profile discount).",
    ),
    Parameter(
        "electricity_adder_eur_per_mwh",
        "Electricity grid + tax adder",
        "cost",
        "triangular",
        (20.0, 30.0, 45.0),
        "EUR/MWh",
        "assumption",
        "Transmission tariff, energy tax and levies for a >10 GWh/yr business connection.",
    ),
    Parameter(
        "ttf_gas_eur_per_mwh",
        "Gas price (TTF)",
        "cost",
        "triangular",
        (27.0, 42.0, 60.0),
        "EUR/MWh",
        "rabobank_ttf",
        "2027 base case EUR 42/MWh, 60 in a supply shock, 27 the 2025-26 lows. Purchased gas "
        "price = TTF + EUR 5/MWh transport and supply fees.",
    ),
    Parameter(
        "co2_price_eur_per_t",
        "CO2 price (EU ETS)",
        "assumptions",
        "triangular",
        (60.0, 95.0, 140.0),
        "EUR/t",
        "reuters_eua+iea_2026",
        "2025 average ~EUR 75/t, analysts' 2027 consensus EUR 107/t.",
    ),
    Parameter(
        "electricity_emission_kg_per_kwh",
        "Grid CO2 intensity",
        "assumptions",
        "triangular",
        (0.10, 0.20, 0.30),
        "kg/kWh",
        "cbs_ef",
        "CBS: 0.20 kg/kWh in 2024 and falling; 0.30 is the GEMINI example value.",
    ),
    # ---- capital cost and finance
    Parameter(
        "well_cost_factor",
        "Well cost factor",
        "cost",
        "triangular",
        (0.8, 1.0, 1.5),
        "x",
        "thermogis+assumption",
        "Multiplier on the ThermoGIS well-cost curve; right-skewed for drilling overruns.",
    ),
    Parameter(
        "surface_cost_factor",
        "Surface CAPEX factor",
        "cost",
        "triangular",
        (0.8, 1.0, 1.3),
        "x",
        "assumption",
        "Multiplier on all non-well equipment unit costs.",
    ),
    Parameter(
        "discount_rate",
        "Discount rate (real)",
        "cost",
        "triangular",
        (0.035, 0.051, 0.08),
        "-",
        "pbl_sde",
        "PBL SDE++ 2025 geothermal WACC: 5.1% real (7.2% nominal).",
    ),
)

PARAMETER_INDEX = {p.name: p for p in PARAMETERS}
GAS_SUPPLY_ADDER_EUR_PER_MWH = 5.0
EXPORT_SHARE_OF_WHOLESALE = 0.9


def get_parameters(names=None, overrides=None):
    """Return the parameter tuple, optionally a subset and/or with replaced distributions.

    ``overrides`` maps a name to ``{"dist": ..., "args": [...]}`` (either key
    optional) so an agent can narrow or widen a range without editing code.
    """
    params = [PARAMETER_INDEX[n] for n in names] if names else list(PARAMETERS)
    overrides = overrides or {}
    unknown = set(overrides) - set(PARAMETER_INDEX)
    if unknown:
        raise KeyError(f"Unknown uncertain parameter(s): {sorted(unknown)}")
    out = []
    for p in params:
        o = overrides.get(p.name)
        if o:
            p = Parameter(
                p.name,
                p.label,
                p.target,
                o.get("dist", p.dist),
                tuple(o.get("args", p.args)),
                p.unit,
                p.source + "+override",
                p.note,
            )
        out.append(p)
    return tuple(out)


def base_values(params=PARAMETERS):
    """Return ``{name: base value}``."""
    return {p.name: p.base for p in params}


def sample(params=PARAMETERS, n=200, seed=2027, method="lhs"):
    """Draw ``n`` joint samples (independent parameters) as a DataFrame.

    ``method="lhs"`` uses a scrambled Latin hypercube, which covers each
    marginal evenly with far fewer runs than plain random sampling.
    """
    d = len(params)
    if method == "lhs":
        u = qmc.LatinHypercube(d=d, seed=seed).random(n)
    elif method == "random":
        u = np.random.default_rng(seed).random((n, d))
    else:
        raise ValueError("method must be 'lhs' or 'random'")
    data = {p.name: p.ppf(u[:, j]) for j, p in enumerate(params)}
    table = pd.DataFrame(data)
    table.index.name = "sample"
    return table


def describe_parameters(params=PARAMETERS):
    """Return a table of every parameter with its range, base value and source."""
    rows = []
    for p in params:
        p10, p50, p90 = p.ppf([0.1, 0.5, 0.9])
        rows.append(
            {
                "name": p.name,
                "label": p.label,
                "acts_on": p.target,
                "distribution": f"{p.dist}{tuple(p.args)}",
                "unit": p.unit,
                "base": p.base,
                "p10": float(p10),
                "p50": float(p50),
                "p90": float(p90),
                "source": p.source,
                "note": p.note,
            }
        )
    return pd.DataFrame(rows)
