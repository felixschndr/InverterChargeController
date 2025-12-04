from datetime import timedelta
from unittest.mock import patch

import pytest

from source.time_handler import TimeHandler


@pytest.fixture
def time_handler():
    return TimeHandler()


def test_get_random_duration(time_handler):
    min_duration = timedelta(minutes=10)
    max_duration = timedelta(minutes=20)

    with patch("source.time_handler.randint", return_value=15):
        duration = time_handler.get_random_duration(min_duration, max_duration)

    assert duration == min_duration + timedelta(seconds=15)
