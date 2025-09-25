import socket
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Generator, Optional

import pause
from aiohttp import ClientError
from goodwe import InverterError, OperationMode
from requests.exceptions import RequestException

from source.abscence_handler import AbsenceHandler
from source.database_handler import DatabaseHandler, InfluxDBField
from source.energy_classes import EnergyAmount, EnergyRate, Power, StateOfCharge
from source.environment_variable_getter import EnvironmentVariableGetter
from source.inverter import Inverter
from source.logger import LoggerMixin
from source.sems_portal_api_handler import SemsPortalApiHandler
from source.sun_forecast_handler import SunForecastHandler
from source.tibber_api_handler import TibberAPIHandler
from source.time_handler import TimeHandler


class InverterChargeController(LoggerMixin):
    def __init__(self):
        super().__init__()

        self.timezone = TimeHandler.get_timezone()
        self.sems_portal_api_handler = SemsPortalApiHandler()
        self.sun_forecast_handler = SunForecastHandler()
        self.inverter = Inverter()
        self.tibber_api_handler = TibberAPIHandler()
        self.absence_handler = AbsenceHandler()
        self.database_handler = DatabaseHandler("power_buy")

        self.current_energy_rate = None
        self.next_price_minimum = None
        self.average_power_consumption = None
        # This is a dict that saves the values of a certain operations such as the upcoming energy rates, the
        # expected power harvested by the sun or the expected power usage.
        # This way if one of the requests to an external system fails (e.g., no Internet access), the prior requests
        # don't have to be made again.
        # This is especially important for the very limited API calls to the sun forecast API.
        self.iteration_cache = {}

    def start(self) -> None:
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
        duration_to_wait_in_cause_of_error = timedelta(minutes=2, seconds=30)
        while True:
            try:
                if first_iteration:
                    self.next_price_minimum = self.tibber_api_handler.get_next_price_minimum(first_iteration=True)
                    first_iteration = False
                else:
                    self._do_iteration()
                    self.iteration_cache = {}

                if self.next_price_minimum.has_to_be_rechecked:
                    now = TimeHandler.get_time(sanitize_seconds=True)
                    time_to_sleep_to = now.replace(hour=14, minute=0)

                    if now <= time_to_sleep_to:
                        self.log.info(
                            f"The price minimum {self.next_price_minimum} has to re-checked "
                            f"--> Waiting until {time_to_sleep_to}..."
                        )
                        pause.until(time_to_sleep_to)
                        self.write_newlines_to_log_file()
                        self.log.info("Waking up since the price minimum has to re-checked")

                    # This without the _if_ before being true does happen when we fetched the prices and the ones for
                    # tomorrow were unavailable, however, we also needed to charge, and now it is passed 2 PM
                    self.next_price_minimum = self.tibber_api_handler.get_next_price_minimum(first_iteration=True)

                self.sems_portal_api_handler.write_values_to_database()

                self.log.info(
                    f"The next price minimum is {self.next_price_minimum.timestamp} --> Waiting until then..."
                )

                pause.until(self.next_price_minimum.timestamp)

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

    def _do_iteration(self) -> None:
        """
        Computes the optimal charging strategy for an inverter until the next price minimum.

        This method performs several key tasks to determine if and how much the inverter needs to be charged:
         - Sets the next price minimum (before it is updated) as the current rate.
         - Retrieves and sets the next price minimum.
         - Sets the maximum charging duration of the current energy rate.
         - Gets the current state of the inverter.
         - Gets the average power consumption.
         - Calculates the estimated minimum and maximum state of charge until the next price minimum.
         - Starts the coordination of the charging process.
        """
        self.write_newlines_to_log_file()
        self.log.info(
            "Waiting is over, now is the a price minimum. Checking what has to be done to reach the next minimum..."
        )
        self.current_energy_rate = self.next_price_minimum

        self.next_price_minimum = self._get_next_price_minimum()
        self.log.info(f"The next price minimum is {self.next_price_minimum}")

        self.tibber_api_handler.set_maximum_charging_duration_of_current_energy_rate(
            self.current_energy_rate, self._get_upcoming_energy_rates()
        )
        self.log.info(
            f"The maximum charging duration of the current energy rate is "
            f"{self.current_energy_rate.maximum_charging_duration}"
        )

        current_state_of_charge = self.inverter.get_state_of_charge()
        self.log.info(f"The battery is currently is at {current_state_of_charge}")

        if current_state_of_charge >= self.target_max_soc:
            self.log.info(
                f"The current state of charge ({current_state_of_charge}) is greater than the maximum allowed "
                f"state of charge ({self.target_max_soc}) --> No charging necessary/possible"
            )
            return

        self.average_power_consumption = self._get_average_power_consumption()
        self.log.info(f"The average power consumption is {self.average_power_consumption}")

        self.log.info(f"The battery shall be at least at {self.target_min_soc} at all times")
        self.log.info(f"The battery shall be at most be charged up to {self.target_max_soc}")

        summary_of_energy_vales = {
            "next price minimum": self.next_price_minimum,
            "next price minimum has to be rechecked": self.next_price_minimum.has_to_be_rechecked,
            "maximum charging duration": str(self.current_energy_rate.maximum_charging_duration),
            "current state of charge": current_state_of_charge,
            "average power consumption": self.average_power_consumption.watts,
            "target min soc": self.target_min_soc,
            "target max soc": self.target_max_soc,
        }
        self.log.debug(f"Summary of energy values: {summary_of_energy_vales}")

        self.coordinate_charging(current_state_of_charge)

    def coordinate_charging(self, current_state_of_charge: StateOfCharge) -> None:
        """
        Coordinates the charging process based on the current state of charge, power consumption, energy rate,
        calculated min and max state of charges and targets for state of charge.
        Determines whether the next price minimum is reachable and initiates corresponding charging strategies.

        Args:
            current_state_of_charge (StateOfCharge): The current level of charge in the battery.
        """
        minimum_of_soc_until_next_price_minimum, maximum_of_soc_until_next_price_minimum = (
            self.sun_forecast_handler.calculate_min_and_max_of_soc_in_timeframe(
                TimeHandler.get_time(),
                self.next_price_minimum.timestamp,
                self.average_power_consumption,
                current_state_of_charge,
                self.next_price_minimum.has_to_be_rechecked,
                self._get_solar_data(),
            )
        )
        self.log.info(
            f"The expected minimum of state of charge until the next price minimum with the current state of charge is "
            f"{minimum_of_soc_until_next_price_minimum}, "
            f"the expected maximum is {maximum_of_soc_until_next_price_minimum}"
        )

        if minimum_of_soc_until_next_price_minimum < self.target_min_soc:
            self.log.info(
                "The expected minimum state of charge until the next price minimum without additional charging "
                f"{minimum_of_soc_until_next_price_minimum} is lower than the target minimum state of charge "
                f"{self.target_min_soc} "
                f"--> Checking whether the next price minimum can be reached even by charging to {self.target_max_soc}"
            )
            if not self._is_next_price_minimum_reachable_by_charging_the_battery_fully():
                self._coordinate_charging_when_next_price_minimum_is_unreachable()
                return

        self._coordinate_charging_next_price_minimum_is_reachable(
            current_state_of_charge,
            minimum_of_soc_until_next_price_minimum,
        )

    def _is_next_price_minimum_reachable_by_charging_the_battery_fully(self) -> bool:
        """
        Determines whether the next price minimum can be reached by fully charging the battery.

        Returns:
            bool: Whether it is possible to reach the next price minimum by charging to the target maximum
        """
        minimum_of_soc_until_next_price_minimum, _ = (
            self.sun_forecast_handler.calculate_min_and_max_of_soc_in_timeframe(
                TimeHandler.get_time(),
                self.next_price_minimum.timestamp,
                self.average_power_consumption,
                self.target_max_soc,
                self.next_price_minimum.has_to_be_rechecked,
                self._get_solar_data(),
            )
        )
        if minimum_of_soc_until_next_price_minimum >= self.target_min_soc:
            self.log.info(
                f"The next price minimum can be reached by charging to {self.target_max_soc} "
                "--> Proceeding with normal operation to determine the target state of charge"
            )
            return True
        else:
            self.log.info(
                f"It is not possible to reach the next price minimum with charging to {self.target_max_soc} "
                "--> Will determine the optimal points in time to charge around the price spike"
            )
            return False

    def _coordinate_charging_when_next_price_minimum_is_unreachable(self) -> None:
        """
        Handles the coordination of battery charging when the upcoming price minimum cannot be reached.

        This function utilizes the upcoming energy rates to determine the most efficient charging strategy. It does this
        by first charging the battery to the target maximum, and then charging the battery around the price spike.
        The "price spike" is the sequence of all EnergyRates that are higher than the average price.
        """
        target_soc = StateOfCharge.from_percentage(100)
        self.log.info(
            f"Firstly, charging the inverter to {target_soc}. As additional charging is required, afterwards, check "
            "the best prices around the price spike to determine the best time to charge"
        )

        target_soc = self._cap_state_of_charge(target_soc)
        if target_soc is not None:
            with self._protocol_amount_of_energy_bought():
                self._charge_inverter(target_soc)

        energy_rate_before_price_rises_over_average, energy_rate_after_price_drops_below_average = (
            self._get_energy_rates_before_and_after_price_spike()
        )

        self.log.info(
            f"The energy rates before the price spike is at {energy_rate_before_price_rises_over_average.timestamp}"
            f"--> Waiting until then..."
        )
        pause.until(energy_rate_before_price_rises_over_average.timestamp)

        self.log.info("Waking up to determine the optimal charging time around the price spike")
        if energy_rate_after_price_drops_below_average < energy_rate_before_price_rises_over_average:
            self.log.info(
                "The energy rate after the price drops below the average is lower than the rate before it drops over "
                "the average --> Checking whether it is necessary to charge now to reach after the price spike "
                f"({energy_rate_after_price_drops_below_average.timestamp})"
            )
            self._coordinate_charging_when_next_price_minimum_is_unreachable_and_second_charge_after_spike_cheaper_than_before(
                energy_rate_after_price_drops_below_average,
            )

        pause.until(energy_rate_after_price_drops_below_average.timestamp)
        self._coordinate_charging_after_price_spike_until_next_minimum()

    def _get_energy_rates_before_and_after_price_spike(self) -> tuple[EnergyRate, EnergyRate]:
        energy_rate_before_price_rises_over_average, energy_rate_after_price_drops_below_average = (
            self.tibber_api_handler.get_energy_rate_before_and_after_the_price_is_higher_than_the_average_until_timestamp(
                self._get_upcoming_energy_rates(), self.next_price_minimum.timestamp
            )
        )
        self.log.info(
            f"The last energy rate before the price rises over the average is "
            f"{energy_rate_before_price_rises_over_average}. "
            f"The first energy rate after the price drops below the average is "
            f"{energy_rate_after_price_drops_below_average}."
            f"--> Will charge now to {self.target_max_soc} and then wait until "
            f"{energy_rate_before_price_rises_over_average.timestamp}"
        )

        return energy_rate_before_price_rises_over_average, energy_rate_after_price_drops_below_average

    def _coordinate_charging_when_next_price_minimum_is_unreachable_and_second_charge_after_spike_cheaper_than_before(
        self,
        energy_rate_after_price_drops_below_average: EnergyRate,
    ) -> None:
        # Current time: Right before the price spike
        self.log.info(
            "The energy rate after the price drops below the average is lower than the rate before it drops over the"
            "average --> Checking whether it is necessary to charge now to reach after the price spike "
            f"({energy_rate_after_price_drops_below_average.timestamp})"
        )
        current_state_of_charge = self.inverter.get_state_of_charge()
        self.log.debug(f"The current state of charge is {current_state_of_charge}")
        minimum_of_soc_until_next_price_minimum, _ = (
            self.sun_forecast_handler.calculate_min_and_max_of_soc_in_timeframe(
                TimeHandler.get_time(),
                energy_rate_after_price_drops_below_average.timestamp,
                self.average_power_consumption,
                current_state_of_charge,
                self.next_price_minimum.has_to_be_rechecked,
                self._get_solar_data(),
            )
        )
        if minimum_of_soc_until_next_price_minimum < self.target_min_soc:
            self.log.info(
                "It is not possible to reach after the price spike without charging. "
                "--> Charging now as few as possible to reach after the price spike "
                f"({energy_rate_after_price_drops_below_average.timestamp})"
            )
            self.log.debug(
                f"Formula for calculating the target state of charge: "
                f"target minimum state of charge ({self.target_min_soc}) - minimum state of charge until next price "
                f"minimum ({minimum_of_soc_until_next_price_minimum})"
            )
            charging_target_soc = StateOfCharge(
                self.target_min_soc.absolute - minimum_of_soc_until_next_price_minimum.absolute
            )
            self.log.info(f"The calculated target state of charge is {charging_target_soc}")
            charging_target_soc = self._cap_state_of_charge(charging_target_soc)
            if charging_target_soc is not None:
                with self._protocol_amount_of_energy_bought():
                    self._charge_inverter(charging_target_soc)

            self.log.info(
                f"Waiting until after the price spike ({energy_rate_after_price_drops_below_average.timestamp})"
            )
        else:
            self.log.info(
                "It is possible to reach after the price spike without charging. "
                f"--> Waiting until then ({energy_rate_after_price_drops_below_average.timestamp})"
            )

    def _coordinate_charging_after_price_spike_until_next_minimum(self) -> None:
        self.log.info(
            f"Determining what is necessary to reach the next price minimum ({self.next_price_minimum.timestamp})"
        )
        current_state_of_charge = self.inverter.get_state_of_charge()
        self.log.debug(f"The current state of charge is {current_state_of_charge}")
        minimum_of_soc_until_next_price_minimum, _ = (
            self.sun_forecast_handler.calculate_min_and_max_of_soc_in_timeframe(
                TimeHandler.get_time(),
                self.next_price_minimum.timestamp,
                self.average_power_consumption,
                current_state_of_charge,
                self.next_price_minimum.has_to_be_rechecked,
                self._get_solar_data(),
            )
        )
        self.log.debug(
            f"Formula for calculating the target state of charge: current {current_state_of_charge} + "
            f"target minimum state of charge ({self.target_min_soc}) - minimum state of charge until next price "
            f"minimum ({minimum_of_soc_until_next_price_minimum})"
        )
        charging_target_soc = StateOfCharge(
            current_state_of_charge.absolute
            + self.target_min_soc.absolute
            - minimum_of_soc_until_next_price_minimum.absolute
        )
        self.log.info(f"The calculated target state of charge is {charging_target_soc}")
        charging_target_soc = self._cap_state_of_charge(charging_target_soc)
        if charging_target_soc is not None:
            with self._protocol_amount_of_energy_bought():
                self._charge_inverter(charging_target_soc)

    def _coordinate_charging_next_price_minimum_is_reachable(
        self,
        current_state_of_charge: StateOfCharge,
        minimum_of_soc_until_next_price_minimum: StateOfCharge,
    ) -> None:
        """
        Determines and coordinates the target state of charge for charging the battery, either to reach the next
        price minimum or to buy as much energy as possible without waisting any of the suns.

        If the energy rate of the current minimum price is higher than the upcoming price minimum, the method calculates
        the target state of charge based on the minimum required energy until the next price minimum.
        Otherwise, it calculates the target state of charge to maximize energy storage while avoiding energy waste.

        Args:
            current_state_of_charge (StateOfCharge): The current level of charge in the battery.
            minimum_of_soc_until_next_price_minimum (StateOfCharge): The calculated minimum SOC in the timespan to the
                next price minimum.
        """
        if self.current_energy_rate >= self.next_price_minimum:
            charging_target_soc = (
                self._calculate_target_soc_next_price_minimum_is_reachable_and_current_minimum_is_higher_than_next_one(
                    current_state_of_charge, minimum_of_soc_until_next_price_minimum
                )
            )
            if charging_target_soc is None:
                return
        else:
            charging_target_soc = (
                self._calculate_target_soc_next_price_minimum_is_reachable_and_current_minimum_is_lower_than_next_one(
                    current_state_of_charge,
                )
            )

        self.log.info(f"The calculated target state of charge is {charging_target_soc}")

        charging_target_soc = self._cap_state_of_charge(charging_target_soc)
        if charging_target_soc is not None:
            with self._protocol_amount_of_energy_bought():
                self._charge_inverter(charging_target_soc)

    def _calculate_target_soc_next_price_minimum_is_reachable_and_current_minimum_is_higher_than_next_one(
        self,
        current_state_of_charge: StateOfCharge,
        minimum_of_soc_until_next_price_minimum: StateOfCharge,
    ) -> Optional[StateOfCharge]:
        self.log.info(
            f"The price of the current minimum ({self.current_energy_rate.rate} ct/kWh) is higher than the one of "
            f"the upcoming minimum ({self.next_price_minimum.rate} ct/kWh) "
            "--> Will only charge the battery as little as possible to reach the next price minimum"
        )
        if minimum_of_soc_until_next_price_minimum > self.target_min_soc:
            self.log.info(
                "The expected minimum state of charge until the next price minimum without additional charging "
                f"{minimum_of_soc_until_next_price_minimum} is higher than the target minimum state of charge "
                f"{self.target_min_soc} --> There is no need to charge"
            )
            return None

        self.log.debug(
            f"Formula for calculating the target state of charge: current {current_state_of_charge} + "
            f"target minimum state of charge ({self.target_min_soc}) - minimum state of charge until next price "
            f"minimum ({minimum_of_soc_until_next_price_minimum})"
        )
        return StateOfCharge(
            current_state_of_charge.absolute
            + self.target_min_soc.absolute
            - minimum_of_soc_until_next_price_minimum.absolute
        )

    def _calculate_target_soc_next_price_minimum_is_reachable_and_current_minimum_is_lower_than_next_one(
        self, current_state_of_charge: StateOfCharge
    ) -> StateOfCharge:
        self.log.info(
            f"The price of the upcoming minimum ({self.next_price_minimum.rate} ct/kWh) is higher than the one of "
            f"the current minimum ({self.current_energy_rate.rate} ct/kWh) "
            "--> Will charge as much as possible without wasting any energy of the sun"
        )
        timeframe_end = self.sun_forecast_handler.get_tomorrows_sunset_time()
        self.log.debug(f"The timeframe end (tomorrows sunset) is {timeframe_end}")
        _, maximum_of_soc_until_timeframe_end = self.sun_forecast_handler.calculate_min_and_max_of_soc_in_timeframe(
            TimeHandler.get_time(),
            timeframe_end,
            self.average_power_consumption,
            current_state_of_charge,
            self.next_price_minimum.has_to_be_rechecked,
            self._get_solar_data(),
        )
        """
        We use StateOfCharge.from_percentage(100) instead of of self.target_max_soc as we want to charge as much as
        possible without wasting any energy of the sun. Since the sun can "charge" the battery to 100 % and we do not
        care about the speed of charging we use that.
        """
        self.log.debug(
            f"Formula for calculating the target state of charge: current ({current_state_of_charge}) + "
            f"{StateOfCharge.from_percentage(100)} - maximum state of charge until tomorrows sunset "
            f"({maximum_of_soc_until_timeframe_end})"
        )
        return StateOfCharge(
            current_state_of_charge.absolute
            + StateOfCharge.from_percentage(100).absolute
            - maximum_of_soc_until_timeframe_end.absolute
        )

    def _charge_inverter(self, target_state_of_charge: StateOfCharge) -> None:
        """
        Charges the inverter battery to the target state of charge within a specified maximum charging duration.
        Monitors the charging progress at regular intervals and stops the charging process if specific conditions are
        met:
         - Charging limit reached
         - Maximum charging duration reached (at this point the energy prices would be too high to charge)
         - The operational mode of the inverter was changed manually
         - Too many errors occurred while trying to communicate with the inverter

        Args:
            target_state_of_charge: The desired battery state of charge percentage to reach during the charging
                process.
        """
        charging_progress_check_interval = timedelta(minutes=5)

        maximum_end_charging_time = TimeHandler.floor_to_quarter(
            TimeHandler.get_time() + self.current_energy_rate.maximum_charging_duration
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

            # Account for program execution times, this way the check happens at 5-minute intervals and delays do not
            # add up (minor cosmetics)
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
                    f"Charging finished, the battery is at {current_state_of_charge} "
                    "--> Setting the inverter back to normal mode"
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
                f"Charging is still ongoing (current: {current_state_of_charge}, target: >= {target_state_of_charge}) "
                f"--> Waiting for another {charging_progress_check_interval}..."
            )

    @contextmanager
    def _protocol_amount_of_energy_bought(self) -> Generator:
        """
        Context manager to monitor and log the amount of energy bought during a battery charging session.

        This function acts as a context manager that tracks the energy purchased before and after charging the battery.
        It calculates the energy bought during the session, logs it, and saves the data in the database.

        Yields:
            Generator: Context manager block is executed.
        """
        energy_bought_before_charging = self.sems_portal_api_handler.get_energy_buy()
        timestamp_starting_to_charge = TimeHandler.get_time()
        self.log.debug(f"The amount of energy bought before charging is {energy_bought_before_charging}")

        yield

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

    def _cap_state_of_charge(self, target_state_of_charge: StateOfCharge) -> Optional[StateOfCharge]:
        """
        Caps the target state of charge based on maximum allowed charge in the environment
        and returns None when the current state of charge is higher than the target state of charge.

        Args:
            target_state_of_charge (StateOfCharge): Desired state of charge

        Returns:
            Optional[StateOfCharge]: Returns the capped state of charge if the target state of charge is higher than the
                current state of charge; otherwise, returns None.
        """
        if target_state_of_charge > self.target_max_soc:
            self.log.info(
                f"The target state of charge {target_state_of_charge} is higher than the maximum allowed charge set in "
                f"the environment --> Setting it to {self.target_max_soc}"
            )
            target_state_of_charge = self.target_max_soc

        current_state_of_charge = self.inverter.get_state_of_charge()
        if current_state_of_charge >= target_state_of_charge:
            self.log.info(
                f"The current state of charge {current_state_of_charge} is higher or equal than the target state of "
                f"charge {target_state_of_charge} --> Will not charge"
            )
            return None

        return target_state_of_charge

    @property
    def target_min_soc(self) -> StateOfCharge:
        return StateOfCharge.from_percentage(
            int(EnvironmentVariableGetter.get("INVERTER_TARGET_MIN_STATE_OF_CHARGE", 15))
        )

    @property
    def target_max_soc(self) -> StateOfCharge:
        return StateOfCharge.from_percentage(
            int(EnvironmentVariableGetter.get("INVERTER_TARGET_MAX_STATE_OF_CHARGE", 95))
        )

    """
    The following methods are used to cache values to reduce the number of API calls made to certain APIs and reduce the
    amount of calculations performed. This cache is only used in the event that during an iteration an API call fails.
    In this case, previous values from the same iteration are saved and used when the failed API call is retried.
    """

    def _get_upcoming_energy_rates(self) -> list[EnergyRate]:
        cache_key = "upcoming_energy_rates"
        upcoming_energy_rates = self._get_value_from_cache_if_exists(cache_key)
        if upcoming_energy_rates:
            return upcoming_energy_rates

        upcoming_energy_rates = self.tibber_api_handler.get_upcoming_energy_rates()
        self._set_cache_key(cache_key, upcoming_energy_rates)
        return upcoming_energy_rates

    def _get_next_price_minimum(self) -> EnergyRate:
        cache_key = "next_price_minimum"
        next_price_minimum = self._get_value_from_cache_if_exists(cache_key)
        if next_price_minimum:
            return next_price_minimum

        next_price_minimum = self.tibber_api_handler.get_next_price_minimum(
            upcoming_energy_rates=self._get_upcoming_energy_rates()
        )
        self._set_cache_key(cache_key, next_price_minimum)
        return next_price_minimum

    def _get_average_power_consumption(self) -> Power:
        cache_key = "average_power_consumption"
        average_power_consumption = self._get_value_from_cache_if_exists(cache_key)
        if average_power_consumption:
            return average_power_consumption

        if self.absence_handler.check_for_current_absence():
            self.log.info(
                "Currently there is an absence, using the power consumption configured in the environment as the basis "
                "for calculation"
            )
            average_power_consumption = Power(float(EnvironmentVariableGetter.get("ABSENCE_POWER_CONSUMPTION", 150)))
        else:
            self.log.debug(
                "Currently there is no absence, using last week's power consumption data as the basis for calculation"
            )
            average_power_consumption = self.sems_portal_api_handler.get_average_power_consumption()
        self._set_cache_key(cache_key, average_power_consumption)
        return average_power_consumption

    def _get_solar_data(self) -> dict[str, Power]:
        cache_key = "solar_data"
        solar_data = self._get_value_from_cache_if_exists(cache_key)
        if solar_data:
            return solar_data

        solar_data = self.sun_forecast_handler.retrieve_solar_data(True)
        self._set_cache_key(cache_key, solar_data)
        return solar_data

    def _get_value_from_cache_if_exists(self, cache_key: str) -> Optional[Any]:
        if cache_key not in self.iteration_cache.keys():
            return None
        return self.iteration_cache[cache_key]

    def _set_cache_key(self, cache_key: str, value: Any) -> None:
        self.iteration_cache[cache_key] = value
