import logging
import sys

from environment_variable_getter import EnvironmentVariableGetter


class LoggerMixin:
    def __init__(self):
        loglevel = EnvironmentVariableGetter.get(
            name_of_variable="LOGLEVEL", default_value="INFO"
        ).upper()
        logging.basicConfig(
            format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
            encoding="utf-8",
            level=loglevel,
            stream=sys.stdout,
        )

        logging.getLogger("gql.transport.aiohttp").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)

        self.log = logging.getLogger(self.__class__.__name__)
