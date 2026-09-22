from datetime import datetime
from unittest.mock import patch

import pytest

from source.abscence_handler import AbsenceHandler

ABSENCE_TIMEFRAME = "2026-04-18T06:00:00+0200;2026-04-25T07:00:00+0200"


@pytest.fixture
def absence_handler_factory(isolated_environment_variables: pytest.MonkeyPatch):
    def create_absence_handler(configured_timeframe: str | None) -> AbsenceHandler:
        if configured_timeframe is None:
            isolated_environment_variables.delenv("ABSENCE_TIMEFRAME", raising=False)
        else:
            isolated_environment_variables.setenv("ABSENCE_TIMEFRAME", configured_timeframe)
        return AbsenceHandler()

    return create_absence_handler


@pytest.mark.parametrize("configured_timeframe", [None, "", "   "])
def test_absence_handler_without_configured_timeframe_reports_no_absence(
    absence_handler_factory, configured_timeframe
):
    absence_handler = absence_handler_factory(configured_timeframe)

    assert absence_handler.absence_start is None
    assert absence_handler.absence_end is None
    assert absence_handler.currently_is_an_absence() is False


@pytest.mark.parametrize(
    "current_time, expected_to_be_an_absence",
    [
        (datetime.fromisoformat("2026-04-17T23:59:00+02:00"), False),
        (datetime.fromisoformat("2026-04-18T06:00:00+02:00"), False),
        (datetime.fromisoformat("2026-04-20T12:00:00+02:00"), True),
        (datetime.fromisoformat("2026-04-25T07:00:00+02:00"), False),
        (datetime.fromisoformat("2026-04-26T00:00:00+02:00"), False),
    ],
)
def test_absence_handler_reports_an_absence_only_inside_the_configured_timeframe(
    absence_handler_factory, current_time, expected_to_be_an_absence
):
    absence_handler = absence_handler_factory(ABSENCE_TIMEFRAME)

    with patch("source.abscence_handler.TimeHandler.get_time", return_value=current_time):
        assert absence_handler.currently_is_an_absence() is expected_to_be_an_absence


@pytest.mark.parametrize(
    "malformed_timeframe",
    [
        "2026-04-18T06:00:00+0200",
        "2026-04-18T06:00:00+0200;2026-04-25T07:00:00+0200;2026-04-30T07:00:00+0200",
        "2026-04-18T06:00:00;2026-04-25T07:00:00",
        "2026-04-18T06:00:00+0200;not-a-timestamp",
    ],
)
def test_absence_handler_rejects_a_malformed_timeframe_with_a_value_error(
    absence_handler_factory, malformed_timeframe
):
    with pytest.raises(ValueError):
        absence_handler_factory(malformed_timeframe)
