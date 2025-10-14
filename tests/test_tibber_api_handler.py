from datetime import datetime, timedelta

import pytest

from source.energy_classes import EnergyRate
from source.tibber_api_handler import TibberAPIHandler


@pytest.fixture
def starting_datetime():
    return datetime.fromtimestamp(0)


@pytest.fixture
def tibber_api_handler():
    tibber_api_handler = TibberAPIHandler()
    tibber_api_handler.log.trace = print
    tibber_api_handler.log.info = print
    tibber_api_handler.log.warning = print
    return tibber_api_handler


def construct_energy_rates(prices: list[float]) -> list[EnergyRate]:
    return [EnergyRate(price, datetime.fromtimestamp(index)) for index, price in enumerate(prices)]


@pytest.fixture
def upcoming_energy_rates():
    return construct_energy_rates(
        [29.62, 29.19, 28.96, 29, 29.43, 30.1, 33.81, 35.68, 35.77, 33.37, 30.17, 29.13]
        + [25.44, 22.8, 23.29, 26.09, 29.82, 31.46, 34.82, 35.35, 35.62, 33.49, 32.17, 30.54]
        + [30.23, 29.82, 29.6, 29.6, 29.81, 30.65, 33.72, 35.21, 35.6, 34.03, 31.58, 31.05]
        + [30.29, 29.6, 29.82, 30.41, 32.65, 33.96, 35.61, 36.72, 35.13, 33.53, 32.43, 31.59]
    )


@pytest.mark.parametrize(
    "starting_energy_rate_index, expected_energy_rate_index, first_iteration",
    [
        # First iteration
        (0, 2, True),
        (2, 2, True),
        (3, 3, True),
        (6, 6, True),
        (7, 7, True),
        (8, 13, True),
        (10, 13, True),
        (12, 13, True),
        (13, 13, True),
        (14, 14, True),
        (17, 17, True),
        (18, 18, True),
        (20, 26, True),
        # Not the first iteration
        (2, 13, False),
        (13, 26, False),
        (26, 37, False),
    ],
)
def test_get_next_price_minimum(
    tibber_api_handler,
    upcoming_energy_rates,
    starting_energy_rate_index,
    expected_energy_rate_index,
    first_iteration,
):
    considered_energy_rates = upcoming_energy_rates[starting_energy_rate_index:]
    expected_energy_rate = upcoming_energy_rates[expected_energy_rate_index]

    assert tibber_api_handler.get_next_price_minimum(first_iteration, considered_energy_rates) == expected_energy_rate


def test_aggregate_to_hourly_rates(tibber_api_handler):
    starting_time = datetime.fromtimestamp(0)
    quarter_hourly_rates = [
        EnergyRate(10, starting_time + timedelta(minutes=0)),
        EnergyRate(15, starting_time + timedelta(minutes=15)),
        EnergyRate(20, starting_time + timedelta(minutes=30)),
        EnergyRate(25, starting_time + timedelta(minutes=45)),
        EnergyRate(10, starting_time + timedelta(hours=1, minutes=0)),
        EnergyRate(10, starting_time + timedelta(hours=1, minutes=15)),
        EnergyRate(10, starting_time + timedelta(hours=1, minutes=30)),
        EnergyRate(10.951, starting_time + timedelta(hours=1, minutes=45)),
        EnergyRate(15, starting_time + timedelta(hours=2, minutes=0)),
    ]
    expected_hourly_rates = [
        EnergyRate(17.5, starting_time),
        EnergyRate(10.24, starting_time + timedelta(hours=1)),
        EnergyRate(15.0, starting_time + timedelta(hours=2)),
    ]

    assert tibber_api_handler._aggregate_to_hourly_rates(quarter_hourly_rates) == expected_hourly_rates
