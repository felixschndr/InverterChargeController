from datetime import datetime, timedelta

import pytest

from source.energy_classes import EnergyRate


def test_energy_rates_with_the_same_price_at_different_timestamps_are_not_equal():
    price = 29.6
    earlier_rate = EnergyRate(price, datetime(2020, 1, 1, 10, 0))
    later_rate = EnergyRate(price, datetime(2020, 1, 1, 14, 0))

    assert earlier_rate != later_rate


def test_energy_rates_are_equal_when_all_of_their_fields_match():
    timestamp = datetime(2020, 1, 1, 10, 0)

    assert EnergyRate(29.6, timestamp) == EnergyRate(29.6, timestamp)


def test_removing_an_energy_rate_from_a_list_removes_the_one_with_the_matching_timestamp():
    price = 29.6
    rates = [
        EnergyRate(price, datetime(2020, 1, 1, 10, 0)),
        EnergyRate(31.4, datetime(2020, 1, 1, 11, 0)),
        EnergyRate(price, datetime(2020, 1, 1, 12, 0)),
    ]

    rates.remove(rates[2])

    assert [rate.timestamp.hour for rate in rates] == [10, 11]


@pytest.mark.parametrize("comparison", [lambda a, b: a < b, lambda a, b: a > b, lambda a, b: a >= b])
def test_energy_rates_cannot_be_compared_without_naming_the_field_to_compare(comparison):
    cheaper_rate = EnergyRate(29.6, datetime(2020, 1, 1, 10, 0))
    pricier_rate = EnergyRate(31.4, datetime(2020, 1, 1, 11, 0))

    with pytest.raises(TypeError):
        comparison(cheaper_rate, pricier_rate)

    assert cheaper_rate.rate < pricier_rate.rate


def test_energy_rate_keeps_its_default_maximum_charging_duration():
    assert EnergyRate(29.6, datetime(2020, 1, 1, 10, 0)).maximum_charging_duration == timedelta(hours=1)
