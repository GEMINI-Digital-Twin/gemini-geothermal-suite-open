"""ESP whose head and power follow the pump similarity (affinity) laws at any frequency.

Why: GEMINI's ESP reads the 60 Hz polynomial at the actual flow, head = N (f/60)^2 H(q) and
power = N (f/60)^3 P(q). The similarity laws scale flow too, so the curve must be read at the flow
the pump would deliver at 60 Hz:

    head(q, f)  = N (f/60)^2 H(q 60/f)
    power(q, f) = N (f/60)^3 P(q 60/f)

At 60 Hz both forms agree; away from 60 Hz GEMINI shifts the best-efficiency point. Efficiency comes
from the parent's efficiency_function and is the same at homologous points (q proportional to f).
Same parameters, inputs and outputs as gemini_model.pump.esp.ESP.

Sources: Guelich, J. F. (2014) Centrifugal Pumps, 3rd ed., Springer,
DOI 10.1007/978-3-642-40114-5 (similarity laws); Takacs, G. (2009) Electrical Submersible Pumps
Manual, Gulf Professional Publishing, ISBN 978-1-85617-557-9 (variable-speed ESP operation).
"""

from gemini_model.pump.esp import ESP


class ESPAffinity(ESP):
    """ESP with head and power read at the 60 Hz-equivalent flow q 60/f."""

    def head_function(self, pump_flow, freq):
        """Head (Pa) at flow pump_flow (m3/s) and frequency freq (Hz), similarity law."""
        return super().head_function(pump_flow * 60.0 / self._check(freq), freq)

    def power_function(self, pump_flow, freq):
        """Shaft power (W) at flow pump_flow (m3/s) and frequency freq (Hz), similarity law."""
        return super().power_function(pump_flow * 60.0 / self._check(freq), freq)

    @staticmethod
    def _check(freq):
        if freq <= 0:
            raise ValueError(f"ESP frequency must be > 0 Hz, got {freq}.")
        return freq
