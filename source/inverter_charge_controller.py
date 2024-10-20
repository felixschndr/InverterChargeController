from datetime import datetime, timedelta

import pause
from environment_variable_getter import EnvironmentVariableGetter
from goodwe import OperationMode
from inverter import Inverter
from logger import LoggerMixin
from sems_portal_api_handler import SemsPortalApiHandler
from sun_forecast_api_handler import SunForecastAPIHandler
from tibber_api_handler import TibberAPIHandler


class InverterChargeController(LoggerMixin):
    def __init__(self):
        super().__init__()

        self.log.info("Initializing...")

        self.sems_portal_api_handler = SemsPortalApiHandler()
        self.sun_forecast_api_handler = SunForecastAPIHandler()
        self.inverter = Inverter()
        self.tibber_api_handler = TibberAPIHandler()

        self.log.info("Finished initializing")

    async def run(self) -> None:
        self.log.info("Starting to work...")

        while True:
            use_debug_solar_output = EnvironmentVariableGetter.get(
                name_of_variable="USE_DEBUG_SOLAR_OUTPUT", default_value=False
            )
            expected_power_generation_today = (
                self.sun_forecast_api_handler._get_debug_solar_output_in_watt_hours()
                if use_debug_solar_output
                else self.sun_forecast_api_handler.get_solar_output_in_watt_hours()
            )
            self.log.info(
                f"The expected solar output for today is {expected_power_generation_today} Wh"
            )

            expected_power_consumption_today = (
                self.sems_portal_api_handler.get_average_power_consumption_per_day()
            )
            self.log.info(
                f"The average power consumption (and thus expected power consumption for today) is {expected_power_consumption_today} Wh"
            )

            current_state_of_charge = self.sems_portal_api_handler.get_state_of_charge()
            missing_energy_in_battery = self.inverter.calculate_energy_missing_from_battery_from_state_of_charge(
                current_state_of_charge
            )
            self.log.info(
                f"The battery is currently at {current_state_of_charge}%, thus {missing_energy_in_battery} Wh are missing from it"
            )

            excess_power = (
                expected_power_generation_today
                - expected_power_consumption_today
                - missing_energy_in_battery
            )

            if excess_power > 0:
                self.log.info(
                    f"The expected solar output is greater than the expected power consumption and missing battery charge ({excess_power} Wh) --> There is no need to charge"
                )
            else:
                self.log.info(
                    f"The expected solar output is less than the expected power consumption and missing battery charge ({abs(excess_power)} Wh) --> There is a need to charge"
                )
                duration_to_charge = (
                    self.inverter.calculate_necessary_duration_to_charge(
                        current_state_of_charge
                    )
                )
                starting_time, charging_price = (
                    await self.tibber_api_handler.find_next_charging_time()
                )

                await self._charge_inverter(
                    starting_time=starting_time,
                    duration_to_charge=duration_to_charge,
                    charging_price=charging_price,
                )

            self.log.info("Finished operation for today, stopping now")
            exit(0)

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
