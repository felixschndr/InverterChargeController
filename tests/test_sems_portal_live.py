import os
from unittest.mock import Mock

import pytest
from dotenv import dotenv_values, find_dotenv

from source.sems_portal_api_handler import SemsPortalApiHandler

pytestmark = pytest.mark.skipif(
    not os.environ.get("SEMSPORTAL_LIVE_TEST"), reason="hits the real SEMS+ API, set SEMSPORTAL_LIVE_TEST=1 to run"
)


@pytest.fixture
def handler(monkeypatch: pytest.MonkeyPatch) -> SemsPortalApiHandler:
    # conftest.py sets dummy credentials, the real ones come from the .env file
    real_values = dotenv_values(find_dotenv(".env"))
    for name in ("SEMSPORTAL_USERNAME", "SEMSPORTAL_PASSWORD", "SEMSPORTAL_POWERSTATION_ID"):
        monkeypatch.setenv(name, real_values[name])
    handler = SemsPortalApiHandler()
    handler.database_handler = Mock()
    return handler


def test_energy_buy(handler):
    energy_bought_today, energy_bought_yesterday = handler.get_energy_buy(), handler.get_energy_buy(1)
    print("Energy bought today:", energy_bought_today, "yesterday:", energy_bought_yesterday)

    assert energy_bought_yesterday.watt_hours > 0
