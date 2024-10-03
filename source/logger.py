import logging
import sys

from environment_variable_getter import EnvironmentVariableGetter


class LoggerMixin:
    def __init__(self):
        print_timestamp_in_log = bool(
            EnvironmentVariableGetter.get(
                name_of_variable="PRINT_TIMESTAMP_IN_LOG", default_value=True
            )
        )
        log_message_format = "[%(asctime)s] " if print_timestamp_in_log else ""
        log_message_format += "[%(name)s] [%(levelname)s] %(message)s"

        loglevel = EnvironmentVariableGetter.get(
            name_of_variable="LOGLEVEL", default_value="INFO"
        ).upper()

        logging.basicConfig(
            format=log_message_format,
            encoding="utf-8",
            level=loglevel,
            stream=sys.stdout,
        )

        logging.getLogger("gql.transport.aiohttp").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)

        self.log = logging.getLogger(self.__class__.__name__)
