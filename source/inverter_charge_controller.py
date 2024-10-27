from datetime import datetime, timedelta

import pause
from aiohttp import ClientError
from dateutil import tz
from energy_amount import EnergyAmount
from environment_variable_getter import EnvironmentVariableGetter
from goodwe import OperationMode
from inverter import Inverter
from logger import LoggerMixin
from requests.exceptions import RequestException
from sems_portal_api_handler import SemsPortalApiHandler
from sun_forecast_handler import SunForecastHandler
from tibber_api_handler import TibberAPIHandler


class InverterChargeController(LoggerMixin):
    def __init__(self):
        super().__init__()

        self.log.info("Starting application")

        self.timezone = tz.gettz(EnvironmentVariableGetter.get("TIMEZONE"))

        self.sems_portal_api_handler = SemsPortalApiHandler(self.timezone)
        self.sun_forecast_handler = SunForecastHandler()
        self.inverter = Inverter()
        self.tibber_api_handler = TibberAPIHandler()

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
        first_iteration = False
        duration_to_wait_in_cause_of_error = timedelta(minutes=10)
        while True:
            try:
                if first_iteration:
                    first_iteration = False
                    next_price_minimum = self._do_first_iteration()
                else:
                    next_price_minimum = self._do_iteration()

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

    def _do_first_iteration(self) -> datetime:
        """
        This is the first iteration after starting the program.
        We have to wait for the first price maximum to be able to determine the next price minimum after that maximum.
        After waiting, we can reliably determine the next price minimum.
        Wait until then and then start with the normal operation mode.

        If we did not wait for the first price maximum, all prices until then would be interpreted as minima.

        Returns:
            datetime: The timestamp of the next price minimum after waiting for the first price maximum.
        """
        next_price_maximum = self.tibber_api_handler.get_timestamp_of_next_price_maximum()
        self.log.info(
            f"The next price maximum is at {next_price_maximum}. Waiting until then to be able to find the next price minimum..."
        )

        pause.until(next_price_maximum)

        return self.tibber_api_handler.get_timestamp_of_next_price_minimum()

    def _do_iteration(self) -> datetime:  # FIXME: Find better name
        """
        Computes the optimal charging strategy for an inverter until the next price minimum.

        This method performs several key tasks to determine if and how much the inverter needs to be charged:
        - Retrieves the current timestamp and the next price minimum.
        - Estimates the solar power output and energy usage until the next price minimum.
        - Calculates the current energy stored in the battery based on its state of charge.
        - Compares the current and expected future state with the target minimum state of charge to determine if additional charging is necessary.
        - Initiates charging if required.

        Returns:
            datetime: The timestamp of the next price minimum.
        """
        self.log.info(
            "Waiting is over, now is the a price minimum. Checking what has to be done to reach the next minimum..."
        )

        timestamp_now = datetime.now(tz=self.timezone)

        next_price_minimum = self.tibber_api_handler.get_timestamp_of_next_price_minimum()
        self.log.info(f"The next price minimum is at {next_price_minimum}")

        expected_power_harvested_till_next_minimum = self.sun_forecast_handler.get_solar_output_in_timeframe(
            timestamp_now, next_price_minimum
        )
        self.log.info(
            f"The expected energy harvested by the sun till the next price minimum is {expected_power_harvested_till_next_minimum}"
        )

        expected_energy_usage_till_next_minimum = self.sems_portal_api_handler.get_energy_usage_in_timeframe(
            timestamp_now, next_price_minimum
        )
        self.log.info(
            f"The total expected energy usage till the next price minimum is {expected_energy_usage_till_next_minimum}"
        )

        current_state_of_charge = self.sems_portal_api_handler.get_state_of_charge()
        current_energy_in_battery = self.inverter.calculate_energy_saved_in_battery_from_state_of_charge(
            current_state_of_charge
        )
        self.log.info(
            f"The battery is currently at {current_state_of_charge} %, thus it is holding {current_energy_in_battery}"
        )

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
            return next_price_minimum

        missing_energy = EnergyAmount(excess_energy.watt_hours * -1)
        self.log.info(f"There is a need to charge {missing_energy}")

        required_energy_in_battery = current_energy_in_battery + missing_energy
        required_state_of_charge = self.inverter.calculate_state_of_charge_from_energy_amount(
            required_energy_in_battery
        )
        self.log.info(
            f"Need to charge to {required_state_of_charge} % in order to reach the next minimum with {target_min_state_of_charge} % left"
        )

        # TODO: Implement error handling
        self._charge_inverter(required_state_of_charge)

        return next_price_minimum

    def _charge_inverter(self, target_state_of_charge: int) -> None:
        """
        Charges the inverter until a given state of charge is reached.
        Checks every few minutes the current state of charge and compares to the target value.

        Args:
            target_state_of_charge: The desired state of charge percentage to reach before stopping the charging process.
        """
        charging_progress_check_interval = timedelta(minutes=10)
        dry_run = EnvironmentVariableGetter.get(name_of_variable="DRY_RUN", default_value=True)

        energy_buy_of_today_before_charging = self.sems_portal_api_handler.get_energy_buy_of_today()
        self.log.debug(f"The amount of energy bought before charging is {energy_buy_of_today_before_charging}")

        self.log.info("Starting to charge")
        self.inverter.set_operation_mode(OperationMode.ECO_CHARGE)

        self.log.info(
            f"Set the inverter to charge, the target state of charge is {target_state_of_charge} %. Checking the charging progress every {charging_progress_check_interval}..."
        )

        while True:
            pause.seconds(charging_progress_check_interval.total_seconds())

            current_state_of_charge = self.sems_portal_api_handler.get_state_of_charge()
            self.log.info(f"The current state of charge is {current_state_of_charge}%")

            if dry_run:
                self.log.debug(
                    f"Assuming state of charge is {target_state_of_charge}% (actually it is {current_state_of_charge}%) since dry run is enabled"
                )
                current_state_of_charge = target_state_of_charge

            if current_state_of_charge >= target_state_of_charge:
                self.log.info(
                    f"Charging finished ({current_state_of_charge}%) --> Setting the inverter back to normal mode"
                )
                self.inverter.set_operation_mode(OperationMode.GENERAL)
                break

            self.log.debug(
                f"Charging is still ongoing (current: {current_state_of_charge}%, target: >= {target_state_of_charge}%) --> Waiting for another {charging_progress_check_interval}..."
            )

        energy_buy_of_today_after_charging = self.sems_portal_api_handler.get_energy_buy_of_today()
        self.log.debug(f"The amount of energy bought after charging is {energy_buy_of_today_after_charging}")

        self.log.info(
            f"Bought {energy_buy_of_today_after_charging - energy_buy_of_today_before_charging} to charge the battery"
        )
