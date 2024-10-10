import logging
import os
import pathlib
from datetime import datetime

from environment_variable_getter import EnvironmentVariableGetter


class LoggerMixin:
    def __init__(self):
        directory_of_repository = pathlib.Path(__file__).parent.parent.resolve()
        directory_of_logs = os.path.join(directory_of_repository, "logs")
        logfile_name = datetime.now().strftime("%Y-%m-%d.log")
        logfile_path = os.path.join(directory_of_logs, logfile_name)

        self._create_logging_directory_if_necessary(directory_of_logs)

        log_message_format = "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"

        loglevel = EnvironmentVariableGetter.get(
            name_of_variable="LOGLEVEL", default_value="INFO"
        ).upper()

        logging.basicConfig(
            format=log_message_format,
            encoding="utf-8",
            level=loglevel,
            filename=logfile_path,
        )

        self._set_log_levels_of_libraries()

        self.log = logging.getLogger(self.__class__.__name__)

    @staticmethod
    def _set_log_levels_of_libraries() -> None:
        logging.getLogger("gql.transport.aiohttp").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)

    @staticmethod
    def _create_logging_directory_if_necessary(directory_of_logs: str) -> None:
        if os.path.exists(directory_of_logs):
            return

        print(f"Creating directory for logs {directory_of_logs}")
        os.mkdir(directory_of_logs)
