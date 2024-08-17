import os

import pytest

from source.environment_variable_getter import EnvironmentVariableGetter


def test_get_with_existent_variable():
    variable_name = "MY_TEST_VARIABLE"
    variable_content = "my content"

    os.environ[variable_name] = variable_content

    returned_content = EnvironmentVariableGetter.get(variable_name)

    assert returned_content == variable_content


def test_get_with_non_existent_variable():
    with pytest.raises(RuntimeError):
        EnvironmentVariableGetter.get("VARIABLE_THAT_DOES_NOT_EXIST")
