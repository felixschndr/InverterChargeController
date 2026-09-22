import pytest

from source import environment_variable_getter


@pytest.fixture
def isolated_environment_variables(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setattr(environment_variable_getter, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(environment_variable_getter, "find_dotenv", lambda *args, **kwargs: "")
    return monkeypatch
