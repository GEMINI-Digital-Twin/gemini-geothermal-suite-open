"""Operating memory for the doublets: commitment rules and wellbore warm-up.

The plain dispatch in :mod:`gemini_design.annual` treats every day as an
independent steady state, so a doublet can start one day and stop the next
for free, and a well restarted after a 35-day outage delivers its full
steady wellhead temperature at once. Real doublets do neither:

* **Commitment.** Every ESP start costs run life (inrush current, thermal
  and mechanical shock, a pulse of fines), so operators keep a pump running
  at low flow rather than cycling it. :func:`commit` chooses how many
  doublets run on each of the 365 days with a dynamic program that adds a
  cost per start and a minimum run time and minimum stop time.
* **Wellbore warm-up.** A flowing producer heats the casing, cement and
  rock around it. The heat loss is large just after a start and falls
  slowly as that rock warms (Ramey 1962; Hasan and Kabir 1991 time
  function). After a stop the rock cools again, so a restart begins part
  of the way back. :class:`WellboreThermalState` tracks this per doublet
  and turns it into a multiplier on the heat loss of GEMINI's steady well
  model (which uses a fixed U = 10 W/m2K on the casing).
"""

import math
from dataclasses import dataclass

import numpy as np

from gemini_design.challenge import ASSUMPTIONS


@dataclass
class OperatingRules:
    """Operating rules for :func:`gemini_design.annual.run_year`.

    ``min_run_days``: a doublet that starts runs at least this long.
    ``min_stop_days``: a doublet that stops stays off at least this long.
    ``start_cost_eur``: cost per doublet start (ESP wear and lost run life).
    ``wellbore_transient``: apply the time-dependent wellbore heat loss.
    ``reference_age_days``: how long the doublets have been flowing when the
    year starts (the plant is in its second year or later).
    """

    min_run_days: int = 7
    min_stop_days: int = 7
    start_cost_eur: float = 10_000.0
    wellbore_transient: bool = True
    reference_age_days: float = 365.0

    def as_dict(self):
        """Return the rules as a plain dict (for summaries)."""
        return dict(self.__dict__)


# ---------------------------------------------------------------- wellbore heat loss
def time_function(t_d):
    """Return the Hasan and Kabir (1991) dimensionless time function f(tD).

    ``t_d`` = alpha t / rw^2. Valid for any tD > 0; f -> 0 as tD -> 0. The two
    published branches differ by about 2.5 % where they meet at tD = 1.5.
    """
    if t_d <= 0.0:
        return 0.0
    if t_d <= 1.5:
        root = math.sqrt(t_d)
        return 1.1281 * root * (1.0 - 0.3 * root)
    return (0.4063 + 0.5 * math.log(t_d)) * (1.0 + 0.6 / t_d)


def _inverse_time_function(f_target):
    """Return the tD at which :func:`time_function` equals ``f_target``."""
    if f_target <= 0.0:
        return 0.0
    lo, hi = 0.0, 1.0
    while time_function(hi) < f_target:
        hi *= 4.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if time_function(mid) < f_target else (lo, mid)
    return 0.5 * (lo + hi)


class WellboreModel:
    """Heat-loss coefficient of a producer as a function of time since start."""

    def __init__(self, assumptions=ASSUMPTIONS):
        """Read formation and wellbore properties from ``assumptions``."""
        a = assumptions
        self.r = a["wellbore_radius_m"]
        self.k = a["formation_conductivity_w_per_m_k"]
        self.alpha = a["formation_diffusivity_m2_per_s"]
        self.u = a["wellbore_u_w_per_m2_k"]
        # GEMINI's steady well model: U = 10 W/m2K on the inner casing area
        self.gemini_w_per_m_k = math.pi * a["well_inner_diameter_m"] * 10.0

    def t_d(self, age_days):
        """Return dimensionless time for an age in days."""
        return self.alpha * age_days * 86400.0 / self.r**2

    def loss_w_per_m_k(self, age_days):
        """Return heat loss per metre and kelvin of fluid-to-geotherm difference (W/m/K)."""
        f = time_function(self.t_d(age_days))
        ru = self.r * self.u
        return 2.0 * math.pi * ru * self.k / (self.k + f * ru)

    def multiplier(self, age_days):
        """Return heat loss at ``age_days`` relative to GEMINI's steady well model."""
        return self.loss_w_per_m_k(age_days) / self.gemini_w_per_m_k

    def restart_age_days(self, age_at_stop_days, stop_days):
        """Return the equivalent age of a well restarted after a stop.

        Superposition in time: the rock around a well that flowed for A days
        and then stopped for ts days keeps a disturbance proportional to
        f(A + ts) - f(ts). The restart age is the age at which a fresh well
        carries the same disturbance.
        """
        remaining = time_function(self.t_d(age_at_stop_days + stop_days)) - time_function(
            self.t_d(stop_days)
        )
        return _inverse_time_function(remaining) * self.r**2 / self.alpha / 86400.0


class WellboreThermalState:
    """Track each doublet's wellbore age through the year (one call per day)."""

    def __init__(self, n_doublets, rules, assumptions=ASSUMPTIONS):
        """Start every doublet as flowing for ``rules.reference_age_days``."""
        self.model = WellboreModel(assumptions)
        self.rules = rules
        self.running = [True] * n_doublets
        self.age = [rules.reference_age_days] * n_doublets
        self.age_at_stop = [rules.reference_age_days] * n_doublets
        self.stopped_days = [0.0] * n_doublets
        self._first_day = True

    def step(self, n_active, available):
        """Advance one day with ``n_active`` doublets running.

        Running doublets are kept running if they are available; extra ones
        are started from the available doublets that stopped most recently
        (warmest rock). Returns a dict with the day's ``heat_loss_multiplier``
        (mean over running doublets, as their brine mixes at equal flow),
        ``starts`` and ``running`` (list of doublet indices).
        """
        n = len(self.running)
        keep = [i for i in range(n) if self.running[i] and available[i]]
        if len(keep) > n_active:
            keep = keep[:n_active]
        candidates = sorted(
            (i for i in range(n) if available[i] and i not in keep),
            key=lambda i: self.stopped_days[i] if not self.running[i] else -1.0,
        )
        running = sorted(keep + candidates[: n_active - len(keep)])
        starts = 0
        multipliers = []
        for i in range(n):
            if i in running:
                if not self.running[i]:
                    if not self._first_day:
                        starts += 1
                    self.age[i] = self.model.restart_age_days(
                        self.age_at_stop[i], self.stopped_days[i]
                    )
                    self.running[i] = True
                multipliers.append(self.model.multiplier(self.age[i] + 0.5))
                self.age[i] += 1.0
            else:
                if self.running[i]:
                    self.age_at_stop[i] = self.age[i]
                    self.stopped_days[i] = 0.0
                    self.running[i] = False
                self.stopped_days[i] += 1.0
        self._first_day = False
        steady = self.model.multiplier(self.rules.reference_age_days)
        if not self.rules.wellbore_transient:
            multipliers = [steady] * len(multipliers)
        return {
            "heat_loss_multiplier": float(np.mean(multipliers)) if multipliers else steady,
            "starts": starts,
            "running": running,
        }


# ---------------------------------------------------------------- commitment
DWELL_PENALTY_EUR = 1.0e6  # breaking a min run/stop time is allowed only if nothing else works


def commit(daily_scores, n_available, rules):
    """Choose the number of running doublets for every day.

    ``daily_scores[i][n]`` is the day's score (EUR, with the unmet-demand
    penalty) of the best operating point with exactly ``n`` doublets
    running, ``inf`` if there is none. Starting a doublet costs
    ``rules.start_cost_eur``. Raising the count needs the current count to
    have held for ``min_stop_days``, lowering it ``min_run_days``; a drop
    forced by an outage is always allowed. A rule may be broken only at
    :data:`DWELL_PENALTY_EUR`, so a plan always exists.

    Returns
    -------
    (list of int, int)
        Running doublets per day, and the number of rule breaks.
    """
    n_days = len(daily_scores)
    n_max = max(len(s) for s in daily_scores) - 1
    hold = max(1, rules.min_run_days, rules.min_stop_days)
    inf = float("inf")
    # cost[n][d]: best total cost so far, ending in n running for d days (capped at hold)
    cost = np.full((n_max + 1, hold + 1), inf)
    for n, s in enumerate(daily_scores[0]):
        cost[n][hold] = s
    back = []
    for i in range(1, n_days):
        new = np.full((n_max + 1, hold + 1), inf)
        arg = {}
        scores = daily_scores[i]
        for m, s in enumerate(scores):
            if not math.isfinite(s):
                continue
            for n in range(n_max + 1):
                for d in range(1, hold + 1):
                    c0 = cost[n][d]
                    if not math.isfinite(c0):
                        continue
                    if m == n:
                        d2, extra, broke = min(d + 1, hold), 0.0, 0
                    else:
                        forced = n > n_available[i]
                        need = rules.min_stop_days if m > n else rules.min_run_days
                        broke = 0 if (forced or d >= need) else 1
                        d2 = 1
                        extra = max(0, m - n) * rules.start_cost_eur + broke * DWELL_PENALTY_EUR
                    c = c0 + s + extra
                    if c < new[m][d2]:
                        new[m][d2] = c
                        arg[(m, d2)] = (n, d, broke)
        back.append(arg)
        cost = new
    m, d = np.unravel_index(np.argmin(cost), cost.shape)
    plan = [int(m)]
    breaks = 0
    for arg in reversed(back):
        n, d, broke = arg[(int(m), int(d))]
        breaks += broke
        plan.append(int(n))
        m = n
    plan.reverse()
    return plan, breaks
