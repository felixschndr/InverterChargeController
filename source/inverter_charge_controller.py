import os
import socket
import sys
from datetime import datetime, timedelta
from typing import Any, Optional

import pause
from abscence_handler import AbsenceHandler
from aiohttp import ClientError
from database_handler import DatabaseHandler, InfluxDBField
from energy_classes import EnergyAmount, EnergyRate, Power, StateOfCharge
from environment_variable_getter import EnvironmentVariableGetter
from goodwe import InverterError, OperationMode
from inverter import Inverter
from logger import LoggerMixin
from requests.exceptions import RequestException
from sems_portal_api_handler import SemsPortalApiHandler
from sun_forecast_handler import SunForecastHandler
from tibber_api_handler import TibberAPIHandler
from time_handler import TimeHandler


class InverterChargeController(LoggerMixin):
    LOCK_FILE_PATH = "/tmp/inverter_charge_controller.lock"  # nosec B108

    def __init__(self):
        super().__init__()

        started_by_systemd = " by systemd" if "INVOCATION_ID" in os.environ else ""
        self.log.info(f"Starting application{started_by_systemd}")

        self.timezone = TimeHandler.get_timezone()
        self.sems_portal_api_handler = SemsPortalApiHandler()
        self.sun_forecast_handler = SunForecastHandler()
        self.inverter = Inverter()
        self.tibber_api_handler = TibberAPIHandler()
        self.absence_handler = AbsenceHandler()
        self.database_handler = DatabaseHandler("power_buy")

        # This is a dict which saves the values of a certain operations such as the upcoming energy rates, the
        # expected power harvested by the sun or the expected power usage
        # This way if one of the requests to an external system fails (e.g. no Internet access) the prior requests don't
        # have to be made again. This is especially important for the very limited API calls to the sun forecast API.
        self.iteration_cache = {}

    def start(self) -> None:
        """
        Starts the inverter charge controller process. Ensures that the process is not already running
        by checking for the presence of a lock file. If the process is running, logs the error and exits.
        Upon successful starting, creates and manages a lock file for the process to avoid multiple
        instances. It Also ensures cleanup of the lock file post execution.
        """
        if os.path.exists(self.LOCK_FILE_PATH):
            self.log.error("Attempted to start the inverter charge controller, but it is already running.")
            return

        self._lock()
        try:
            self._start()
        finally:
            self.unlock()

    def _start(self) -> None:
        """
        Starts the continuous running of the program and handles all exceptions possibly raised during execution.
         - Expected exceptions: Wait for some minutes and retry
         - Unexpected exceptions: Exit with status code 1

        This method indefinitely repeats a sequence of operations until an unrecoverable error occurs.
        On the first iteration, it performs a special initialization operation to determine the next scheduled execution
        time.
        On subsequent iterations, it performs a standard operation to determine the next scheduled execution time.

        Raises:
            SystemExit: If an unexpected error occurs, the program will exit with a status code of 1.
        """
        first_iteration = True
        next_price_minimum = None
        duration_to_wait_in_cause_of_error = timedelta(minutes=2, seconds=30)
        while True:
            try:
                self.write_newlines_to_log_file()
                if first_iteration:
                    next_price_minimum = self.tibber_api_handler.get_next_price_minimum(first_iteration)
                    first_iteration = False
                else:
                    next_price_minimum = self._do_iteration(next_price_minimum)

                if next_price_minimum.has_to_be_rechecked:
                    now = TimeHandler.get_time(sanitize_seconds=True)
                    time_to_sleep_to = now.replace(hour=14, minute=0)
                    if now > time_to_sleep_to:
                        time_to_sleep_to += timedelta(days=1)
                    self.log.info(
                        f"The price minimum {next_price_minimum} has to re-checked "
                        f"--> Waiting until {time_to_sleep_to}..."
                    )
                    pause.until(time_to_sleep_to)
                    self.log.info("Waking up since the the price minimum has to re-checked")
                    next_price_minimum = self.tibber_api_handler.get_next_price_minimum(True)

                self.sems_portal_api_handler.write_values_to_database()

                self.log.info(f"The next price minimum is at {next_price_minimum.timestamp}. Waiting until then...")

                pause.until(next_price_minimum.timestamp)

            except (ClientError, RequestException, socket.gaierror, InverterError, TimeoutError):
                self.log.warning(
                    f"An exception occurred while trying to fetch data from a different system. "
                    f"Waiting for {duration_to_wait_in_cause_of_error} to try again...",
                    exc_info=True,
                )
                pause.seconds(duration_to_wait_in_cause_of_error.total_seconds())

            except Exception:
                self.log.critical("An unexpected error occurred. Exiting now...", exc_info=True)
                sys.exit(1)

    def _do_iteration(self, current_energy_rate: EnergyRate) -> EnergyRate:
        """
        Computes the optimal charging strategy for an inverter until the next price minimum.

        This method performs several key tasks to determine if and how much the inverter needs to be charged:
         - Retrieves the next price minimum.
         - Sets the maximum charging duration of the current energy rate.
         - Gets the current state of the inverter.
         - Gets the average power consumption.
         - Calculates the estimated minimum state of charge until the next price minimum.
         - If the estimated minimum state of charge is lower than the target minimum state of charge, the method
           calculates the required state of charge to reach the target minimum state of charge and initiates charging.

        Returns:
            EnergyRate: The next price minimum energy rate.
        """
        self.log.info(
            "Waiting is over, now is the a price minimum. Checking what has to be done to reach the next minimum..."
        )
        timestamp_now = TimeHandler.get_time()

        next_price_minimum = self._get_next_price_minimum()
        self.log.info(f"The next price minimum is at {next_price_minimum}")

        self.tibber_api_handler.set_maximum_charging_duration_of_current_energy_rate(current_energy_rate)
        self.log.info(
            f"The maximum charging duration of the current energy rate is "
            f"{current_energy_rate.maximum_charging_duration}"
        )

        if next_price_minimum.rate > current_energy_rate.rate:
            # Information is unused at the moment
            self.log.info("The price of the upcoming minimum is higher than the current energy rate")

        current_state_of_charge = self.inverter.get_state_of_charge()
        self.log.info(f"The battery is currently is at {current_state_of_charge}")

        average_power_consumption = self._get_average_power_consumption()
        self.log.info(f"The average power consumption is {average_power_consumption}")

        minimum_of_soc_until_next_price_minimum = self._get_minimum_of_soc_until_next_price_minimum(
            next_price_minimum.timestamp, average_power_consumption, current_state_of_charge
        )
        self.log.info(
            f"The minimum of state of charge until the next price minimum with the current state of charge is "
            f"{minimum_of_soc_until_next_price_minimum}"
        )

        target_min_soc = StateOfCharge.from_percentage(
            int(EnvironmentVariableGetter.get("INVERTER_TARGET_MIN_STATE_OF_CHARGE", 10))
        )
        self.log.info(f"The battery shall be at least at {target_min_soc} at all times")

        summary_of_energy_vales = {
            "timestamp now": str(timestamp_now),
            "next price minimum": next_price_minimum,
            "minimum_has_to_be_rechecked": next_price_minimum.has_to_be_rechecked,
            "maximum charging duration": current_energy_rate.format_maximum_charging_duration(),
            "current state of charge": current_state_of_charge,
            "average power consumption": average_power_consumption,
            "minimum of soc until next price minimum": minimum_of_soc_until_next_price_minimum,
            "target min soc": target_min_soc,
        }
        self.log.debug(f"Summary of energy values: {summary_of_energy_vales}")

        if minimum_of_soc_until_next_price_minimum > target_min_soc:
            self.log.info(
                "The expected minimum state of charge until the next price minimum without additional charging"
                "is higher than the target minimum state of charge. --> There is no need to charge"
            )
            self.iteration_cache = {}
            return next_price_minimum

        required_state_of_charge = current_state_of_charge + (target_min_soc - minimum_of_soc_until_next_price_minimum)
        self.log.info(f"There is a need to charge to {required_state_of_charge}")

        max_target_soc = StateOfCharge.from_percentage(
            int(EnvironmentVariableGetter.get("INVERTER_TARGET_MAX_STATE_OF_CHARGE", 95))
        )
        if required_state_of_charge > max_target_soc:
            self.log.info(
                "The target state of charge is more than the maximum allowed charge set in the environment "
                f"--> Setting it to {max_target_soc}"
            )
            required_state_of_charge = max_target_soc

        energy_bought_before_charging = self.sems_portal_api_handler.get_energy_buy()
        timestamp_starting_to_charge = TimeHandler.get_time()
        self.log.debug(f"The amount of energy bought before charging is {energy_bought_before_charging}")

        self._charge_inverter(required_state_of_charge, current_energy_rate.maximum_charging_duration)

        timestamp_ending_to_charge = TimeHandler.get_time()

        duration_to_wait_for_semsportal_update = timedelta(minutes=20)
        self.log.info(
            f"Sleeping for {duration_to_wait_for_semsportal_update} to let the SEMS Portal update its power "
            "consumption data..."
        )
        pause.seconds(duration_to_wait_for_semsportal_update.total_seconds())

        energy_bought = self._calculate_amount_of_energy_bought(
            energy_bought_before_charging,
            timestamp_starting_to_charge,
            timestamp_ending_to_charge + duration_to_wait_for_semsportal_update,
        )
        self.log.info(f"Bought {energy_bought} to charge the battery")

        self._write_energy_buy_statistics_to_database(
            timestamp_starting_to_charge, timestamp_ending_to_charge, energy_bought
        )

        self.iteration_cache = {}
        return next_price_minimum

    def _charge_inverter(self, target_state_of_charge: StateOfCharge, maximum_charging_duration: timedelta) -> None:
        """
        Charges the inverter battery to the target state of charge within a specified maximum charging duration.
        Monitors the charging progress at regular intervals and stops the charging process if specific conditions are
        met:
         - Charging limit reached
         - Maximum charging duration reached (at this point the energy prices would be to high to charge)
         - The state of the inverter was changed manually
         - Too many errors occurred while trying to communicate with the inverter

        Args:
            target_state_of_charge: The desired battery state of charge percentage to reach during the
                charging process.
            maximum_charging_duration: The maximum duration allowed for the charging process to complete.
        """
        charging_progress_check_interval = timedelta(minutes=5)

        maximum_end_charging_time = (
            TimeHandler.get_time(sanitize_seconds=True).replace(minute=0) + maximum_charging_duration
        )

        self.log.info("Starting to charge")
        self.inverter.set_operation_mode(OperationMode.ECO_CHARGE)

        self.log.info(
            f"Set the inverter to charge, the target state of charge is {target_state_of_charge}. "
            f"End of charging is {maximum_end_charging_time.strftime('%H:%M:%S')} at the latest. "
            f"Checking the charging progress every {charging_progress_check_interval}..."
        )

        error_counter = 0
        while True:
            if error_counter == 3:
                self.log.error(
                    f"An error occurred {error_counter} times while trying to get the current state of charge"
                    f"--> Stopping the charging process"
                )
                # Can't set the mode of the inverter as it is unresponsive
                break

            # Account for program execution times, this way the check happens at 05:00 and does not add up delays
            # (minor cosmetics)
            pause.seconds(charging_progress_check_interval.total_seconds() - TimeHandler.get_time().second)

            try:
                if self.inverter.get_operation_mode() != OperationMode.ECO_CHARGE:
                    self.log.warning(
                        "The operation mode of the inverter was changed by the user --> Stopping the charging progress"
                    )
                    break

                current_state_of_charge = self.inverter.get_state_of_charge()

                error_counter = 0
            except InverterError:
                self.log.warning(
                    f"An exception occurred while trying to fetch the current state of charge. "
                    f"Waiting for {charging_progress_check_interval} to try again...",
                    exc_info=True,
                )
                error_counter += 1
                continue

            if current_state_of_charge >= target_state_of_charge:
                self.log.info(
                    f"Charging finished ({current_state_of_charge}) --> Setting the inverter back to normal mode"
                )
                self.inverter.set_operation_mode(OperationMode.GENERAL)
                break

            if TimeHandler.get_time() > maximum_end_charging_time:
                self.log.info(
                    f"The maximum end charging time of {maximum_end_charging_time} has been reached "
                    f"--> Stopping the charging process. The battery is at {current_state_of_charge}"
                )
                self.inverter.set_operation_mode(OperationMode.GENERAL)
                break

            self.log.debug(
                f"Charging is still ongoing (current: {current_state_of_charge}, target: >= {target_state_of_charge} "
                f") --> Waiting for another {charging_progress_check_interval}..."
            )

    def _calculate_amount_of_energy_bought(
        self,
        energy_bought_before_charging: EnergyAmount,
        timestamp_starting_to_charge: datetime,
        timestamp_ending_to_charge: datetime,
    ) -> EnergyAmount:
        """
        Calculates the total amount of energy bought during a charging session.

        This method determines the energy purchased based on whether the charging session occurred on a single day or
        spanned across two consecutive days. It uses the SEMS portal API to fetch the amount of energy purchased for the
        different days and computes the total difference.

        Args:
            energy_bought_before_charging: Energy amount recorded before charging started.
            timestamp_starting_to_charge: Datetime object representing when the charging started.
            timestamp_ending_to_charge: Datetime object representing when the charging ended.

        Returns:
            EnergyAmount: The total energy bought during the charging session.
        """
        if timestamp_starting_to_charge.date() == timestamp_ending_to_charge.date():
            energy_bought_today_after_charging = self.sems_portal_api_handler.get_energy_buy()
            self.log.debug(
                f"It is till the same day since starting to charge, the amount of energy bought after charging is "
                f"{energy_bought_today_after_charging}"
            )
            return energy_bought_today_after_charging - energy_bought_before_charging

        energy_bought_today_after_charging = self.sems_portal_api_handler.get_energy_buy()
        energy_bought_yesterday = self.sems_portal_api_handler.get_energy_buy(1) - energy_bought_before_charging
        self.log.debug(
            f"It is the next day since starting to charge, the amount of energy bought after charging (today) is "
            f"{energy_bought_today_after_charging}, the amount of energy bought after charging (yesterday) is "
            f"{energy_bought_yesterday}"
        )
        return energy_bought_today_after_charging + energy_bought_yesterday

    def _write_energy_buy_statistics_to_database(
        self, timestamp_starting_to_charge: datetime, timestamp_ending_to_charge: datetime, energy_bought: EnergyAmount
    ) -> None:
        """
        Writes the amount of energy bought and the corresponding start and end timestamps into the database.

        Args:
            timestamp_starting_to_charge: Datetime object representing when the charging started.
            timestamp_ending_to_charge: Datetime object representing when the charging ended.
            energy_bought: EnergyAmount object containing the amount of energy (in watt-hours) purchased.
        """
        self.log.debug("Writing statistics of power buy to database")
        self.database_handler.write_to_database(
            [
                InfluxDBField("amount_of_power_bought_in_watt_hours", energy_bought.watt_hours),
                InfluxDBField("timestamp_starting_to_charge", timestamp_starting_to_charge.isoformat()),
                InfluxDBField("timestamp_ending_to_charge", timestamp_ending_to_charge.isoformat()),
            ]
        )

    """
    The following methods are used to cache values to reduce the number of API calls made to certain APIs and reduce the
    amount of calculations performed. This cache is only used in the event that during an iteration an API call fails.
    In this case, previous values from the same iteration are saved and used when the failed API call is retried.
    """

    def _get_next_price_minimum(self) -> EnergyRate:
        cache_key = "next_price_minimum"
        next_price_minimum = self._get_value_from_cache_if_exists(cache_key)
        if next_price_minimum:
            return next_price_minimum

        next_price_minimum = self.tibber_api_handler.get_next_price_minimum()
        self._set_cache_key(cache_key, next_price_minimum)
        return next_price_minimum

    def _get_average_power_consumption(self) -> Power:
        cache_key = "average_power_consumption"
        average_power_consumption = self._get_value_from_cache_if_exists(cache_key)
        if average_power_consumption:
            return average_power_consumption

        average_power_consumption = self.sems_portal_api_handler.get_average_power_consumption()
        self._set_cache_key(cache_key, average_power_consumption)
        return average_power_consumption

    def _get_minimum_of_soc_until_next_price_minimum(
        self, next_price_minimum_timestamp: datetime, average_power_consumption: Power, current_soc: StateOfCharge
    ) -> StateOfCharge:
        cache_key = "minimum_of_soc_until_next_price_minimum"
        minimum_of_soc_until_next_price_minimum = self._get_value_from_cache_if_exists(cache_key)
        if minimum_of_soc_until_next_price_minimum:
            return minimum_of_soc_until_next_price_minimum

        minimum_of_soc_until_next_price_minimum, _ = (
            self.sun_forecast_handler.calculate_minimum_of_soc_and_power_generation_in_timeframe(
                TimeHandler.get_time(), next_price_minimum_timestamp, average_power_consumption, current_soc
            )
        )
        self._set_cache_key(cache_key, minimum_of_soc_until_next_price_minimum)
        return minimum_of_soc_until_next_price_minimum

    def _get_value_from_cache_if_exists(self, cache_key: str) -> Optional[Any]:
        if cache_key not in self.iteration_cache.keys():
            return None
        self.log.debug(f"Cache hit for: {cache_key}")
        return self.iteration_cache[cache_key]

    def _set_cache_key(self, cache_key: str, value: Any) -> None:
        self.iteration_cache[cache_key] = value

    def _lock(self) -> None:
        """
        Writes the current process ID to a lock file to indicate the process is active.
        """
        with open(self.LOCK_FILE_PATH, "w") as lock_file:
            lock_file.write(str(os.getpid()))
        self.log.debug("Lock file created")

    def unlock(self) -> None:
        """
        Removes the lock file if it exists and thus unlocking the process.
        """
        if not os.path.exists(self.LOCK_FILE_PATH):
            return

        os.remove(self.LOCK_FILE_PATH)
        self.log.debug("Lock file removed")
