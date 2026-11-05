import pytest
from seasonal_heat_store import SeasonalHeatStore

@pytest.mark.parametrize('soc,charge,discharge', [(0,30,0),(10000,30,0),(10000,0,30),(100,0,30),(5000,12,0),(5000,0,12),(5000,30,20),(0,0,30)])
def test_storage_balance_and_limits(soc, charge, discharge):
    model = SeasonalHeatStore()
    model.calculate_output({'soc_mwh': soc, 'charge_request_mw': charge, 'discharge_request_mw': discharge})
    out = model.get_output()
    assert out['soc_mwh'] == pytest.approx(soc + 24*(out['charge_mw']-out['discharge_mw']) - out['loss_mwh'])
    assert 0 <= out['soc_mwh'] <= 10000
    assert 0 <= out['charge_mw'] <= min(charge,30)
    assert 0 <= out['discharge_mw'] <= min(discharge,30)
    assert out['loss_mwh'] >= 0
    assert out['charge_mw'] * out['discharge_mw'] == 0

def test_configured_power_is_honoured():
    model = SeasonalHeatStore()
    model.parameters.update({'power_mw': 7.0, 'loss_fraction_per_day': 0.0})
    model.calculate_output({'soc_mwh':5000, 'charge_request_mw':20, 'discharge_request_mw':0})
    assert model.get_output()['charge_mw'] == pytest.approx(7)
    model.calculate_output({'soc_mwh':5000, 'charge_request_mw':0, 'discharge_request_mw':20})
    assert model.get_output()['discharge_mw'] == pytest.approx(7)

def test_empty_store_cannot_deliver_energy():
    model = SeasonalHeatStore()
    model.calculate_output({'soc_mwh':0, 'charge_request_mw':0, 'discharge_request_mw':30})
    assert model.get_output()['discharge_mw'] == 0

def test_invalid_initial_energy_is_rejected():
    with pytest.raises(ValueError):
        SeasonalHeatStore().calculate_output({'soc_mwh':-1, 'charge_request_mw':0, 'discharge_request_mw':0})
