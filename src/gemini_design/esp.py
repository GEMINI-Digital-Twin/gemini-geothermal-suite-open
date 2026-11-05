"""Sized electric submersible pump (ESP) for a producer: pump curve, drive and cost.

By default the design toolkit treats the ESP as an ideal pump: it gives the
producer whatever pressure the day's flow needs at the challenge's fixed
70% efficiency, for any flow from 50 to 300 m3/h, and its cost sits inside
``surface_cost_per_doublet_eur``. A design that sets
``esp_rated_flow_m3h`` gets a real pump instead:

* **Rating.** The pump's best-efficiency flow ``Q_r`` is the design's
  rated flow; its rated head ``H_r`` is the head the producer needs at
  ``Q_r`` times ``esp_head_margin``. The motor is rated
  ``Q_r H_r / eta_bep`` times ``esp_motor_margin``.
* **Curve.** At nominal speed the head falls with flow as
  ``H = H_r (a - (a - 1) x^2)`` with ``x = Q / Q_r`` and ``a`` the
  shut-off head ratio (``esp_shutoff_head_ratio``); the efficiency is
  ``eta = eta_bep (2x - x^2)``, peaking at ``Q_r``. ``eta_bep`` is the
  challenge's ``pump_efficiency``.
* **Fixed-speed drive.** The pump runs on its curve and a surface choke
  burns the head the well does not need, so the motor pays for the full
  pump head. A flow whose curve head is below what the well needs cannot
  be delivered.
* **Variable-speed drive (VSD).** The speed is set so the pump head equals
  what the well needs (affinity laws: ``H(Q, s) = s^2 H(Q / s, 1)``,
  efficiency read at the equivalent point ``Q / s``), between
  ``esp_vsd_speed_min`` and ``esp_vsd_speed_max`` of nominal speed. Below
  the minimum speed the excess head is choked; above the maximum the flow
  cannot be delivered. The drive loses ``1 - esp_vsd_efficiency``.
* **Operating range.** The equivalent point ``x`` must stay within
  ``esp_min_flow_ratio``..``esp_max_flow_ratio`` (thrust and wear limits);
  outside it the day is a violation, so the dispatcher picks another flow.
* **Cost.** ``esp_cost_fixed_eur + esp_cost_eur_per_kw x motor kW`` (plus
  ``esp_vsd_cost_eur_per_kw`` for a VSD), booked against
  ``esp_reference_cost_eur``, the share of the surface cost per doublet
  that the ideal-pump default already pays for an ESP.

All pump numbers are stated assumptions in
:data:`gemini_design.challenge.ASSUMPTIONS` (team estimates, low confidence).
"""

import math

DRIVES = ("vsd", "fixed")


class EspPump:
    """One producer's ESP, sized for a rated flow at that producer's head."""

    def __init__(self, rated_flow_m3h, rated_head_bar, drive, efficiency_bep, assumptions):
        """Set up the pump; ``rated_head_bar`` already includes the head margin."""
        if drive not in DRIVES:
            raise ValueError(f"esp_drive must be one of {DRIVES}")
        a = assumptions
        self.rated_flow_m3h = float(rated_flow_m3h)
        self.rated_head_bar = float(rated_head_bar)
        self.drive = drive
        self.efficiency_bep = float(efficiency_bep)
        self.shutoff = float(a["esp_shutoff_head_ratio"])
        self.x_min = float(a["esp_min_flow_ratio"])
        self.x_max = float(a["esp_max_flow_ratio"])
        self.s_min = float(a["esp_vsd_speed_min"]) if drive == "vsd" else 1.0
        self.s_max = float(a["esp_vsd_speed_max"]) if drive == "vsd" else 1.0
        self.drive_efficiency = float(a["esp_vsd_efficiency"]) if drive == "vsd" else 1.0
        self.motor_kw = (
            self.rated_flow_m3h
            / 3600.0
            * self.rated_head_bar
            * 1e5
            / self.efficiency_bep
            * float(a["esp_motor_margin"])
            / 1e3
        )

    @classmethod
    def sized_for(cls, hydraulics, rated_flow_m3h, drive, challenge, assumptions):
        """Size a pump for a :class:`gemini_design.doublet.DoubletHydraulics` producer."""
        need = hydraulics.ideal_producer(rated_flow_m3h)["esp_dp_bar"]
        head = max(need, 1.0) * float(assumptions["esp_head_margin"])
        return cls(rated_flow_m3h, head, drive, challenge["pump_efficiency"], assumptions)

    def flow_range_m3h(self):
        """Flows the pump can run at (operating range times the speed range)."""
        return (
            self.s_min * self.x_min * self.rated_flow_m3h,
            self.s_max * self.x_max * self.rated_flow_m3h,
        )

    def _head_bar(self, x, speed):
        return self.rated_head_bar * speed * speed * (self.shutoff - (self.shutoff - 1.0) * x * x)

    def operate(self, flow_m3h, needed_dp_bar):
        """Return the pump's duty at a flow and the head the well needs there.

        Keys: ``esp_power_w`` (electric), ``esp_pump_dp_bar`` (head the pump
        makes), ``esp_choke_bar`` (head burnt at the surface choke),
        ``esp_speed_ratio``, ``esp_efficiency`` (wire to water),
        ``esp_flow_ratio`` (equivalent point ``x``), ``esp_in_range``.
        """
        q = float(flow_m3h)
        need = max(0.0, float(needed_dp_bar))
        r = q / self.rated_flow_m3h
        if self.drive == "vsd":
            # speed that makes the pump head exactly what the well needs
            s2 = (need / self.rated_head_bar + (self.shutoff - 1.0) * r * r) / self.shutoff
            speed = math.sqrt(max(s2, 0.0))
            speed = min(max(speed, self.s_min), self.s_max)
        else:
            speed = 1.0
        x = r / speed if speed > 0 else float("inf")
        head = self._head_bar(x, speed)
        can_lift = head >= need - 1e-9
        in_range = self.x_min - 1e-9 <= x <= self.x_max + 1e-9 and can_lift
        eff_pump = self.efficiency_bep * max(2.0 * x - x * x, 0.05)
        eff = eff_pump * self.drive_efficiency
        pump_head = max(head, need)  # an undeliverable flow is still costed at the needed head
        power = q / 3600.0 * pump_head * 1e5 / eff
        return {
            "esp_power_w": power,
            "esp_pump_dp_bar": pump_head,
            "esp_choke_bar": max(0.0, head - need),
            "esp_speed_ratio": speed,
            "esp_efficiency": eff,
            "esp_flow_ratio": x,
            "esp_in_range": bool(in_range),
        }

    def capex_eur(self, assumptions):
        """Installed cost of this pump (and drive), EUR."""
        a = assumptions
        cost = a["esp_cost_fixed_eur"] + a["esp_cost_eur_per_kw"] * self.motor_kw
        if self.drive == "vsd":
            cost += a["esp_vsd_cost_eur_per_kw"] * self.motor_kw
        return cost

    def as_dict(self):
        """Rating summary for reports."""
        return {
            "rated_flow_m3h": self.rated_flow_m3h,
            "rated_head_bar": self.rated_head_bar,
            "drive": self.drive,
            "motor_kw": self.motor_kw,
            "flow_range_m3h": list(self.flow_range_m3h()),
        }


def capex_vs_reference_eur(pumps, assumptions):
    """Cost of the design's sized pumps less the ESP share already in the surface cost."""
    if not pumps:
        return 0.0
    return sum(p.capex_eur(assumptions) - assumptions["esp_reference_cost_eur"] for p in pumps)
