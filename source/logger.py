import logging
import os
import pathlib
from logging.handlers import RotatingFileHandler

from environment_variable_getter import EnvironmentVariableGetter


class RotatingFileHandlerWithPermissions(RotatingFileHandler):
    """
    A RotatingFileHandler subclass with custom file permissions.

    This class extends the functionality of RotatingFileHandler to include setting
    specific permissions for the rotated log files. It ensures that after a log file is
    rolled over, all users have the permissions to read and write to it.
    """

    def doRollover(self) -> None:
        super().doRollover()
        self.set_permissions(self.baseFilename)

    @staticmethod
    def set_permissions(file_path: str) -> None:
        os.chmod(file_path, 0o666)  # nosec: B103


class LoggerMixin:
    """
    A mixin to set up and manage logging for a class.

    Any class can inherit from this and then call self.log.{trace,debug,info,warning,error,critical} to log.
    Notice that the loglevel trace with a weight of 5 was added.
    """

    def __init__(self, logger_name: str = None):
        root_logger = logging.getLogger()
        if len(root_logger.handlers) == 0:
            self._set_logger(root_logger)

        if not logger_name:
            logger_name = self.__class__.__name__
        self.log = logging.getLogger(logger_name)

    def _set_logger(self, root_logger: logging.Logger) -> None:
        """
        Args:
            root_logger: The root logger instance where handlers and formatters will be added.

        The function sets up the logging configuration for the application.
        It determines the directory paths for logs, ensures the logging directory exists,
        and configures a rotating file handler with a specific log level and format.
        """
        self._add_trace_loglevel()
        self._set_log_levels_of_libraries()

        directory_of_repository = pathlib.Path(__file__).parent.parent.resolve()
        directory_of_logs_default_value = os.path.join(directory_of_repository, "logs")

        self._directory_of_logs = EnvironmentVariableGetter.get(
            name_of_variable="DIRECTORY_OF_LOGS",
            default_value=directory_of_logs_default_value,
        )
        self._create_logging_directory_if_necessary(self._directory_of_logs)

        log_level = EnvironmentVariableGetter.get(name_of_variable="LOGLEVEL", default_value="INFO").upper()

        instance_id = os.getpid()
        formatter = logging.Formatter(
            f"[%(asctime)s] [{instance_id}] [%(name)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )

        file_handler = RotatingFileHandlerWithPermissions(
            os.path.join(self._directory_of_logs, "app.log"),
            maxBytes=1024 * 1024,
            backupCount=7,
        )

        handlers = [file_handler]
        if EnvironmentVariableGetter.get("PRINT_TO_STDOUT", True):
            handlers.append(logging.StreamHandler())
        for handler in handlers:
            handler.setFormatter(formatter)
            handler.setLevel(log_level)
            root_logger.addHandler(handler)

        root_logger.setLevel(log_level)

    @staticmethod
    def _add_trace_loglevel() -> None:
        """
        Adds a custom TRACE log level, which is below the DEBUG level
        """
        trace_level_number = logging.DEBUG - 5
        logging.addLevelName(trace_level_number, "TRACE")

        def trace(self, message, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN201
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
        logging.getLogger("tzlocal").setLevel(logging.INFO)

    @staticmethod
    def _create_logging_directory_if_necessary(directory_of_logs: str) -> None:
        """
        Args:
            directory_of_logs: The path to the directory where log files will be stored. If the directory does not already exist, it will be created.
        """
        if os.path.exists(directory_of_logs):
            return

        print(f"Creating directory for logs {directory_of_logs}")
        os.mkdir(directory_of_logs)

    def write_newlines_to_log_file(self, amount_of_newlines: int = 2) -> None:
        """
        Writes the specified number of newline characters to the log file without a timestamp or loglevel.

        Args:
            amount_of_newlines: Number of newline characters to write. Default is 2.
        """
        self.log.parent.handlers[0].stream.write("".join("\n" for _ in range(amount_of_newlines)))

    @property
    def directory_of_logs(self) -> str:
        return self._directory_of_logs
