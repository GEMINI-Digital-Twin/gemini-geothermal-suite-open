"""Electrical submersible pump (ESP) whose head and power follow the pump similarity laws: the 60 Hz curve is read at q x 60/f.

GEMINI's ESP reads the curve at q; at 60 Hz both agree.

Sources: Guelich 2014, Centrifugal Pumps, DOI 10.1007/978-3-642-40114-5; Takacs 2009, Electrical Submersible Pumps Manual.
"""

from gemini_model.pump.esp import ESP


class ESPAffinity(ESP):
    """GEMINI ESP with head and power read at the 60 Hz-equivalent flow q x 60/f."""

    def head_function(self, pump_flow, freq):
        """Head (Pa) at flow pump_flow (m3/s) and frequency freq (Hz), similarity law."""
        return super().head_function(pump_flow * 60.0 / self._check(freq), freq)

    def power_function(self, pump_flow, freq):
        """Shaft power (W) at flow pump_flow (m3/s) and frequency freq (Hz), similarity law."""
        return super().power_function(pump_flow * 60.0 / self._check(freq), freq)

    @staticmethod
    def _check(freq):
        """Return freq, or raise ValueError if it is not above 0 Hz."""
        if freq <= 0:
            raise ValueError(f"ESP frequency must be > 0 Hz, got {freq}.")
        return freq
