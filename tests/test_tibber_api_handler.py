import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from source.energy_classes import EnergyRate
from source.tibber_api_handler import TibberAPIHandler


@pytest.fixture
def starting_datetime():
    return datetime.fromtimestamp(0)


@pytest.fixture
def tibber_api_handler():
    tibber_api_handler = TibberAPIHandler()
    for level_name in list(logging.getLevelNamesMapping().keys()) + ["trace"]:
        setattr(tibber_api_handler.log, level_name.lower(), print)
    return tibber_api_handler


def construct_energy_rates(prices: list[float], step: timedelta = timedelta(hours=1)) -> list[EnergyRate]:
    starting_time = datetime.fromtimestamp(0)
    return [EnergyRate(price, starting_time + (index * step)) for index, price in enumerate(prices)]


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
        (6, 13, True),
        (7, 13, True),
        (8, 13, True),
        (10, 13, True),
        (12, 13, True),
        (13, 13, True),
        (14, 14, True),
        (17, 17, True),
        (18, 26, True),
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


@pytest.mark.parametrize(
    "log, first_iteration, expected_time_of_minimum",
    [
        (
            "32.7 ct/kWh at 2025-12-13 14:00:00+01:00, 34.54 ct/kWh at 2025-12-13 15:00:00+01:00, 35.14 ct/kWh at 2025-12-13 16:00:00+01:00, 34.99 ct/kWh at 2025-12-13 17:00:00+01:00, 34.25 ct/kWh at 2025-12-13 18:00:00+01:00, 33.23 ct/kWh at 2025-12-13 19:00:00+01:00, 31.81 ct/kWh at 2025-12-13 20:00:00+01:00, 31.67 ct/kWh at 2025-12-13 21:00:00+01:00, 32.04 ct/kWh at 2025-12-13 22:00:00+01:00, 30.93 ct/kWh at 2025-12-13 23:00:00+01:00, 31.75 ct/kWh at 2025-12-14 00:00:00+01:00, 31.67 ct/kWh at 2025-12-14 01:00:00+01:00, 30.64 ct/kWh at 2025-12-14 02:00:00+01:00, 30.41 ct/kWh at 2025-12-14 03:00:00+01:00, 30.09 ct/kWh at 2025-12-14 04:00:00+01:00, 30.27 ct/kWh at 2025-12-14 05:00:00+01:00, 30.08 ct/kWh at 2025-12-14 06:00:00+01:00, 30.11 ct/kWh at 2025-12-14 07:00:00+01:00, 30.62 ct/kWh at 2025-12-14 08:00:00+01:00, 30.69 ct/kWh at 2025-12-14 09:00:00+01:00, 30.41 ct/kWh at 2025-12-14 10:00:00+01:00, 30.9 ct/kWh at 2025-12-14 11:00:00+01:00, 31.28 ct/kWh at 2025-12-14 12:00:00+01:00, 31.24 ct/kWh at 2025-12-14 13:00:00+01:00, 31.45 ct/kWh at 2025-12-14 14:00:00+01:00, 31.85 ct/kWh at 2025-12-14 15:00:00+01:00, 32.71 ct/kWh at 2025-12-14 16:00:00+01:00, 33.12 ct/kWh at 2025-12-14 17:00:00+01:00, 33.19 ct/kWh at 2025-12-14 18:00:00+01:00, 31.96 ct/kWh at 2025-12-14 19:00:00+01:00, 31.65 ct/kWh at 2025-12-14 20:00:00+01:00, 30.94 ct/kWh at 2025-12-14 21:00:00+01:00, 30.73 ct/kWh at 2025-12-14 22:00:00+01:00, 29.91 ct/kWh at 2025-12-14 23:00:00+01:00",
            False,
            "2025-12-14 06:00:00+01:00",
        ),
        (
            "29.3 ct/kWh at 2025-12-15 03:00:00+01:00, 29.85 ct/kWh at 2025-12-15 04:00:00+01:00, 30.04 ct/kWh at 2025-12-15 05:00:00+01:00, 31.19 ct/kWh at 2025-12-15 06:00:00+01:00, 32.65 ct/kWh at 2025-12-15 07:00:00+01:00, 32.93 ct/kWh at 2025-12-15 08:00:00+01:00, 32.4 ct/kWh at 2025-12-15 09:00:00+01:00, 31.56 ct/kWh at 2025-12-15 10:00:00+01:00, 30.38 ct/kWh at 2025-12-15 11:00:00+01:00, 30.38 ct/kWh at 2025-12-15 12:00:00+01:00, 31.4 ct/kWh at 2025-12-15 13:00:00+01:00, 32.25 ct/kWh at 2025-12-15 14:00:00+01:00, 33.66 ct/kWh at 2025-12-15 15:00:00+01:00, 33.82 ct/kWh at 2025-12-15 16:00:00+01:00, 33.3 ct/kWh at 2025-12-15 17:00:00+01:00, 32.58 ct/kWh at 2025-12-15 18:00:00+01:00, 31.66 ct/kWh at 2025-12-15 19:00:00+01:00, 30.92 ct/kWh at 2025-12-15 20:00:00+01:00, 31.03 ct/kWh at 2025-12-15 21:00:00+01:00, 31.01 ct/kWh at 2025-12-15 22:00:00+01:00, 30.47 ct/kWh at 2025-12-15 23:00:00+01:00",
            False,
            "2025-12-15 11:00:00+01:00",
        ),
        (
            "29.05 ct/kWh at 2025-12-07 21:00:00+01:00, 28.7 ct/kWh at 2025-12-07 22:00:00+01:00, 25.86 ct/kWh at 2025-12-07 23:00:00+01:00, 23.19 ct/kWh at 2025-12-08 00:00:00+01:00, 22.21 ct/kWh at 2025-12-08 01:00:00+01:00, 22.28 ct/kWh at 2025-12-08 02:00:00+01:00, 21.56 ct/kWh at 2025-12-08 03:00:00+01:00, 22.43 ct/kWh at 2025-12-08 04:00:00+01:00, 24.3 ct/kWh at 2025-12-08 05:00:00+01:00, 28.55 ct/kWh at 2025-12-08 06:00:00+01:00, 30.75 ct/kWh at 2025-12-08 07:00:00+01:00, 32.8 ct/kWh at 2025-12-08 08:00:00+01:00, 32.59 ct/kWh at 2025-12-08 09:00:00+01:00, 31.13 ct/kWh at 2025-12-08 10:00:00+01:00, 30.41 ct/kWh at 2025-12-08 11:00:00+01:00, 30.33 ct/kWh at 2025-12-08 12:00:00+01:00, 31.23 ct/kWh at 2025-12-08 13:00:00+01:00, 32.09 ct/kWh at 2025-12-08 14:00:00+01:00, 32.81 ct/kWh at 2025-12-08 15:00:00+01:00, 32.92 ct/kWh at 2025-12-08 16:00:00+01:00, 33.97 ct/kWh at 2025-12-08 17:00:00+01:00, 32.83 ct/kWh at 2025-12-08 18:00:00+01:00, 32.4 ct/kWh at 2025-12-08 19:00:00+01:00, 31.53 ct/kWh at 2025-12-08 20:00:00+01:00, 30.83 ct/kWh at 2025-12-08 21:00:00+01:00, 30.44 ct/kWh at 2025-12-08 22:00:00+01:00, 29.61 ct/kWh at 2025-12-08 23:00:00+01:00",
            False,
            "2025-12-08 12:00:00+01:00",
        ),
        (
            "27.87 ct/kWh at 2025-12-07 03:00:00+01:00, 28.28 ct/kWh at 2025-12-07 04:00:00+01:00, 28.27 ct/kWh at 2025-12-07 05:00:00+01:00, 28.48 ct/kWh at 2025-12-07 06:00:00+01:00, 29.44 ct/kWh at 2025-12-07 07:00:00+01:00, 30.18 ct/kWh at 2025-12-07 08:00:00+01:00, 31.08 ct/kWh at 2025-12-07 09:00:00+01:00, 31.67 ct/kWh at 2025-12-07 10:00:00+01:00, 31.83 ct/kWh at 2025-12-07 11:00:00+01:00, 32.49 ct/kWh at 2025-12-07 12:00:00+01:00, 32.74 ct/kWh at 2025-12-07 13:00:00+01:00, 33.29 ct/kWh at 2025-12-07 14:00:00+01:00, 33.47 ct/kWh at 2025-12-07 15:00:00+01:00, 33.94 ct/kWh at 2025-12-07 16:00:00+01:00, 34.2 ct/kWh at 2025-12-07 17:00:00+01:00, 32.42 ct/kWh at 2025-12-07 18:00:00+01:00, 31.3 ct/kWh at 2025-12-07 19:00:00+01:00, 30.86 ct/kWh at 2025-12-07 20:00:00+01:00, 29.67 ct/kWh at 2025-12-07 21:00:00+01:00, 28.7 ct/kWh at 2025-12-07 22:00:00+01:00, 25.86 ct/kWh at 2025-12-07 23:00:00+01:00",
            False,
            "2025-12-07 23:00:00+01:00",
        ),
        (
            "45.62 ct/kWh at 2025-12-03 14:00:00+01:00, 49.76 ct/kWh at 2025-12-03 15:00:00+01:00, 57.59 ct/kWh at 2025-12-03 16:00:00+01:00, 51.78 ct/kWh at 2025-12-03 17:00:00+01:00, 45.19 ct/kWh at 2025-12-03 18:00:00+01:00, 41.44 ct/kWh at 2025-12-03 19:00:00+01:00, 38.3 ct/kWh at 2025-12-03 20:00:00+01:00, 35.75 ct/kWh at 2025-12-03 21:00:00+01:00, 34.39 ct/kWh at 2025-12-03 22:00:00+01:00, 33.28 ct/kWh at 2025-12-03 23:00:00+01:00, 32.48 ct/kWh at 2025-12-04 00:00:00+01:00, 32.06 ct/kWh at 2025-12-04 01:00:00+01:00, 31.7 ct/kWh at 2025-12-04 02:00:00+01:00, 31.65 ct/kWh at 2025-12-04 03:00:00+01:00, 31.88 ct/kWh at 2025-12-04 04:00:00+01:00, 32.41 ct/kWh at 2025-12-04 05:00:00+01:00, 35.75 ct/kWh at 2025-12-04 06:00:00+01:00, 36.18 ct/kWh at 2025-12-04 07:00:00+01:00, 38.11 ct/kWh at 2025-12-04 08:00:00+01:00, 40.41 ct/kWh at 2025-12-04 09:00:00+01:00, 37.36 ct/kWh at 2025-12-04 10:00:00+01:00, 38.52 ct/kWh at 2025-12-04 11:00:00+01:00, 37.79 ct/kWh at 2025-12-04 12:00:00+01:00, 38.17 ct/kWh at 2025-12-04 13:00:00+01:00, 38.99 ct/kWh at 2025-12-04 14:00:00+01:00, 38.86 ct/kWh at 2025-12-04 15:00:00+01:00, 38.17 ct/kWh at 2025-12-04 16:00:00+01:00, 38.11 ct/kWh at 2025-12-04 17:00:00+01:00, 37.83 ct/kWh at 2025-12-04 18:00:00+01:00, 36.96 ct/kWh at 2025-12-04 19:00:00+01:00, 35.0 ct/kWh at 2025-12-04 20:00:00+01:00, 33.19 ct/kWh at 2025-12-04 21:00:00+01:00, 33.87 ct/kWh at 2025-12-04 22:00:00+01:00, 32.59 ct/kWh at 2025-12-04 23:00:00+01:00",
            False,
            "2025-12-04 03:00:00+01:00",
        ),
        (
            "31.33 ct/kWh at 2025-11-17 14:00:00+01:00, 32.5 ct/kWh at 2025-11-17 15:00:00+01:00, 33.66 ct/kWh at 2025-11-17 16:00:00+01:00, 34.86 ct/kWh at 2025-11-17 17:00:00+01:00, 34.76 ct/kWh at 2025-11-17 18:00:00+01:00, 34.07 ct/kWh at 2025-11-17 19:00:00+01:00, 33.14 ct/kWh at 2025-11-17 20:00:00+01:00, 31.92 ct/kWh at 2025-11-17 21:00:00+01:00, 31.57 ct/kWh at 2025-11-17 22:00:00+01:00, 30.55 ct/kWh at 2025-11-17 23:00:00+01:00, 30.99 ct/kWh at 2025-11-18 00:00:00+01:00, 30.75 ct/kWh at 2025-11-18 01:00:00+01:00, 30.3 ct/kWh at 2025-11-18 02:00:00+01:00, 30.14 ct/kWh at 2025-11-18 03:00:00+01:00, 30.47 ct/kWh at 2025-11-18 04:00:00+01:00, 30.83 ct/kWh at 2025-11-18 05:00:00+01:00, 31.73 ct/kWh at 2025-11-18 06:00:00+01:00, 33.36 ct/kWh at 2025-11-18 07:00:00+01:00, 35.16 ct/kWh at 2025-11-18 08:00:00+01:00, 33.68 ct/kWh at 2025-11-18 09:00:00+01:00, 31.86 ct/kWh at 2025-11-18 10:00:00+01:00, 31.46 ct/kWh at 2025-11-18 11:00:00+01:00, 31.51 ct/kWh at 2025-11-18 12:00:00+01:00, 31.68 ct/kWh at 2025-11-18 13:00:00+01:00, 32.39 ct/kWh at 2025-11-18 14:00:00+01:00, 35.24 ct/kWh at 2025-11-18 15:00:00+01:00, 37.78 ct/kWh at 2025-11-18 16:00:00+01:00, 38.94 ct/kWh at 2025-11-18 17:00:00+01:00, 38.01 ct/kWh at 2025-11-18 18:00:00+01:00, 36.5 ct/kWh at 2025-11-18 19:00:00+01:00, 33.64 ct/kWh at 2025-11-18 20:00:00+01:00, 32.16 ct/kWh at 2025-11-18 21:00:00+01:00, 32.49 ct/kWh at 2025-11-18 22:00:00+01:00, 31.6 ct/kWh at 2025-11-18 23:00:00+01:00",
            False,
            "2025-11-18 03:00:00+01:00",
        ),
    ],
)
def test_get_next_price_minimum_from_logged_energy_rates(
    tibber_api_handler, log, first_iteration, expected_time_of_minimum
):
    result = tibber_api_handler.get_next_price_minimum(first_iteration, _convert_log_to_energy_rates(log))

    assert str(result.timestamp) == expected_time_of_minimum


@pytest.mark.parametrize("first_iteration", [True, False])
def test_debug_get_next_price_minimum_from_logged_energy_rates(tibber_api_handler, first_iteration):
    log = "INSERT_LOG_HERE"

    print(tibber_api_handler.get_next_price_minimum(first_iteration, _convert_log_to_energy_rates(log)))


def _convert_log_to_energy_rates(log: str) -> list[EnergyRate]:
    log_as_array = log.replace("[", "").replace("]", "").split(", ")
    upcoming_energy_rates = []
    for log_entry in log_as_array:
        price, timestamp = log_entry.split(" ct/kWh at ")
        upcoming_energy_rates.append(EnergyRate(float(price), datetime.fromisoformat(timestamp)))
    return upcoming_energy_rates


def test_aggregate_to_hourly_rates(tibber_api_handler):
    quarter_hourly_rates = construct_energy_rates([10, 15, 20, 25, 10, 10, 10, 10.951, 15], timedelta(minutes=15))
    expected_hourly_rates = construct_energy_rates([17.5, 10.24, 15.0], timedelta(hours=1))

    assert tibber_api_handler._aggregate_to_hourly_rates(quarter_hourly_rates) == expected_hourly_rates


def test_get_upcoming_energy_rates_rejects_a_response_that_contains_no_future_rate(tibber_api_handler):
    api_response_with_only_past_rates = {
        "viewer": {
            "homes": [
                {
                    "currentSubscription": {
                        "priceInfo": {
                            "today": [{"total": 0.2962, "startsAt": "2020-01-01T00:00:00.000+01:00"}],
                            "tomorrow": [],
                        }
                    }
                }
            ]
        }
    }

    with (
        patch.object(
            tibber_api_handler, "_fetch_upcoming_prices_from_api", return_value=api_response_with_only_past_rates
        ),
        patch.object(tibber_api_handler, "write_energy_rates_to_database"),
    ):
        with pytest.raises(ValueError, match="none of them is in the future"):
            tibber_api_handler.get_upcoming_energy_rates()


def test_get_energy_rates_around_the_price_spike_rejects_an_ending_timestamp_before_all_rates(
    tibber_api_handler, upcoming_energy_rates
):
    ending_timestamp_before_all_rates = upcoming_energy_rates[0].timestamp - timedelta(hours=1)

    with pytest.raises(ValueError, match="None of the"):
        tibber_api_handler.get_energy_rate_before_and_after_the_price_is_higher_than_the_average_until_timestamp(
            upcoming_energy_rates, ending_timestamp_before_all_rates
        )


FIRST_DAY = datetime(2026, 4, 18, tzinfo=timezone(timedelta(hours=2)))


def construct_rates_for_days(amount_of_days: int) -> list[EnergyRate]:
    return [EnergyRate(30.0, FIRST_DAY + timedelta(hours=hour)) for hour in range(24 * amount_of_days)]


@pytest.mark.parametrize(
    "hour_of_the_minimum, amount_of_days_with_rates, expected_to_need_a_recheck",
    [(23, 1, True), (23, 2, False), (14, 1, False), (0, 1, False)],
)
def test_a_minimum_needs_a_recheck_only_at_the_end_of_a_day_without_rates_for_tomorrow(
    tibber_api_handler, hour_of_the_minimum, amount_of_days_with_rates, expected_to_need_a_recheck
):
    upcoming_energy_rates = construct_rates_for_days(amount_of_days_with_rates)
    price_minimum = EnergyRate(29.0, FIRST_DAY + timedelta(hours=hour_of_the_minimum))

    with patch("source.tibber_api_handler.TimeHandler.get_date", return_value=FIRST_DAY.date()):
        needs_a_recheck = (
            tibber_api_handler._check_if_minimum_is_at_end_of_day_and_energy_rates_of_tomorrow_are_unavailable(
                price_minimum, upcoming_energy_rates
            )
        )

    assert needs_a_recheck is expected_to_need_a_recheck


def test_the_rates_between_the_first_and_second_maximum_start_at_the_first_maximum(tibber_api_handler):
    upcoming_energy_rates = construct_energy_rates([10, 12, 20, 15, 11, 13, 25, 18, 12])

    rates_between_the_maxima = tibber_api_handler._get_energy_rates_between_first_and_second_maximum(
        upcoming_energy_rates
    )

    assert [energy_rate.rate for energy_rate in rates_between_the_maxima] == [20, 15, 11, 13, 25]
    assert rates_between_the_maxima[0] is upcoming_energy_rates[2]


def test_prices_repeating_before_the_first_maximum_do_not_shift_the_starting_point(tibber_api_handler):
    upcoming_energy_rates = construct_energy_rates([10, 10, 20, 15, 10, 13, 25, 18, 12])

    rates_between_the_maxima = tibber_api_handler._get_energy_rates_between_first_and_second_maximum(
        upcoming_energy_rates
    )

    assert rates_between_the_maxima[0] is upcoming_energy_rates[2]


def test_the_rates_between_the_maxima_are_the_whole_list_when_it_holds_a_single_rate(tibber_api_handler):
    upcoming_energy_rates = construct_energy_rates([10])

    assert tibber_api_handler._get_energy_rates_between_first_and_second_maximum(upcoming_energy_rates) == (
        upcoming_energy_rates
    )
