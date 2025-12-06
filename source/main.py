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
# The rate limit for the solar forecast is shared with all free users
# Thus, we wake up a few minutes before/after the new hour to not run into the rate limit
SOLAR_FORECAST_Check_OFFSET = timedelta(minutes=8)

logger = LoggerMixin("Main")


def lock() -> None:
    with open(LOCK_FILE_PATH, "w") as lock_file:
        lock_file.write(str(os.getpid()))
    logger.log.trace("Lock file created")


def unlock() -> None:
    if not os.path.exists(LOCK_FILE_PATH):
        return

    os.remove(LOCK_FILE_PATH)
    logger.log.trace("Lock file removed")


def write_solar_forecast_and_history_to_db() -> None:
    sun_forecast_handler = SunForecastHandler()
    morning_time = time(hour=4, minute=52, second=0, microsecond=0, tzinfo=TimeHandler.get_timezone())
    evening_time = time(hour=23, minute=8, second=0, microsecond=0, tzinfo=TimeHandler.get_timezone())

    while True:
        next_wakeup_time = _get_next_wakeup_time(morning_time, evening_time)
        logger.log.info(f"Next wakeup time to log solar data of the day is at {next_wakeup_time}")
        pause.until(next_wakeup_time)

        logger.write_newlines_to_log_file()
        logger.log.info("Waking up to log solar data of today")

        try:
            # We call this function instead of retrieve_solar_data to ensure not writing debug data into the DB
            need_to_retrieve_future_data = next_wakeup_time.hour == morning_time.hour
            sun_forecast_handler.retrieve_solar_data_from_api(need_to_retrieve_future_data)
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


def _get_morning_and_evening_timestamp_of_today(morning_time: time, evening_time: time) -> tuple[datetime, datetime]:
    today = TimeHandler.get_date()
    return datetime.combine(today, morning_time), datetime.combine(today, evening_time)


def _get_next_wakeup_time(morning_time: time, evening_time: time) -> datetime:
    now = TimeHandler.get_time()
    next_morning_wakeup_time, next_evening_wakeup_time = _get_morning_and_evening_timestamp_of_today(
        morning_time, evening_time
    )
    if now >= next_morning_wakeup_time:
        next_morning_wakeup_time += timedelta(days=1)
    if now >= next_evening_wakeup_time:
        next_evening_wakeup_time += timedelta(days=1)

    if next_morning_wakeup_time - now < next_evening_wakeup_time - now:
        return next_morning_wakeup_time
    else:
        return next_evening_wakeup_time


def handle_stop_signal(signal_number: int, _frame: FrameType) -> None:
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
