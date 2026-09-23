import os

import pytest

from source.environment_variable_getter import EnvironmentVariableGetter

NAME = "A_VARIABLE_THAT_IS_ONLY_USED_IN_THIS_TEST"


@pytest.fixture
def dotenv_files(tmp_path, monkeypatch):
    def write(env: str = "", env_override: str = "") -> None:
        (tmp_path / ".env").write_text(env)
        (tmp_path / ".env.override").write_text(env_override)
        monkeypatch.setattr(
            "source.environment_variable_getter._get_paths_of_dotenv_files",
            lambda: (str(tmp_path / ".env.override"), str(tmp_path / ".env")),
        )

    return write


def test_the_process_environment_wins_over_the_files(dotenv_files, monkeypatch):
    dotenv_files(env=f"{NAME}=from_env_file", env_override=f"{NAME}=from_override_file")
    monkeypatch.setenv(NAME, "from_process_environment")

    assert EnvironmentVariableGetter.get(NAME) == "from_process_environment"


def test_the_override_file_wins_over_the_env_file(dotenv_files):
    dotenv_files(env=f"{NAME}=from_env_file", env_override=f"{NAME}=from_override_file")

    assert EnvironmentVariableGetter.get(NAME) == "from_override_file"


def test_a_value_of_a_file_does_not_leak_into_the_process_environment(dotenv_files):
    dotenv_files(env=f"{NAME}=from_env_file")

    assert EnvironmentVariableGetter.get(NAME) == "from_env_file"
    assert NAME not in os.environ


def test_an_unset_variable_falls_back_to_the_default_value(dotenv_files):
    dotenv_files()

    assert EnvironmentVariableGetter.get(NAME, "the_default") == "the_default"


def test_an_unset_variable_without_a_default_value_raises(dotenv_files):
    dotenv_files()

    with pytest.raises(ValueError, match=NAME):
        EnvironmentVariableGetter.get(NAME)
