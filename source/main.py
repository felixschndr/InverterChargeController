import asyncio
from datetime import datetime

import pause
from goodwe import OperationMode

from source.inverter import Inverter
from source.logger import LoggerMixin
from source.price_slice import PriceSlice
from source.sems_portal_api_handler import SemsPortalApiHandler
from source.sun_forecast_api_handler import SunForecastAPIHandler
from source.tibber_api_handler import TibberAPIHandler


class Main(LoggerMixin):
    def __init__(self, dry_run: bool = True):
        """
        :param dry_run: If True, the operation will be simulated and no changes to the operation mode of the inverter will be made. Defaults to True.
        """
        super().__init__()

        self.log.info("Initializing...")

        self.sems_portal_api_handler = SemsPortalApiHandler()
        self.sun_forecast_api_handler = SunForecastAPIHandler()
        self.inverter = Inverter(dry_run)
        self.tibber_api_handler = TibberAPIHandler()

        self.log.info("Finished initializing")

    async def run(self) -> None:
        self.log.info("Starting working...")

        expected_power_consumption_today = (
            self.sems_portal_api_handler.get_average_power_consumption_per_day()
        )
        self.log.info(
            f"The average power consumption - and thus expected power consumption for today - is {expected_power_consumption_today:.2f} Wh"
        )

        # expected_power_generation_today = (
        #     self.sun_forecast_api_handler.get_solar_output_in_watt_hours()
        # )
        expected_power_generation_today = (
            self.sun_forecast_api_handler._get_debug_solar_output_in_watt_hours()
        )
        self.log.info(
            f"The expected solar output for today is {expected_power_generation_today} Wh"
        )

        excess_power = (
            expected_power_generation_today - expected_power_consumption_today
        )
        excess_power = -1000
        if excess_power > 0:
            self.log.info(
                f"The expected solar output is greater than the expected power consumption ({excess_power} Wh) --> There is no need to charge"
            )
        else:
            self.log.info(
                f"The expected solar output is less than the expected power consumption ({abs(excess_power)} Wh) --> There is a need to charge"
            )
            duration_to_charge = self.inverter.calculate_necessary_duration_to_charge(
                expected_power_consumption_today
            )
            self.log.info(
                f"Calculated estimated duration to charge: {duration_to_charge} hours"
            )
            starting_time, charging_price = await self._find_start_time_to_charge(
                duration_to_charge
            )
            self.log.info(
                f"Calculated starting time to charge: {starting_time.strftime('%H:%M')} with an average rate {charging_price:.3f} €/kWh, waiting until then..."
            )
            pause.until(starting_time)
            self.log.info("Starting charging")
            await self.inverter.set_operation_mode(OperationMode.ECO_CHARGE)
            self.log.info(
                f"Set the inverter to charge, waiting for {duration_to_charge} hours..."
            )
            pause.hours(duration_to_charge)
            self.log.info("Charging finished. Setting the inverter back to normal mode")
            await self.inverter.set_operation_mode(OperationMode.GENERAL)

        self.log.info("Finished operation for today, stopping now")
        exit(0)

    @staticmethod
    def _calculate_price_slices(
        prices_of_tomorrow: list[PriceSlice], slice_size: int
    ) -> list[list[PriceSlice]]:
        """
        Calculates all possible slices of prices which are <slice_size> long.
        Example:
            Input:
                [
                    PriceSlice('rate': 0.2903, 'startsAt': datetime('2024-10-02T00:00:00.000+02:00')),
                    PriceSlice('rate': 0.2849, 'startsAt': datetime('2024-10-02T01:00:00.000+02:00')),
                    PriceSlice('rate': 0.2804, 'startsAt': datetime('2024-10-02T02:00:00.000+02:00')),
                    PriceSlice('rate': 0.2778, 'startsAt': datetime('2024-10-02T03:00:00.000+02:00')),
                ]
                hours = 2
            Output:
                [
                    [PriceSlice('rate': 0.2903, 'startsAt': datetime('2024-10-02T00:00:00.000+02:00')), PriceSlice('rate': 0.2849, 'startsAt': datetime('2024-10-02T01:00:00.000+02:00'))],
                    [PriceSlice('rate': 0.2849, 'startsAt': datetime('2024-10-02T01:00:00.000+02:00')), PriceSlice('rate': 0.2804, 'startsAt': datetime('2024-10-02T02:00:00.000+02:00'))],
                    [PriceSlice('rate': 0.2804, 'startsAt': datetime('2024-10-02T02:00:00.000+02:00')), PriceSlice('rate': 0.2778, 'startsAt': datetime('2024-10-02T03:00:00.000+02:00'))]
                ]

        :param prices_of_tomorrow: List of dictionaries containing prices for each hour of the next day.
        :param slice_size: Number of hours for each price slice.
        :return: List of lists, where each sublist contains a slice of the original prices for a given number of hours.
        """
        slices = []
        for i in range(len(prices_of_tomorrow) - slice_size + 1):
            slices.append(prices_of_tomorrow[i : i + slice_size])

        return slices

    @staticmethod
    def _determine_cheapest_price_slice(
        price_slices_combinations: list[list[PriceSlice]],
    ) -> list[PriceSlice]:
        """
        :param price_slices_combinations: A list of lists, where each sublist contains PriceSlice objects representing different slice combinations.
        :return: The sublist from price_slices_combinations that has the lowest aggregate rate.
        """
        return min(
            price_slices_combinations,
            key=lambda price_slice_combination: sum(
                price_slice.rate for price_slice in price_slice_combination
            ),
        )

    async def _find_start_time_to_charge(
        self, charging_duration: int
    ) -> tuple[datetime, float]:
        """
        :param charging_duration: The duration (in hours) for which the charging is needed.
        :return: A tuple containing the start time (as a datetime object) when charging should begin and the average price (as a float) for the charging duration.
        """
        prices_of_tomorrow = await self.tibber_api_handler.get_prices_of_tomorrow()
        price_slices = self._calculate_price_slices(
            prices_of_tomorrow=prices_of_tomorrow, slice_size=charging_duration
        )
        cheapest_slice = self._determine_cheapest_price_slice(price_slices)
        average_charging_price = self._calculate_average_price_of_slice(cheapest_slice)
        starting_time = cheapest_slice[0].timestamp

        return starting_time, average_charging_price

    @staticmethod
    def _calculate_average_price_of_slice(price_slices: list[PriceSlice]) -> float:
        """
        :param price_slices: A list of PriceSlice objects
        :return: The average price computed from the given price slices
        """
        total_price = sum(price_slice.rate for price_slice in price_slices)
        return total_price / len(price_slices)


if __name__ == "__main__":
    main = Main()
    asyncio.run(main.run())
