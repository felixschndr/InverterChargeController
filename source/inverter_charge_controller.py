from datetime import datetime, timedelta

import pause
from aiohttp import ClientError
from dateutil import tz
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

        self.log.trace("Initializing...")

        self.timezone = tz.gettz(EnvironmentVariableGetter.get("TIMEZONE"))

        self.sems_portal_api_handler = SemsPortalApiHandler(self.timezone)
        self.sun_forecast_handler = SunForecastHandler(self.timezone)
        self.inverter = Inverter()
        self.tibber_api_handler = TibberAPIHandler()

    async def start(self) -> None:
        self.log.info("Starting application")

        first_iteration = True
        duration_to_wait_in_cause_of_error = timedelta(minutes=10)
        while True:
            try:
                if first_iteration:
                    self.log.info("Checking what has to be done to reach the next minimum...")
                    first_iteration = False
                else:
                    self.log.info(
                        "Waiting is over, now is the a price minimum, Checking what has to be done to reach the next minimum..."
                    )

                next_price_minimum = await self._do_iteration()
                self.log.info(f"The next price minimum is at {next_price_minimum}. Waiting until then...")
                pause.until(next_price_minimum)

            except (ClientError, RequestException) as e:
                self.log.exception(f"An exception occurred while trying to fetch data from a different system: {e}")
                self.log.warning(f"Waiting for {duration_to_wait_in_cause_of_error} to try again...")
                pause.seconds(duration_to_wait_in_cause_of_error.total_seconds())

            except Exception as e:
                self.log.exception(f"An unexpected error occurred: {e}")
                self.log.critical("Exiting now...")
                exit(1)

    async def _do_iteration(self) -> datetime:  # FIXME: Find better name
        timestamp_now = datetime.now(tz=self.timezone)

        next_price_minimum = await self.tibber_api_handler.get_next_price_minimum_timestamp()
        self.log.info(f"The next price minimum is at {next_price_minimum}")

        expected_power_harvested_till_next_minimum_in_watt_hours = (
            self.sun_forecast_handler.get_solar_output_in_timeframe_in_watt_hours(timestamp_now, next_price_minimum)
        )
        self.log.info(
            f"The expected energy harvested by the sun till the next price minimum is {expected_power_harvested_till_next_minimum_in_watt_hours} Wh"
        )

        expected_energy_usage_till_next_minimum_in_watt_hours = (
            self.sems_portal_api_handler.get_energy_usage_in_timeframe_in_watt_hours(timestamp_now, next_price_minimum)
        )
        self.log.info(
            f"The expected energy usage till the next price minimum is {expected_energy_usage_till_next_minimum_in_watt_hours} Wh"
        )

        current_state_of_charge = self.sems_portal_api_handler.get_state_of_charge()
        energy_in_battery_in_watt_hours = self.inverter.calculate_energy_saved_in_battery_from_state_of_charge(
            current_state_of_charge
        )
        self.log.info(
            f"The battery is currently at {current_state_of_charge}%, thus it is holding {energy_in_battery_in_watt_hours} Wh"
        )

        self.log.info("Would calculate amount to be charged and charge if necessary. To be implemented...")
        # TODO: Implement amount of energy to be charged
        # TODO: Implement charging itself

        return next_price_minimum

    async def _charge_inverter(
        self,
        starting_time: datetime,
        duration_to_charge: timedelta,
        charging_price: float,
    ) -> None:
        target_state_of_charge = int(EnvironmentVariableGetter.get("INVERTER_TARGET_STATE_OF_CHARGE", 98))
        charging_progress_check_interval = timedelta(minutes=10)
        dry_run = EnvironmentVariableGetter.get(name_of_variable="DRY_RUN", default_value=True)

        self.log.info(
            f"Calculated starting time to charge: {starting_time.strftime('%H:%M')} with an average rate {charging_price:.3f} €/kWh, waiting until then..."
        )
        pause.until(starting_time)

        energy_buy_of_today_before_charging = self.sems_portal_api_handler.get_energy_buy_of_today()
        self.log.debug(f"The amount of energy bought before charging is {energy_buy_of_today_before_charging} Wh")

        self.log.info("Starting to charge")
        await self.inverter.set_operation_mode(OperationMode.ECO_CHARGE)

        self.log.info(
            f"Set the inverter to charge, the estimated charging duration is {duration_to_charge}. Checking every {charging_progress_check_interval} the state of charge..."
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
                await self.inverter.set_operation_mode(OperationMode.GENERAL)
                break

            self.log.debug(
                f"Charging is still ongoing (current: {current_state_of_charge}%, target: >= {target_state_of_charge}%) --> Waiting for another {charging_progress_check_interval}..."
            )

        energy_buy_of_today_after_charging = self.sems_portal_api_handler.get_energy_buy_of_today()
        self.log.debug(f"The amount of energy bought after charging is {energy_buy_of_today_after_charging} Wh")

        energy_bought_through_charging = energy_buy_of_today_after_charging - energy_buy_of_today_before_charging
        cost_to_charge = energy_bought_through_charging / 1000 * charging_price
        self.log.info(
            f"Bought {energy_bought_through_charging} Wh to charge the battery, cost about {cost_to_charge:.2f} €"
        )
