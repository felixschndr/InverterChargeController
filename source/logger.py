import logging
import os
import pathlib
from logging.handlers import RotatingFileHandler

from environment_variable_getter import EnvironmentVariableGetter


class LoggerMixin:
    """
    A mixin to set up and manage logging for a class.

    Any class can inherit from this and then call self.log.{debug,info,warning,error,critical} to log.
    """

    def __init__(self):
        root_logger = logging.getLogger()
        if len(root_logger.handlers) == 0:
            self._set_logger(root_logger)

        self.log = logging.getLogger(self.__class__.__name__)

    def _set_logger(self, root_logger: logging.Logger) -> None:
        """
        Args:
            root_logger: The root logger instance where handlers and formatters will be added.

        The function sets up the logging configuration for the application.
        It determines the directory paths for logs, ensures the logging directory exists,
        and configures a rotating file handler with a specific log level and format.
        """
        directory_of_repository = pathlib.Path(__file__).parent.parent.resolve()
        directory_of_logs_default_value = os.path.join(directory_of_repository, "logs")

        directory_of_logs = EnvironmentVariableGetter.get(
            name_of_variable="DIRECTORY_OF_LOGS",
            default_value=directory_of_logs_default_value,
        )
        self._create_logging_directory_if_necessary(directory_of_logs)

        log_level = EnvironmentVariableGetter.get(
            name_of_variable="LOGLEVEL", default_value="INFO"
        ).upper()
        environment = EnvironmentVariableGetter.get("ENVIRONMENT", "")
        environment = f"_{environment}" if environment else ""

        handler = RotatingFileHandler(
            os.path.join(directory_of_logs, f"app{environment}.log"),
            maxBytes=1024 * 1024,
            backupCount=7,
        )
        handler.setLevel(log_level)

        formatter = logging.Formatter(
            "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
        handler.setFormatter(formatter)

        root_logger.addHandler(handler)
        root_logger.setLevel(log_level)

        self._add_trace_loglevel()
        self._set_log_levels_of_libraries()

    @staticmethod
    def _add_trace_loglevel() -> None:
        trace_level_number = logging.DEBUG - 5
        logging.addLevelName(trace_level_number, "TRACE")

        def trace(
            self, message, *args, **kwargs  # noqa: ANN001, ANN002, ANN003
        ):  # noqa: ANN201
            if self.isEnabledFor(trace_level_number):
                self._log(trace_level_number, message, args, **kwargs)

        logging.Logger.trace = trace

    @staticmethod
    def _set_log_levels_of_libraries() -> None:
        """
        A static method to set the logging level for specific third-party libraries to be less verbose.
        """
        logging.getLogger("gql.transport.aiohttp").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        logging.getLogger("goodwe").setLevel(logging.INFO)
        logging.getLogger("goodwe.protocol").setLevel(logging.INFO)

    @staticmethod
    def _create_logging_directory_if_necessary(directory_of_logs: str) -> None:
        if os.path.exists(directory_of_logs):
            return

        print(f"Creating directory for logs {directory_of_logs}")
        os.mkdir(directory_of_logs)
