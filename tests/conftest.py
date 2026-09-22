import os

import pytest

dummy = "dummy"

for name, value in {
    "INVERTER_BATTERY_CAPACITY": "10000",
    "INVERTER_HOSTNAME": "192.0.2.1",
    "TIBBER_API_TOKEN": dummy,
    "SEMSPORTAL_USERNAME": dummy,
    "SEMSPORTAL_PASSWORD": dummy,
    "SEMSPORTAL_POWERSTATION_ID": dummy,
    "SOLCAST_API_KEY": dummy,
    "ROOFTOP_ID_1": dummy,
    "LATITUDE": "48.1",
    "LONGITUDE": "11.5",
    "INFLUXDB_TOKEN": dummy,
}.items():
    os.environ.setdefault(name, value)

from source import environment_variable_getter  # noqa: E402


@pytest.fixture
def isolated_environment_variables(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setattr(environment_variable_getter, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(environment_variable_getter, "find_dotenv", lambda *args, **kwargs: "")
    return monkeypatch
