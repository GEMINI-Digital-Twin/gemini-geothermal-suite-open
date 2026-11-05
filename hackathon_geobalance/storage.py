"""Simple hot-water heat storage tank (daily time step).

Charged with spare geothermal capacity on low-demand days, discharged to
cover heating shortfalls (peak days, doublet maintenance) before the
backup boiler is used. Energy model only: stored at supply temperature,
a fixed fraction of the content is lost per day.
"""


class HeatStorage:
    def __init__(self, capacity_mwh=0.0, loss_per_day=0.01, max_power_mw=None):
        self.capacity = float(capacity_mwh)
        self.loss = float(loss_per_day)
        # Default: full charge/discharge in 2 days
        self.max_power = max_power_mw if max_power_mw is not None else self.capacity / 48.0
        self.soc = 0.5 * self.capacity   # start half full
        self.lost_mwh = 0.0

    def step_losses(self):
        lost = self.soc * self.loss
        self.soc -= lost
        self.lost_mwh += lost

    def charge(self, available_mw):
        """Store up to available_mw (daily average). Returns MW actually stored."""
        if self.capacity <= 0:
            return 0.0
        mw = min(available_mw, self.max_power, (self.capacity - self.soc) / 24.0)
        mw = max(mw, 0.0)
        self.soc += mw * 24.0
        return mw

    def discharge(self, needed_mw):
        """Deliver up to needed_mw (daily average). Returns MW delivered."""
        if self.capacity <= 0:
            return 0.0
        mw = min(needed_mw, self.max_power, self.soc / 24.0)
        mw = max(mw, 0.0)
        self.soc -= mw * 24.0
        return mw
