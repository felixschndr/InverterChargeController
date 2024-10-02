import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()


class EnvironmentVariableGetter:
    @staticmethod
    def get(name_of_variable: str, default_value: Any = None) -> str:
        try:
            return os.environ[name_of_variable]
        except KeyError:
            if default_value is not None:
                return default_value

            raise RuntimeError(
                f'The environment variable "{name_of_variable}" is not set!'
            )
