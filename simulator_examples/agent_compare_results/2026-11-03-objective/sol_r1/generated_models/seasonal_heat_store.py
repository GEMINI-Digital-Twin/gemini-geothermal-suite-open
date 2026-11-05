from gemini_model.model_abstract import StaticModel

class SeasonalHeatStore(StaticModel):
    def __init__(self):
        super().__init__()
        self.parameters.update({'capacity_mwh': 10000.0, 'power_mw': 30.0, 'loss_fraction_per_day': 0.001})

    def calculate_output(self, u, x=None):
        capacity = max(0.0, float(self.parameters['capacity_mwh']))
        power = max(0.0, float(self.parameters['power_mw']))
        loss_fraction = min(1.0, max(0.0, float(self.parameters['loss_fraction_per_day'])))
        soc = float(u['soc_mwh'])
        if not 0.0 <= soc <= capacity:
            raise ValueError('Initial state of charge must be within storage capacity')
        loss = soc * loss_fraction
        available = soc - loss
        charge_request = max(0.0, float(u['charge_request_mw']))
        discharge_request = max(0.0, float(u['discharge_request_mw']))
        net_request = charge_request - discharge_request
        charge = min(max(net_request, 0.0), power, (capacity - available) / 24.0)
        discharge = min(max(-net_request, 0.0), power, available / 24.0)
        self.output = {'soc_mwh': available + 24.0 * (charge - discharge), 'charge_mw': charge, 'discharge_mw': discharge, 'loss_mwh': loss}
        return self.output
