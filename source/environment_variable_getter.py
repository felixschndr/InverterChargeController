import os

from dotenv import load_dotenv

load_dotenv()


class EnvironmentVariableGetter:
    @staticmethod
    def get(name_of_variable: str) -> str:
        try:
            return os.environ[name_of_variable]
        except KeyError:
            raise RuntimeError(
                f'The environment variable "{name_of_variable}" is not set!'
            )
