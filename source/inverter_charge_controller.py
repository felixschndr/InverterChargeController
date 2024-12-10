from datetime import datetime, timedelta

import pause
from abscence_handler import AbsenceHandler
from aiohttp import ClientError
from energy_amount import EnergyAmount
from environment_variable_getter import EnvironmentVariableGetter
from goodwe import OperationMode, RequestFailedException
from inverter import Inverter
from logger import LoggerMixin
from requests.exceptions import RequestException
from sems_portal_api_handler import SemsPortalApiHandler
from sun_forecast_handler import SunForecastHandler
from tibber_api_handler import TibberAPIHandler
from time_handler import TimeHandler


class InverterChargeController(LoggerMixin):
    def __init__(self):
        super().__init__()

        self.log.info("Starting application")

        self.timezone = TimeHandler.get_timezone()
        self.sems_portal_api_handler = SemsPortalApiHandler()
        self.sun_forecast_handler = SunForecastHandler()
        self.inverter = Inverter()
        self.tibber_api_handler = TibberAPIHandler()
        self.absence_handler = AbsenceHandler()

    def start(self) -> None:
        """
        Starts the continuous running of the program and handles all exceptions possibly raised during execution.
         - Expected exceptions: Wait for some minutes and retry
         - Unexpected exceptions: Exit with status code 1

        This method indefinitely repeats a sequence of operations until an unrecoverable error occurs.
        On the first iteration, it performs a special initialization operation to determine the next scheduled execution time.
        On subsequent iterations, it performs a standard operation to determine the next scheduled execution time.

        Raises:
            SystemExit: If an unexpected error occurs, the program will exit with a status code of 1.
        """
        first_iteration = True
        duration_to_wait_in_cause_of_error = timedelta(minutes=10)
        while True:
            try:
                if first_iteration:
                    next_price_minimum, minimum_has_to_be_rechecked = (
                        self.tibber_api_handler.get_timestamp_of_next_price_minimum(first_iteration)
                    )
                    first_iteration = False
                else:
                    next_price_minimum, minimum_has_to_be_rechecked = self._do_iteration()

                if minimum_has_to_be_rechecked:
                    now = TimeHandler.get_time()
                    time_to_sleep_to = now.replace(hour=14, minute=0, second=0, microsecond=0)
                    if now > time_to_sleep_to:
                        time_to_sleep_to += timedelta(days=1)
                    self.log.info(f"The price minimum has to re-checked at {time_to_sleep_to}. Waiting until then...")
                    pause.until(time_to_sleep_to)
                    self.log.info("Waking up since the the price minimum has to re-checked")
                    next_price_minimum, _ = self.tibber_api_handler.get_timestamp_of_next_price_minimum(True)

                self.log.info(f"The next price minimum is at {next_price_minimum}. Waiting until then...")

                self._write_newlines_to_log_file()
                pause.until(next_price_minimum)

            except (ClientError, RequestException) as e:
                self.log.exception(f"An exception occurred while trying to fetch data from a different system: {e}")
                self.log.warning(f"Waiting for {duration_to_wait_in_cause_of_error} to try again...")
                pause.seconds(duration_to_wait_in_cause_of_error.total_seconds())

            except Exception as e:
                self.log.exception(f"An unexpected error occurred: {e}")
                self.log.critical("Exiting now...")
                exit(1)

    def _do_iteration(self) -> tuple[datetime, bool]:  # FIXME: Find better name
        """
        Computes the optimal charging strategy for an inverter until the next price minimum.

        This method performs several key tasks to determine if and how much the inverter needs to be charged:
         - Retrieves the current timestamp and the next price minimum.
         - Estimates the solar power output and energy usage until the next price minimum.
         - Calculates the current energy stored in the battery based on its state of charge.
         - Compares the current and expected future state with the target minimum state of charge to determine if
           additional charging is necessary.
         - Initiates charging if required.

        Returns:
            datetime: The timestamp of the next price minimum.
            minimum_has_to_be_rechecked: Whether the price minimum has to be re-checked since not all the prices were
                available yet.
        """
        self.log.info(
            "Waiting is over, now is the a price minimum. Checking what has to be done to reach the next minimum..."
        )

        timestamp_now = TimeHandler.get_time()

        next_price_minimum, minimum_has_to_be_rechecked = self.tibber_api_handler.get_timestamp_of_next_price_minimum()
        self.log.info(f"The next price minimum is at {next_price_minimum}")

        if minimum_has_to_be_rechecked:
            self.log.info(
                "The price minimum has to be re-checked since it is at the end of a day and the price rates for tomorrow are unavailable"
            )

        expected_power_harvested_till_next_minimum = self.sun_forecast_handler.get_solar_output_in_timeframe(
            timestamp_now, next_price_minimum
        )
        self.log.info(
            f"The expected energy harvested by the sun till the next price minimum is {expected_power_harvested_till_next_minimum}"
        )

        if self.absence_handler.check_for_current_absence():
            self.log.info(
                "Currently there is an absence, using the power consumption configured in the environment as the basis for calculation"
            )
            expected_energy_usage_till_next_minimum = self.absence_handler.calculate_power_usage_for_absence(
                timestamp_now, next_price_minimum
            )
        else:
            self.log.info(
                "Currently there is no absence, using last week's power consumption data as the basis for calculation"
            )
            expected_energy_usage_till_next_minimum = self.sems_portal_api_handler.estimate_energy_usage_in_timeframe(
                timestamp_now, next_price_minimum
            )

        if minimum_has_to_be_rechecked:
            power_usage_increase_factor = 20
            self.log.info(
                "Since the real price minimum is unknown at the moment the expected power usage "
                + f"({expected_energy_usage_till_next_minimum}) is increased by {power_usage_increase_factor} %"
            )
            expected_energy_usage_till_next_minimum += expected_energy_usage_till_next_minimum * (
                power_usage_increase_factor / 100
            )

        self.log.info(
            f"The total expected energy usage till the next price minimum is {expected_energy_usage_till_next_minimum}"
        )

        current_state_of_charge = self.inverter.get_state_of_charge()
        current_energy_in_battery = self.inverter.calculate_energy_saved_in_battery_from_state_of_charge(
            current_state_of_charge
        )
        self.log.info(f"The battery is currently holds {current_energy_in_battery} ({current_state_of_charge} %)")

        target_min_state_of_charge = int(EnvironmentVariableGetter.get("INVERTER_TARGET_MIN_STATE_OF_CHARGE", 20))
        energy_to_be_in_battery_when_reaching_next_minimum = (
            self.inverter.calculate_energy_saved_in_battery_from_state_of_charge(target_min_state_of_charge)
        )
        self.log.info(
            f"The battery shall contain {energy_to_be_in_battery_when_reaching_next_minimum} ({target_min_state_of_charge} %) when reaching the next minimum"
        )

        summary_of_energy_vales = {
            "timestamp now": str(timestamp_now),
            "next price minimum": str(next_price_minimum),
            "expected power harvested till next minimum": expected_power_harvested_till_next_minimum,
            "expected energy usage till next minimum": expected_energy_usage_till_next_minimum,
            "current state of charge": current_state_of_charge,
            "current energy in battery": current_energy_in_battery,
            "target min state of charge": target_min_state_of_charge,
            "energy to be in battery when reaching next minimum": energy_to_be_in_battery_when_reaching_next_minimum,
            "minimum_has_to_be_rechecked": minimum_has_to_be_rechecked,
        }
        self.log.debug(f"Summary of energy values: {summary_of_energy_vales}")

        excess_energy = (
            current_energy_in_battery
            + expected_power_harvested_till_next_minimum
            - expected_energy_usage_till_next_minimum
            - energy_to_be_in_battery_when_reaching_next_minimum
        )
        if excess_energy.watt_hours > 0:
            self.log.info(f"There is {excess_energy} of excess energy, thus there is no need to charge")
            return next_price_minimum, minimum_has_to_be_rechecked

        missing_energy = excess_energy * -1
        self.log.info(f"There is a need to charge {missing_energy}")

        required_energy_in_battery = current_energy_in_battery + missing_energy
        required_state_of_charge = self.inverter.calculate_state_of_charge_from_energy_amount(
            required_energy_in_battery
        )
        self.log.info(f"Need to charge to {required_state_of_charge} %")

        max_target_soc_environment_variable = "INVERTER_MAX_TARGET_SOC"
        max_target_soc = int(EnvironmentVariableGetter.get(max_target_soc_environment_variable, 90))
        if required_state_of_charge > max_target_soc:
            self.log.info(
                "The target state of charge is more than the maximum allowed charge set in the environment "
                + f'("{max_target_soc_environment_variable}") --> Setting it to {max_target_soc} %'
            )
            required_state_of_charge = max_target_soc

        energy_bought_before_charging = self.sems_portal_api_handler.get_energy_buy()
        timestamp_starting_to_charge = TimeHandler.get_time()
        self.log.debug(f"The amount of energy bought before charging is {energy_bought_before_charging}")

        self._charge_inverter(required_state_of_charge)

        timestamp_ending_to_charge = TimeHandler.get_time()

        duration_to_wait_for_semsportal_update = timedelta(minutes=10)
        self.log.info(
            f"Sleeping for {duration_to_wait_for_semsportal_update} to let the SEMS Portal update its power consumption data..."
        )
        pause.seconds(duration_to_wait_for_semsportal_update.total_seconds())

        energy_bought = self._calculate_amount_of_energy_bought(
            energy_bought_before_charging,
            timestamp_starting_to_charge,
            timestamp_ending_to_charge + duration_to_wait_for_semsportal_update,
        )
        self.log.info(f"Bought {energy_bought} to charge the battery")

        self._write_energy_buy_statistics_to_file(
            timestamp_starting_to_charge, timestamp_ending_to_charge, energy_bought
        )

        return next_price_minimum, minimum_has_to_be_rechecked

    def _charge_inverter(self, target_state_of_charge: int) -> None:
        """
        Charges the inverter until a given state of charge is reached.
        Checks every few minutes the current state of charge and compares to the target value.

        Args:
            target_state_of_charge: The desired state of charge percentage to reach before stopping the charging process.
        """
        charging_progress_check_interval = timedelta(minutes=5)
        dry_run = EnvironmentVariableGetter.get(name_of_variable="DRY_RUN", default_value=True)

        self.log.info("Starting to charge")
        self.inverter.set_operation_mode(OperationMode.ECO_CHARGE)

        self.log.info(
            f"Set the inverter to charge, the target state of charge is {target_state_of_charge} %. Checking the charging progress every {charging_progress_check_interval}..."
        )

        error_counter = 0
        while True:
            if error_counter == 3:
                self.log.error(
                    f"An error occurred {error_counter} times while trying to get the current state of charge --> Stopping the charging process"
                )
                # Can't set the mode of the inverter as it is unresponsive
                break

            pause.seconds(charging_progress_check_interval.total_seconds())

            try:
                if self.inverter.get_operation_mode() != OperationMode.ECO_CHARGE:
                    self.log.warning(
                        "The operation mode of the inverter changed from the user --> Stopping the charging progress"
                    )
                    break

                current_state_of_charge = self.inverter.get_state_of_charge()

                error_counter = 0
            except RequestFailedException as e:
                self.log.exception(f"An exception occurred while trying to fetch the current state of charge: {e}")
                self.log.warning(f"Waiting for {charging_progress_check_interval} to try again...")
                error_counter += 1
                continue

            if dry_run:
                self.log.debug(
                    f"Assuming state of charge is {target_state_of_charge} % (actually it is {current_state_of_charge} %) since dry run is enabled"
                )
                current_state_of_charge = target_state_of_charge

            if current_state_of_charge >= target_state_of_charge:
                self.log.info(
                    f"Charging finished ({current_state_of_charge} %) --> Setting the inverter back to normal mode"
                )
                self.inverter.set_operation_mode(OperationMode.GENERAL)
                break

            self.log.debug(
                f"Charging is still ongoing (current: {current_state_of_charge} %, target: >= {target_state_of_charge} %) --> Waiting for another {charging_progress_check_interval}..."
            )

    def _calculate_amount_of_energy_bought(
        self,
        energy_bought_before_charging: EnergyAmount,
        timestamp_starting_to_charge: datetime,
        timestamp_ending_to_charge: datetime,
    ) -> EnergyAmount:
        if timestamp_starting_to_charge.date() == timestamp_ending_to_charge.date():
            energy_bought_today_after_charging = self.sems_portal_api_handler.get_energy_buy()
            self.log.debug(
                f"It is till the same day since starting to charge, the amount of energy bought after charging is {energy_bought_today_after_charging}"
            )
            return energy_bought_today_after_charging - energy_bought_before_charging

        energy_bought_today_after_charging = self.sems_portal_api_handler.get_energy_buy()
        energy_bought_yesterday = self.sems_portal_api_handler.get_energy_buy(1) - energy_bought_before_charging
        self.log.debug(
            f"It is the next day since starting to charge, the amount of energy bought after charging (today) is {energy_bought_today_after_charging}, the amount of energy bought after charging (yesterday) is {energy_bought_yesterday}"
        )
        return energy_bought_today_after_charging + energy_bought_yesterday

    def _write_energy_buy_statistics_to_file(
        self, timestamp_starting_to_charge: datetime, timestamp_ending_to_charge: datetime, energy_bought: EnergyAmount
    ) -> None:
        filename = super().directory_of_logs + "/energy_buy.log"
        with open(filename, "a") as f:
            f.write(
                f"{timestamp_starting_to_charge.isoformat()}\t{timestamp_ending_to_charge.isoformat()}\t{int(energy_bought.watt_hours)}\n"
            )
