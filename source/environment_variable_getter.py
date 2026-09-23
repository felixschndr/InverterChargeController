import os
from functools import cache
from typing import Any, Optional

from dotenv import dotenv_values, find_dotenv


@cache
def _get_paths_of_dotenv_files() -> tuple[str, ...]:
    return tuple(path_of_file for path_of_file in (find_dotenv(".env.override"), find_dotenv(".env")) if path_of_file)


class EnvironmentVariableGetter:
    @staticmethod
    def get(name_of_variable: str, default_value: Any = None) -> bool | str:
        """
        Gets the value of an environment variable.

        The value is looked up in the process environment first, then in an `.env.override` file and finally in the
        `.env` file. If none of them does, an optional default value is returned; without one, a ValueError is raised.

        Args:
            name_of_variable (str): The name of the environment variable to query.
            default_value (Any, optional): The fallback value to return if the environment variable is not set.

        Returns:
            bool | str: The retrieved environment variable value, either as a boolean (if applicable) or string.

        Raises:
            ValueError: If the specified environment variable is not found and no default value is provided.
        """
        value = EnvironmentVariableGetter._read_value(name_of_variable)
        if value:
            return EnvironmentVariableGetter._cast_string_to_bool(value)

        if default_value is not None:
            return default_value

        raise ValueError(f'The environment variable "{name_of_variable}" is not set!')

    @staticmethod
    def _read_value(name_of_variable: str) -> Optional[str]:
        sources = [os.environ, *(dotenv_values(path_of_file) for path_of_file in _get_paths_of_dotenv_files())]
        for source in sources:
            value = source.get(name_of_variable)
            if value:
                return value

        return None

    @staticmethod
    def _cast_string_to_bool(value: str) -> bool | str:
        """
        Args:
            value: A string that may represent a boolean value.

        Returns:
            bool | str: The boolean value corresponding to the input string if it's "True" or "False".
            Otherwise, returns the input string.
        """
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        return value
