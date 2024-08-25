from unittest import mock

import pytest

from source.sems_portal_api_handler import SemsPortalApiHandler


def _mock_response(status=200, json_data=None) -> mock.Mock:
    mock_resp = mock.Mock()
    mock_resp.status_code = status
    mock_resp.content = "CONTENT"
    if json_data is not None:
        mock_resp.json = mock.Mock(side_effect=lambda: json_data)
    return mock_resp


@mock.patch("source.sems_portal_api_handler.requests.post")
def test_set_sems_token_and_api(mock_post):
    response_data = {
        "api": "api_url",
        "data": {
            "token": "token_value",
            "timestamp": "timestamp_value",
            "uid": "uid_value",
        },
    }
    mock_post.return_value = _mock_response(status=200, json_data=response_data)

    sems_portal_api_handler = SemsPortalApiHandler()
    sems_portal_api_handler.set_sems_token_and_api()

    assert sems_portal_api_handler.api_url == "api_url"
    assert sems_portal_api_handler.token == "token_value"
    assert sems_portal_api_handler.timestamp == "timestamp_value"
    assert sems_portal_api_handler.user_id == "uid_value"


def test_parse_consumption_response(response_data):
    expected_consumption = pytest.approx(expected=5.7, rel=0.1)

    sems_portal_api_handler = SemsPortalApiHandler()

    assert (
        sems_portal_api_handler._extract_consumption_data_of_response(response_data)
        == expected_consumption
    )
