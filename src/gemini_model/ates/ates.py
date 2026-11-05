"""Shallow aquifer thermal energy storage (ATES) for cooling, one day per call.

An open-loop ATES system has one or more well pairs in a shallow aquifer
(typically 50-250 m deep in the Netherlands). Each pair has a *cold* well
and a *warm* well. In winter, water is pumped from the warm well, cooled
in a dry cooler against cold outdoor air, and injected into the cold
well. In summer the flow reverses: cold water is pumped from the cold
well, cools the district chilled-water return in a plate heat exchanger
(the aquifer water and the network never mix), and goes back into the
warm well.

The model keeps two lumped stores (the cold and the warm "bubble"), each
with a volume and a mixed temperature. The state is passed in and
returned, so the model itself has no hidden state and one call is one
24 h day:

1. Standing loss: both store temperatures relax towards the undisturbed
   groundwater temperature by ``loss_fraction_per_day`` (conduction to
   the surrounding aquifer and mixing at the bubble edge).
2. ``mode = "discharge"``: cools the chilled-water stream as far as the
   cold water allows (outlet no colder than ``chilled_temperature_out_target``
   and no colder than the extracted water + ``hex_approach``), limited by
   the well flow and by ``cooling_request`` if given. Once the cold
   bubble is used up the well draws native groundwater.
3. ``mode = "charge"``: cools warm-well water to
   ``max(cold_injection_min, air_temperature + charge_approach)`` and
   injects it into the cold well, at full flow, until the cold store is
   full.

Pump power follows the flow squared at a fixed pressure drop at full
flow; the dry-cooler fans draw ``fan_power_fraction`` of the heat they
reject.

Parameters
----------
well_pairs, flow_max_m3h (per pair), groundwater_c, warm_well_max_c,
cold_injection_min_c, charge_approach_k, hex_approach_k,
pressure_drop_bar (per pair at full flow), pump_efficiency,
loss_fraction_per_day, store_volume_m3 (per pair, per store),
fan_power_fraction, rho, cp.

Inputs
------
State: ``cold_volume_m3``, ``cold_temperature_c``, ``warm_volume_m3``,
``warm_temperature_c``. ``mode`` ("discharge", "charge" or "idle").
Discharge: ``chilled_temperature_in`` (degC), ``chilled_flow_rate``
(m3/s), ``chilled_temperature_out_target`` (degC), optional
``cooling_request`` (W) and ``flow_fraction`` (share of the well flow
allowed, 0-1). Charge: ``air_temperature`` (degC, daily mean), optional
``flow_fraction``.

Outputs
-------
``cooling_power`` (W), ``chilled_temperature_out``, ``charge_power`` (W of
heat removed from the aquifer water), ``groundwater_flow_m3h``,
``extraction_temperature_c``, ``injection_temperature_c``,
``pump_power``, ``fan_power``, ``power_el`` (W), ``loss_mwh`` (the day's
standing loss, MWh relative to groundwater) and the new state.

References
----------
Fleuchaus, P., Godschalk, B., Stober, I., Blum, P. (2018). "Worldwide
application of aquifer thermal energy storage - A review." Renewable and
Sustainable Energy Reviews 94, 861-876.
Bloemendal, M., Olsthoorn, T., van de Ven, F. (2015). "Combining climatic
and geo-hydrological preconditions as a method to determine world
potential for aquifer thermal energy storage." Science of the Total
Environment 538, 621-633.
"""

from gemini_model.model_abstract import StaticModel

SECONDS_PER_DAY = 86400.0
MODES = ("discharge", "charge", "idle")


class ATES(StaticModel):
    """Open-loop aquifer cold store with a cold and a warm well bubble."""

    def __init__(self):
        """Model initialization with typical Dutch shallow-ATES defaults."""
        self.parameters = {
            "well_pairs": 1,
            "flow_max_m3h": 150.0,
            "groundwater_c": 11.0,
            "warm_well_max_c": 25.0,
            "cold_injection_min_c": 5.0,
            "charge_approach_k": 5.0,
            "hex_approach_k": 1.5,
            "pressure_drop_bar": 4.0,
            "pump_efficiency": 0.7,
            "loss_fraction_per_day": 0.0015,
            "store_volume_m3": 1.5e6,
            "fan_power_fraction": 0.03,
            "rho": 1000.0,
            "cp": 4186.0,
        }
        self.output = {}

    def update_parameters(self, parameters):
        """Update model parameters.

        Parameters
        ----------
        parameters: dict
            Parameters dict as defined by the model.
        """
        for key, value in parameters.items():
            self.parameters[key] = value

    def initialize_state(self, x):
        """Return the default state: both stores empty, at groundwater temperature."""
        t_gw = self.parameters["groundwater_c"]
        return {
            "cold_volume_m3": 0.0,
            "cold_temperature_c": t_gw,
            "warm_volume_m3": 0.0,
            "warm_temperature_c": t_gw,
        }

    def update_state(self, u, x):
        """Return the state after the last calculated day."""
        return {k: self.output[k] for k in self.initialize_state(None)}

    # ------------------------------------------------------------------ helpers
    def _q_max(self, flow_fraction):
        p = self.parameters
        return p["well_pairs"] * p["flow_max_m3h"] / 3600.0 * max(0.0, min(1.0, flow_fraction))

    def _pump_power(self, q):
        """Well-pump power (W) for a total groundwater flow ``q`` (m3/s), shared by the pairs."""
        p = self.parameters
        if q <= 0.0 or p["well_pairs"] <= 0:
            return 0.0
        q_pair_max = p["flow_max_m3h"] / 3600.0
        q_pair = q / p["well_pairs"]
        dp = p["pressure_drop_bar"] * 1e5 * (q_pair / q_pair_max) ** 2
        return q * dp / p["pump_efficiency"]

    @staticmethod
    def _blend(volume_needed, store_volume, store_t, native_t):
        """Mean temperature of ``volume_needed`` drawn from a store, then from native water."""
        if volume_needed <= 0.0:
            return store_t if store_volume > 0 else native_t
        from_store = min(volume_needed, store_volume)
        return (from_store * store_t + (volume_needed - from_store) * native_t) / volume_needed

    @staticmethod
    def _mix(volume, t, added_volume, added_t):
        total = volume + added_volume
        if total <= 0.0:
            return 0.0, t
        return total, (volume * t + added_volume * added_t) / total

    # ------------------------------------------------------------------ main
    def calculate_output(self, u, x=None):
        """Calculate one day of operation; see the module docstring for keys."""
        p = self.parameters
        rho_cp = p["rho"] * p["cp"]
        t_gw = p["groundwater_c"]
        capacity = p["well_pairs"] * p["store_volume_m3"]
        keep = 1.0 - p["loss_fraction_per_day"]

        v_c, v_w = max(0.0, u["cold_volume_m3"]), max(0.0, u["warm_volume_m3"])
        t_c0, t_w0 = u["cold_temperature_c"], u["warm_temperature_c"]
        t_c = t_gw + (t_c0 - t_gw) * keep
        t_w = t_gw + (t_w0 - t_gw) * keep
        loss_j = rho_cp * (v_c * abs(t_c0 - t_c) + v_w * abs(t_w0 - t_w))

        mode = u.get("mode", "idle")
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got '{mode}'")
        flow_fraction = u.get("flow_fraction", 1.0)
        q_max = self._q_max(flow_fraction)

        out = {
            "cooling_power": 0.0,
            "chilled_temperature_out": u.get("chilled_temperature_in"),
            "charge_power": 0.0,
            "groundwater_flow_m3h": 0.0,
            "extraction_temperature_c": None,
            "injection_temperature_c": None,
            "pump_power": 0.0,
            "fan_power": 0.0,
        }

        if mode == "discharge" and q_max > 0.0 and u.get("chilled_flow_rate", 0.0) > 0.0:
            t_in = u["chilled_temperature_in"]
            cap_chw = u["chilled_flow_rate"] * rho_cp
            t_target = u["chilled_temperature_out_target"]
            request = u.get("cooling_request")
            t_back = min(t_in - p["hex_approach_k"], p["warm_well_max_c"])  # into the warm well
            room = max(0.0, capacity - v_w)  # the warm store takes what the cold one gives
            t_ext, q = (t_c if v_c > 0 else t_gw), 0.0
            cooling = 0.0
            for _ in range(30):  # the extraction temperature depends on the volume drawn
                t_out = max(t_target, t_ext + p["hex_approach_k"])
                wanted = max(0.0, cap_chw * (t_in - t_out))
                if request is not None:
                    wanted = min(wanted, max(0.0, request))
                dt_ground = t_back - t_ext
                if wanted <= 0.0 or dt_ground <= 0.0:
                    q, cooling = 0.0, 0.0
                    break
                q = min(q_max, wanted / (rho_cp * dt_ground), room / SECONDS_PER_DAY)
                t_new = self._blend(q * SECONDS_PER_DAY, v_c, t_c, t_gw)
                cooling = q * rho_cp * (t_back - t_new)
                if abs(t_new - t_ext) < 1e-6:
                    break
                t_ext = t_new
            if q > 0.0:
                volume = q * SECONDS_PER_DAY
                t_ext = self._blend(volume, v_c, t_c, t_gw)
                cooling = max(0.0, min(cooling, cap_chw * (t_in - t_target)))
                v_c = max(0.0, v_c - volume)
                v_w, t_w = self._mix(v_w, t_w, volume, t_back)
                out.update(
                    {
                        "cooling_power": cooling,
                        "chilled_temperature_out": t_in - cooling / cap_chw,
                        "groundwater_flow_m3h": q * 3600.0,
                        "extraction_temperature_c": t_ext,
                        "injection_temperature_c": t_back,
                        "pump_power": self._pump_power(q),
                    }
                )

        elif mode == "charge" and q_max > 0.0:
            t_inj = max(p["cold_injection_min_c"], u["air_temperature"] + p["charge_approach_k"])
            room = max(0.0, capacity - v_c)
            q = min(q_max, room / SECONDS_PER_DAY)
            volume = q * SECONDS_PER_DAY
            t_src = self._blend(volume, v_w, t_w, t_gw)
            if q > 0.0 and t_src - t_inj >= 2.0:
                heat = q * rho_cp * (t_src - t_inj)
                v_w = max(0.0, v_w - volume)
                v_c, t_c = self._mix(v_c, t_c, volume, t_inj)
                out.update(
                    {
                        "charge_power": heat,
                        "groundwater_flow_m3h": q * 3600.0,
                        "extraction_temperature_c": t_src,
                        "injection_temperature_c": t_inj,
                        "pump_power": self._pump_power(q),
                        "fan_power": p["fan_power_fraction"] * heat,
                    }
                )

        out["power_el"] = out["pump_power"] + out["fan_power"]
        out["loss_mwh"] = loss_j / 3.6e9
        out.update(
            {
                "cold_volume_m3": v_c,
                "cold_temperature_c": t_c,
                "warm_volume_m3": v_w,
                "warm_temperature_c": t_w,
            }
        )
        self.output = out

    def get_output(self):
        """Get output of the model."""
        return self.output
