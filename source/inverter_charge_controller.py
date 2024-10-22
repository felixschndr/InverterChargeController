from datetime import datetime, timedelta

import pause
from dateutil import tz
from environment_variable_getter import EnvironmentVariableGetter
from goodwe import OperationMode
from inverter import Inverter
from logger import LoggerMixin
from sems_portal_api_handler import SemsPortalApiHandler
from sun_forecast_handler import SunForecastHandler
from tibber_api_handler import TibberAPIHandler


class InverterChargeController(LoggerMixin):
    def __init__(self):
        super().__init__()

        self.log.trace("Initializing...")

        self.timezone = tz.gettz("Europe/Berlin")  # TODO: Convert to env variable

        self.sems_portal_api_handler = SemsPortalApiHandler(self.timezone)
        self.sun_forecast_handler = SunForecastHandler(self.timezone)
        self.inverter = Inverter()
        self.tibber_api_handler = TibberAPIHandler()

    async def run(self) -> None:
        self.log.info("Starting application")

        first_iteration = True
        while True:
            if first_iteration:
                self.log.info(
                    "Checking what has to be done to reach the next minimum..."
                )
                first_iteration = False
            else:
                self.log.info(
                    "Waiting is over, now is the a price minimum, Checking what has to be done to reach the next minimum..."
                )

            next_price_minimum = (
                await self.tibber_api_handler.get_next_price_minimum_timestamp()
            )
            self.log.info(f"The next price minimum is at {next_price_minimum}")

            timestamp_now = datetime.now(tz=self.timezone)
            expected_power_generation_till_next_minimum = (
                self.sun_forecast_handler.get_solar_output_in_timeframe_in_watt_hours(
                    timestamp_now, next_price_minimum
                )
            )
            self.log.info(
                f"The expected solar output till the next price minimum is {expected_power_generation_till_next_minimum} Wh"
            )

            expected_power_usage_till_next_minimum = (
                self.sems_portal_api_handler.get_power_usage_in_timeframe_in_watt_hours(
                    timestamp_now, next_price_minimum
                )
            )
            self.log.info(
                f"The expected power usage till the next price minimum is {expected_power_usage_till_next_minimum} Wh"
            )

            # TODO: Implement checking of battery
            # TODO: Implement amount of energy to be charged
            # TODO: Implement charging itself
            self.log.info(
                "Would check battery status, calculate amount to be charged and charge if necessary. To be implemented..."
            )

            self.log.info(
                f"The next price minimum is at {next_price_minimum}. Waiting until then..."
            )
            pause.until(next_price_minimum)

    async def _charge_inverter(
        self,
        starting_time: datetime,
        duration_to_charge: timedelta,
        charging_price: float,
    ) -> None:
        target_state_of_charge = int(
            EnvironmentVariableGetter.get("INVERTER_TARGET_STATE_OF_CHARGE", 98)
        )
        charging_progress_check_interval = timedelta(minutes=10)
        dry_run = EnvironmentVariableGetter.get(
            name_of_variable="DRY_RUN", default_value=True
        )

        self.log.info(
            f"Calculated starting time to charge: {starting_time.strftime('%H:%M')} with an average rate {charging_price:.3f} €/kWh, waiting until then..."
        )
        pause.until(starting_time)

        power_buy_of_today_before_charging = (
            self.sems_portal_api_handler.get_power_buy_of_today()
        )
        self.log.debug(
            f"The amount of power bought before charging is {power_buy_of_today_before_charging} Wh"
        )

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

        power_buy_of_today_after_charging = (
            self.sems_portal_api_handler.get_power_buy_of_today()
        )
        self.log.debug(
            f"The amount of power bought after charging is {power_buy_of_today_after_charging} Wh"
        )

        power_buy_through_charging = (
            power_buy_of_today_after_charging - power_buy_of_today_before_charging
        )
        cost_to_charge = power_buy_through_charging / 1000 * charging_price
        self.log.info(
            f"Bought {power_buy_through_charging} Wh to charge the battery, cost about {cost_to_charge:.2f} €"
        )
