from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from source.sems_portal_api_handler import SemsPortalApiHandler

TIMEZONE = timezone(timedelta(hours=2))
TODAY = date(2026, 4, 18)


@pytest.fixture
def handler_stub() -> Mock:
    handler_stub = Mock()
    handler_stub._retrieve_power_data.return_value = {"data": {"lines": [{"xy": []}]}}
    return handler_stub


def crawled_dates(handler_stub: Mock) -> list[date]:
    return [call.args[0] for call in handler_stub._retrieve_power_data.call_args_list]


def write_values_with_newest_saved_value_from(handler_stub: Mock, newest_saved_timestamp: datetime) -> None:
    handler_stub.database_handler.get_newest_value_of_measurement.return_value = newest_saved_timestamp
    with patch("source.sems_portal_api_handler.TimeHandler.get_date", return_value=TODAY):
        SemsPortalApiHandler.write_values_to_database(handler_stub)


def test_no_data_is_crawled_when_the_database_is_unreachable(handler_stub):
    handler_stub.database_handler.get_newest_value_of_measurement.return_value = None

    with patch("source.sems_portal_api_handler.TimeHandler.get_date", return_value=TODAY):
        SemsPortalApiHandler.write_values_to_database(handler_stub)

    assert crawled_dates(handler_stub) == []


def test_only_today_is_crawled_when_the_database_is_up_to_date(handler_stub):
    write_values_with_newest_saved_value_from(handler_stub, datetime(2026, 4, 18, 9, 0, tzinfo=TIMEZONE))

    assert crawled_dates(handler_stub) == [TODAY]


def test_every_day_since_the_newest_saved_value_is_crawled(handler_stub):
    write_values_with_newest_saved_value_from(handler_stub, datetime(2026, 4, 15, 23, 55, tzinfo=TIMEZONE))

    assert crawled_dates(handler_stub) == [
        date(2026, 4, 18),
        date(2026, 4, 17),
        date(2026, 4, 16),
        date(2026, 4, 15),
    ]


def test_the_amount_of_crawled_days_is_capped_at_a_month(handler_stub):
    write_values_with_newest_saved_value_from(handler_stub, datetime(2024, 1, 1, 0, 0, tzinfo=TIMEZONE))

    assert len(crawled_dates(handler_stub)) == 32
    assert crawled_dates(handler_stub)[0] == TODAY


@pytest.mark.parametrize(
    "unusable_response",
    [
        {"data": {"lines": [{"xy": None}]}},  # the response that crashed the controller on 2026-09-23
        {"data": {"lines": [{}]}},
        {"data": {"lines": []}},
        {"data": {"lines": None}},
        {"data": None},
    ],
)
def test_a_day_the_api_holds_no_power_data_for_is_skipped(handler_stub, unusable_response):
    handler_stub._retrieve_power_data.return_value = unusable_response

    write_values_with_newest_saved_value_from(handler_stub, datetime(2026, 4, 16, 9, 0, tzinfo=TIMEZONE))

    # Every day is still crawled, the unusable ones are skipped instead of ending the iteration
    assert crawled_dates(handler_stub) == [TODAY, date(2026, 4, 17), date(2026, 4, 16)]
    handler_stub.database_handler.write_to_database.assert_not_called()
