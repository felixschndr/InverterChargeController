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
    starting_time = datetime.fromtimestamp(0) - timedelta(hours=1)
    return [EnergyRate(price, starting_time + timedelta(minutes=15) * index) for index, price in enumerate(prices)]


@pytest.fixture
def upcoming_energy_rates():
    return construct_energy_rates(
        [33.1, 31.87, 31.13, 31.06]
        + [31.6, 31.13, 31.01, 30.9]
        + [31.06, 31.01, 30.95, 30.95]
        + [31.29, 31.29, 31.43, 31.6]
        + [31.16, 31.49, 31.18, 31.46]
        + [30.92, 31.69, 32.5, 33.83]
        + [32.44, 34.88, 36.75, 38.99]
        + [40.05, 42.49, 42.34, 41.19]
        + [44.72, 37.95, 34.88, 32.23]
        + [37.49, 33.39, 32.04, 30.75]
        + [33.18, 31.97, 30.56, 28.83]
        + [30.83, 29.47, 28.67, 28.2]
        + [29.01, 28.66, 28.68, 28.66]
        + [28.7, 28.95, 29.16, 29.32]
        + [28.57, 29.25, 29.77, 30.55]
        + [28.66, 29.77, 31.37, 32.67]
        + [28.29, 31.55, 33.16, 34.78]
        + [31.07, 34.68, 38.15, 44.13]
        + [38.38, 44.69, 54.81, 66.23]
        + [69.51, 65.68, 59.2, 51.02]
        + [46.84, 39.37, 35.99, 33.75]
        + [36.44, 35.34, 33.15, 32.45]
        + [33.85, 32.97, 32.24, 31.41]
        + [32.15, 31.79, 31.74, 31.05]
    )


@pytest.mark.parametrize(
    "starting_energy_rate_index, expected_energy_rate_index, first_iteration",
    [
        # First iteration
        # (0, 7, True),
        # (8, 20, True),
        # (21, 21, True),
        # (23, 24, True),
        # (24, 24, True),
        # (29, 35, True),
        # (35, 35, True),
        # (36, 47, True),
        # (39, 47, True),
        # (48, 64, True),
        # (64, 64, True),
        # (65, 68, True),
        # (69, 69, True),
        # (70, 70, True),
        # (71, 72, True),
        # (72, 72, True),
        # (76, 95, True),
        # Not the first iteration
        (7, 47, False),
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

    print(f"The starting energy rate is {considered_energy_rates[0]}")
    assert tibber_api_handler.get_next_price_minimum(first_iteration, considered_energy_rates) == expected_energy_rate
