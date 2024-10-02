import logging
import os
from datetime import datetime
from pathlib import Path

from environment_variable_getter import EnvironmentVariableGetter


class LoggerMixin:
    def __init__(self):
        log_directory_user_input = EnvironmentVariableGetter.get("LOGFILE_DIRECTORY")
        path_to_source_folder = os.path.dirname(os.path.realpath(__file__))
        path_to_repository = Path(path_to_source_folder).parent.absolute()
        log_directory = os.path.join(  # noqa: FKA100
            path_to_repository, log_directory_user_input
        )
        if not os.path.exists(log_directory):
            os.makedirs(log_directory)
        logfile_name = (
            f"{log_directory}/{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}.log"
        )

        loglevel = os.environ.get("LOGLEVEL", "INFO").upper()  # noqa: FKA100

        logging.basicConfig(
            format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
            encoding="utf-8",
            level=loglevel,
            filename=logfile_name,
        )

        logging.getLogger("gql.transport.aiohttp").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)

        self.log = logging.getLogger(self.__class__.__name__)
