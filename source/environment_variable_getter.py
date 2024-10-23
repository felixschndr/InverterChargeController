import os
from typing import Any

from dotenv import load_dotenv


class EnvironmentVariableGetter:
    @staticmethod
    def get(name_of_variable: str, default_value: Any = None) -> str:
        """
        Args:
            name_of_variable: The name of the environment variable to be retrieved.
            default_value: Optional; The default value to return if the environment variable is not set.

        Returns:
            The value of the environment variable cast to a boolean if possible, otherwise returns its string value or the default value.

        Raises:
            RuntimeError: If the environment variable is not set and no default value is provided.
        """
        load_dotenv(override=True)

        try:
            value = os.environ[name_of_variable]
            return EnvironmentVariableGetter._cast_string_to_bool(value)
        except KeyError:
            if default_value is not None:
                return default_value

            raise RuntimeError(f'The environment variable "{name_of_variable}" is not set!')

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
