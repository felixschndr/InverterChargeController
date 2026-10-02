import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from source.energy_classes import EnergyAmount
from source.sems_portal_api_handler import SemsPortalApiHandler

TIMEZONE = timezone(timedelta(hours=2))
TODAY = date(2026, 4, 18)


@pytest.fixture
def handler() -> SemsPortalApiHandler:
    handler = SemsPortalApiHandler()
    handler.database_handler = Mock()
    handler._retrieve_power_data = Mock(return_value={"dataList": []})
    return handler


def power_data(*points: tuple[str, float | None, float, float, float, int]) -> dict:
    return {
        "dataList": [
            {"item": item, "powerData": [{"tp": point[0], "power": point[index + 1]} for point in points]}
            for index, item in enumerate(("pSystem", "pBat", "pGrid", "pConsum", "soc"))
        ]
    }


def crawled_dates(handler: SemsPortalApiHandler) -> list[date]:
    return [call.args[0] for call in handler._retrieve_power_data.call_args_list]


def written_values(handler: SemsPortalApiHandler) -> list[dict]:
    return [
        {field.name: field.value for field in call.args[0]}
        for call in handler.database_handler.write_to_database.call_args_list
    ]


def write_values_with_newest_saved_value_from(handler: SemsPortalApiHandler, newest_saved_timestamp: datetime) -> None:
    handler.database_handler.get_newest_value_of_measurement.return_value = newest_saved_timestamp
    with (
        patch("source.sems_portal_api_handler.TimeHandler.get_date", return_value=TODAY),
        patch("source.sems_portal_api_handler.TimeHandler.get_timezone", return_value=TIMEZONE),
    ):
        handler.write_values_to_database()


def api_response(code: str, data: dict | None = None) -> Mock:
    response = Mock()
    response.json.return_value = {"code": code, "description": "some description", "data": data}
    return response


def test_the_password_is_sent_as_base64_of_its_md5_hex_digest():
    assert SemsPortalApiHandler._hash_password("my-secret-password") == "YTJkOTY3OWM3ZmZmM2U5Y2Y0MzAwYTJjYzNmYmFkNzk="


def test_the_signature_is_base64_of_the_sha256_of_timestamp_uid_and_token_followed_by_the_timestamp():
    with patch("source.sems_portal_api_handler.time_module.time", return_value=1790960592.073):
        signature = SemsPortalApiHandler._signature("some-uid", "some-token")

    assert signature == (
        "YzA2MzRmYWJjMTVhMzc4OTBhYTNlMzIxYWM4YjNmODI0NDE0NTA0ODlhYTAwNzU0OTNhOTMzYTlkODI3NzZiNEAxNzkwOTYwNTkyMDcz"
    )


def test_a_request_logs_in_and_sends_the_login_response_as_token_to_the_returned_api():
    login_data = {"uid": "some-uid", "token": "some-token", "api": "https://gateway.example/web/sems"}  # nosec B105

    with patch(
        "source.sems_portal_api_handler.requests.post",
        side_effect=[api_response("00000", login_data), api_response("00000", {"some": "data"})],
    ) as post:
        data = SemsPortalApiHandler()._request("/some/path", {"some": "payload"})

    assert data == {"some": "data"}
    login_call, request_call = post.call_args_list
    assert login_call.args[0] == SemsPortalApiHandler.LOGIN_URL
    assert request_call.args[0] == "https://gateway.example/web/sems/some/path"
    assert json.loads(request_call.kwargs["headers"]["token"]) == login_data
    assert request_call.kwargs["json"] == {"some": "payload"}


def test_an_error_code_of_the_api_raises_an_error():
    with patch("source.sems_portal_api_handler.requests.post", return_value=api_response("100004")):
        with pytest.raises(RuntimeError, match="100004"):
            SemsPortalApiHandler()._login()


@pytest.mark.parametrize("days_in_past, expected_day", [(0, "2026-04-18"), (1, "2026-04-17")])
def test_the_energy_bought_on_the_requested_day_is_returned(handler, days_in_past, expected_day):
    handler._request = Mock(
        return_value={
            "dataList": [{"item": "proPurchaseStats", "statisticsList": [{"date": expected_day, "val": 2.78}]}]
        }
    )

    with patch("source.sems_portal_api_handler.TimeHandler.get_date", return_value=TODAY):
        energy_bought = handler.get_energy_buy(days_in_past)

    assert energy_bought == EnergyAmount(2780)
    payload = handler._request.call_args.args[1]
    assert (payload["startTime"], payload["endTime"]) == (f"{expected_day} 00:00:00", f"{expected_day} 23:59:59")


def test_no_data_is_crawled_when_the_database_is_unreachable(handler):
    handler.database_handler.get_newest_value_of_measurement.return_value = None

    with patch("source.sems_portal_api_handler.TimeHandler.get_date", return_value=TODAY):
        handler.write_values_to_database()

    assert crawled_dates(handler) == []


def test_only_today_is_crawled_when_the_database_is_up_to_date(handler):
    write_values_with_newest_saved_value_from(handler, datetime(2026, 4, 18, 9, 0, tzinfo=TIMEZONE))

    assert crawled_dates(handler) == [TODAY]


def test_every_day_since_the_newest_saved_value_is_crawled(handler):
    write_values_with_newest_saved_value_from(handler, datetime(2026, 4, 15, 23, 55, tzinfo=TIMEZONE))

    assert crawled_dates(handler) == [
        date(2026, 4, 18),
        date(2026, 4, 17),
        date(2026, 4, 16),
        date(2026, 4, 15),
    ]


def test_the_amount_of_crawled_days_is_capped_at_a_month(handler):
    write_values_with_newest_saved_value_from(handler, datetime(2024, 1, 1, 0, 0, tzinfo=TIMEZONE))

    assert len(crawled_dates(handler)) == 32
    assert crawled_dates(handler)[0] == TODAY


def test_the_power_values_are_written_in_watts_with_charge_and_usage_counted_as_positive(handler):
    handler._retrieve_power_data.return_value = power_data(("2026-04-18 12:00:00", 4.16429, -4.07592, 0.193, 0.0, 26))

    write_values_with_newest_saved_value_from(handler, datetime(2026, 4, 18, 9, 0, tzinfo=TIMEZONE))

    assert written_values(handler) == [
        {
            "solar_generation_in_watts": 4164,
            "battery_charge_in_watts": 4076,
            "grid_usage_in_watts": -193,
            "power_usage_in_watts": 0,
            "state_of_charge_in_percent": 26,
            "timestamp": "2026-04-18T12:00:00+02:00",
        }
    ]


def test_only_values_newer_than_the_newest_saved_one_and_not_in_the_future_are_written(handler):
    handler._retrieve_power_data.return_value = power_data(
        ("2026-04-18 08:55:00", 0.1, 0, 0, 0.1, 10),  # already saved
        ("2026-04-18 09:00:00", 0.1, 0, 0, 0.1, 10),  # already saved
        ("2026-04-18 09:05:00", 0.2, 0, 0, 0.2, 10),
        ("2026-04-18 09:10:00", None, None, None, None, None),  # in the future
    )

    write_values_with_newest_saved_value_from(handler, datetime(2026, 4, 18, 9, 0, tzinfo=TIMEZONE))

    assert [values["timestamp"] for values in written_values(handler)] == ["2026-04-18T09:05:00+02:00"]


@pytest.mark.parametrize(
    "unusable_response",
    [
        {"dataList": []},  # the response when the "timeZone" parameter is missing
        {"dataList": None},
        {"dataList": [{"item": "pSystem"}]},
        None,
        RuntimeError("There was a problem with the SEMS+ API"),
    ],
)
def test_a_day_the_api_holds_no_power_data_for_is_skipped(handler, unusable_response):
    handler._retrieve_power_data.side_effect = (
        unusable_response if isinstance(unusable_response, Exception) else lambda _: unusable_response
    )

    write_values_with_newest_saved_value_from(handler, datetime(2026, 4, 16, 9, 0, tzinfo=TIMEZONE))

    # Every day is still crawled, the unusable ones are skipped instead of ending the iteration
    assert crawled_dates(handler) == [TODAY, date(2026, 4, 17), date(2026, 4, 16)]
    handler.database_handler.write_to_database.assert_not_called()
