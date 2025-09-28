import os
import signal
import sys
import threading
from datetime import datetime, time, timedelta
from types import FrameType

import pause
import requests
from requests.exceptions import ReadTimeout
from urllib3.exceptions import ReadTimeoutError

from source.environment_variable_getter import EnvironmentVariableGetter
from source.inverter_charge_controller import InverterChargeController
from source.logger import LoggerMixin
from source.sun_forecast_handler import SunForecastHandler
from source.time_handler import TimeHandler

LOCK_FILE_PATH = "/tmp/inverter_charge_controller.lock"  # nosec B108

logger = LoggerMixin("Main")


def lock() -> None:
    """
    Writes the current process ID to a lock file to indicate the process is active.
    """
    with open(LOCK_FILE_PATH, "w") as lock_file:
        lock_file.write(str(os.getpid()))
    logger.log.trace("Lock file created")


def unlock() -> None:
    """
    Removes the lock file if it exists and thus unlocking the process.
    """
    if not os.path.exists(LOCK_FILE_PATH):
        return

    os.remove(LOCK_FILE_PATH)
    logger.log.trace("Lock file removed")


def write_solar_forecast_and_history_to_db() -> None:
    sun_forecast_handler = SunForecastHandler()

    while True:
        next_wakeup_time = _get_next_wakeup_time()
        logger.log.info(f"Next wakeup time to log solar data of the day is at {next_wakeup_time}")
        pause.until(next_wakeup_time)

        logger.write_newlines_to_log_file()
        logger.log.info("Waking up to log solar data of today")

        try:
            # We call this function instead of retrieve_solar_data to ensure not writing debug data into the DB
            sun_forecast_handler.retrieve_solar_data_from_api(False)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code != 429:
                raise e
            logger.log.warning("Too many requests to the solar forecast API --> unable to log solar forecast data")
        except (TimeoutError, ReadTimeout, ReadTimeoutError):
            logger.log.warning(
                "Timeout while fetching solar forecast data from the API --> unable to log solar forecast data"
            )
        except Exception:
            logger.log.error("Failed to log solar forecast data", exc_info=True)


def _get_next_wakeup_time() -> datetime:
    evening_wakeup_time = time(hour=23, minute=0, second=0, microsecond=0, tzinfo=TimeHandler.get_timezone())
    next_evening_wakeup_time = datetime.combine(TimeHandler.get_date(), evening_wakeup_time)
    if TimeHandler.get_time() >= next_evening_wakeup_time:
        next_evening_wakeup_time += timedelta(days=1)

    return next_evening_wakeup_time


def handle_stop_signal(signal_number: int, _frame: FrameType) -> None:
    """
    Logs the signals SIGINT and SIGTERM and then exits.

    Args:
        signal_number: The number representing the signal received.
        _frame: The current stack frame when the signal was received.
    """
    logger.write_newlines_to_log_file()
    logger.log.info(f"Received {signal.Signals(signal_number).name}. Exiting now...")
    unlock()
    sys.exit(0)


for signal_to_catch in [signal.SIGINT, signal.SIGTERM]:
    signal.signal(signal_to_catch, handle_stop_signal)


if __name__ == "__main__":
    started_by_systemd = " by systemd" if EnvironmentVariableGetter.get("INVOCATION_ID", "") else ""
    if os.path.exists(LOCK_FILE_PATH):
        logger.write_newlines_to_log_file()
        logger.log.warning(
            f"Attempted to start the inverter charge controller{started_by_systemd}, but it is already running."
        )
        sys.exit(1)

    try:
        logger.write_newlines_to_log_file()
        logger.log.info(f"Starting application{started_by_systemd}")
        lock()

        solar_protocol_thread = threading.Thread(target=write_solar_forecast_and_history_to_db, daemon=True)
        solar_protocol_thread.start()

        # Let the thread calculate and log its next wakeup time before logging all the info of the InverterChargeController
        pause.seconds(2)

        inverter_charge_controller = InverterChargeController()
        inverter_charge_controller_thread = threading.Thread(target=inverter_charge_controller.start)
        inverter_charge_controller_thread.start()
        inverter_charge_controller_thread.join()
    finally:
        unlock()
