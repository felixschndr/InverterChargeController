import signal
import sys
import threading
from datetime import datetime, time, timedelta
from types import FrameType

import pause
from energy_classes import Power, StateOfCharge
from inverter_charge_controller import InverterChargeController
from logger import LoggerMixin
from sun_forecast_handler import SunForecastHandler
from time_handler import TimeHandler

logger = LoggerMixin()


def log_solar_forecast() -> None:
    sun_forecast_handler = SunForecastHandler()
    morning_time = time(hour=5, minute=0, second=0, microsecond=0, tzinfo=TimeHandler.get_timezone())
    evening_time = time(hour=23, minute=0, second=0, microsecond=0, tzinfo=TimeHandler.get_timezone())
    while True:
        next_wakeup_time = _get_next_wakeup_time(morning_time, evening_time)
        logger.log.info(f"Next wakeup time to log solar forecast data is at {next_wakeup_time}")
        logger.write_newlines_to_log_file(2)
        pause.until(next_wakeup_time)

        start, end = _get_morning_and_evening_timestamp_of_today(morning_time, evening_time)
        logger.log.info(f"Waking up to log solar forecast data from {start} to {end}")
        if TimeHandler.get_time().hour == morning_time.hour:
            start += timedelta(minutes=2)
        else:
            end -= timedelta(minutes=2)

        sun_forecast_handler.calculate_minimum_of_soc_and_power_generation_in_timeframe(
            start, end, Power(0), StateOfCharge.from_percentage(0)
        )


def _get_morning_and_evening_timestamp_of_today(morning_time: time, evening_time: time) -> tuple[datetime, datetime]:
    today = TimeHandler.get_date()
    return (
        datetime.combine(today, morning_time),
        datetime.combine(today, evening_time),
    )


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
    """
    Logs the signals SIGINT and SIGTERM and then exits.

    Args:
        signal_number: The number representing the signal received.
        _frame: The current stack frame when the signal was received.
    """
    logger.log.info(f"Received {signal.Signals(signal_number).name}. Exiting now...")
    inverter_charge_controller.unlock()
    sys.exit(0)


for signal_to_catch in [signal.SIGINT, signal.SIGTERM]:
    signal.signal(signal_to_catch, handle_stop_signal)

if __name__ == "__main__":
    solar_forecast_logging_thread = threading.Thread(target=log_solar_forecast, daemon=True)
    solar_forecast_logging_thread.start()
    # Let the solar forecast calculate and log its next wakeup time before logging all the info of the
    # InverterChargeController
    pause.seconds(1)

    inverter_charge_controller = InverterChargeController()
    inverter_charge_controller_thread = threading.Thread(target=inverter_charge_controller.start)
    inverter_charge_controller_thread.start()
    inverter_charge_controller_thread.join()
