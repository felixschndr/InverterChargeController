import math
from datetime import datetime, timedelta

import pause
from energy_rate import ConsecutiveEnergyRates
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
        self.log.info("Starting working...")

        expected_power_consumption_today = (
            self.sems_portal_api_handler.get_average_power_consumption_per_day()
        )
        self.log.info(
            f"The average power consumption (and thus expected power consumption for today) is {expected_power_consumption_today} Wh"
        )

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

        excess_power = (
            expected_power_generation_today - expected_power_consumption_today
        )

        if excess_power > 0:
            self.log.info(
                f"The expected solar output is greater than the expected power consumption ({excess_power} Wh) --> There is no need to charge"
            )
        else:
            self.log.info(
                f"The expected solar output is less than the expected power consumption ({abs(excess_power)} Wh) --> There is a need to charge"
            )
            state_of_charge = self.sems_portal_api_handler.get_state_of_charge()
            duration_to_charge = self.inverter.calculate_necessary_duration_to_charge(
                state_of_charge
            )
            starting_time, charging_price = await self._find_start_time_to_charge(
                duration_to_charge
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
            EnvironmentVariableGetter.get("INVERTER_TARGET_STATE_OF_CHARGE")
        )
        time_before_charging_end_to_start_checking_state_of_charge = timedelta(
            minutes=30
        )
        waiting_time_if_not_finished_charging = timedelta(minutes=15)

        self.log.info(
            f"Calculated starting time to charge: {starting_time.strftime('%H:%M')} with an average rate {charging_price:.3f} €/kWh, waiting until then..."
        )
        pause.until(starting_time)

        self.log.info("Starting charging")
        await self.inverter.set_operation_mode(OperationMode.ECO_CHARGE)

        duration_to_charge_minus_threshold = max(
            timedelta(0),
            duration_to_charge
            - time_before_charging_end_to_start_checking_state_of_charge,
        )
        self.log.info(
            f"Set the inverter to charge, waiting for an {duration_to_charge_minus_threshold} (estimated duration to charge - threshold of 30 minutes)..."
        )
        pause.seconds(duration_to_charge_minus_threshold.total_seconds())

        dry_run = EnvironmentVariableGetter.get(
            name_of_variable="DRY_RUN", default_value=True
        )
        while True:
            current_state_of_charge = self.sems_portal_api_handler.get_state_of_charge()

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
                f"Charging is still ongoing (current: {current_state_of_charge}%, target: >= {target_state_of_charge}%) --> Waiting for {waiting_time_if_not_finished_charging}..."
            )
            pause.seconds(waiting_time_if_not_finished_charging.total_seconds())

    @staticmethod
    def _calculate_consecutive_energy_rates(
        consecutive_energy_rates: ConsecutiveEnergyRates, slice_size: int
    ) -> list[ConsecutiveEnergyRates]:
        """
        Calculates all possible slices of EnergyRates which are <slice_size> long.
        Example:
            Input:
                ConsecutiveEnergyRates(
                    [
                        EnergyRate('rate': 0.2903, 'startsAt': datetime('2024-10-02T00:00:00.000+02:00')),
                        EnergyRate('rate': 0.2849, 'startsAt': datetime('2024-10-02T01:00:00.000+02:00')),
                        EnergyRate('rate': 0.2804, 'startsAt': datetime('2024-10-02T02:00:00.000+02:00')),
                        EnergyRate('rate': 0.2778, 'startsAt': datetime('2024-10-02T03:00:00.000+02:00')),
                    ]
                )
                hours = 2
            Output:
                [
                    ConsecutiveEnergyRates([EnergyRate('rate': 0.2903, 'startsAt': datetime('2024-10-02T00:00:00.000+02:00')), EnergyRate('rate': 0.2849, 'startsAt': datetime('2024-10-02T01:00:00.000+02:00'))]),
                    ConsecutiveEnergyRates([EnergyRate('rate': 0.2849, 'startsAt': datetime('2024-10-02T01:00:00.000+02:00')), EnergyRate('rate': 0.2804, 'startsAt': datetime('2024-10-02T02:00:00.000+02:00'))]),
                    ConsecutiveEnergyRates([EnergyRate('rate': 0.2804, 'startsAt': datetime('2024-10-02T02:00:00.000+02:00')), EnergyRate('rate': 0.2778, 'startsAt': datetime('2024-10-02T03:00:00.000+02:00'))]
                ]

        :param consecutive_energy_rates: A list of PriceSlice objects representing the prices for tomorrow.
        :param slice_size: An integer representing the size of each price slice to generate.
        :return: A list of ConsecutiveEnergyRates objects where each bundle is a slice of the prices_slices list.
        """
        slices = []
        for i in range(len(consecutive_energy_rates) - slice_size + 1):
            slices.append(
                ConsecutiveEnergyRates(consecutive_energy_rates[i : i + slice_size])
            )

        return slices

    @staticmethod
    def _find_cheapest_consecutive_energy_rates(
        price_slices_combinations: list[ConsecutiveEnergyRates],
    ) -> ConsecutiveEnergyRates:
        """
        :param price_slices_combinations: A list of PriceSliceBundle objects representing different combinations of EnergyRates.
        :return: The ConsecutiveEnergyRates with the lowest total rate.
        """
        return min(
            price_slices_combinations,
            key=lambda price_slice_combination: sum(
                price_slice.rate for price_slice in price_slice_combination
            ),
        )

    @staticmethod
    def _calculate_average_price_of_slice(
        consecutive_energy_rates: ConsecutiveEnergyRates,
    ) -> float:
        """
        :param consecutive_energy_rates: A ConsecutiveEnergyRates containing multiple price slices for calculation.
        :return: The average price of the consecutive_energy_rates.
        """
        total_price = sum(
            price_slice.rate for price_slice in consecutive_energy_rates.slices
        )
        return total_price / len(consecutive_energy_rates)

    async def _find_start_time_to_charge(
        self, charging_duration: timedelta
    ) -> tuple[datetime, float]:
        """
        :param charging_duration: The (estimated) duration which is needed for charging.
        :return: A tuple containing the start time (as a datetime object) when charging should begin and the average price (as a float) for the charging duration.
        """
        prices_of_tomorrow = await self.tibber_api_handler.get_prices_of_tomorrow()
        slice_size = math.ceil(charging_duration.total_seconds() / (60 * 60))
        price_slices = self._calculate_consecutive_energy_rates(
            consecutive_energy_rates=prices_of_tomorrow, slice_size=slice_size
        )
        cheapest_slice = self._find_cheapest_consecutive_energy_rates(price_slices)
        average_charging_price = self._calculate_average_price_of_slice(cheapest_slice)
        starting_time = cheapest_slice[0].timestamp

        return starting_time, average_charging_price
