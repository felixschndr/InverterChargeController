import os
from typing import Any

from dotenv import find_dotenv, load_dotenv


class EnvironmentVariableGetter:
    @staticmethod
    def get(name_of_variable: str, default_value: Any = None) -> bool | str:
        """
        Gets the value of an environment variable.

        The method attempts to retrieve the value of the provided environment variable. If the variable exists, it's
        retrieved and, if applicable, converted to a boolean. If the variable doesn't exist, an optional default value
        is returned. If neither the variable is set nor a default value is provided, it raises a RuntimeError.
        The method also processes and gives precedence to variables defined in an `.env.override` file.

        Args:
            name_of_variable (str): The name of the environment variable to query.
            default_value (Any, optional): The fallback value to return if the environment variable is not set.

        Returns:
            bool | str: The retrieved environment variable value, either as a boolean (if applicable) or string.

        Raises:
            RuntimeError: If the specified environment variable is not found and no default value is provided.
        """
        load_dotenv(override=True)

        # Load variables from .env.override with higher priority
        load_dotenv(dotenv_path=find_dotenv(".env.override"), override=True)

        try:
            value = os.environ[name_of_variable]
            if value == "":
                raise KeyError()
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
