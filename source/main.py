import asyncio
from datetime import datetime

import pause
from goodwe import OperationMode

from source.inverter import Inverter
from source.logger import LoggerMixin
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

        expected_power_consumption_tomorrow = (
            self.sems_portal_api_handler.get_average_power_consumption_per_day()
        )
        self.log.info(
            f"The average power consumption - and thus expected power consumption for tomorrow - is {expected_power_consumption_tomorrow:.2f} Wh"
        )

        expected_power_generation_tomorrow = (
            self.sun_forecast_api_handler.get_solar_output_in_watt_hours()
        )
        # expected_power_generation_tomorrow = (
        #     self.sun_forecast_api_handler._get_debug_solar_output_in_watt_hours()
        # )
        self.log.info(
            f"The expected solar output for tomorrow is {expected_power_generation_tomorrow} Wh"
        )

        excess_power = (
            expected_power_generation_tomorrow - expected_power_consumption_tomorrow
        )
        # excess_power = -1000
        if excess_power > 0:
            self.log.info(
                f"The expected solar output is greater than the expected power consumption ({excess_power} Wh) --> There is no need to charge"
            )
        else:
            self.log.info(
                f"The expected solar output is less than the expected power consumption ({abs(excess_power)} Wh) --> There is a need to charge"
            )
            duration_to_charge = self.inverter.calculate_necessary_duration_to_charge(
                expected_power_consumption_tomorrow
            )
            self.log.info(
                f"Calculated estimated duration to charge: {duration_to_charge} hours"
            )
            starting_time, charging_price = await self._find_start_time_to_charge(
                duration_to_charge
            )
            self.log.info(
                f"Calculated starting time to charge: {starting_time} with an average rate {charging_price:.2f} €/kWh, waiting until then..."
            )
            pause.until(starting_time)
            self.log.info("Starting charging")
            await self.inverter.set_operation_mode(OperationMode.ECO_CHARGE)
            self.log.info(
                "Set the inverter to charge, waiting until charge is complete..."
            )
            pause.hours(duration_to_charge)
            self.log.info("Charging finished. Setting the inverter back to normal mode")
            await self.inverter.set_operation_mode(OperationMode.GENERAL)

        self.log.info("Finished operation for today, stopping now")
        exit(0)

    @staticmethod
    def _calculate_price_slices(
        prices_of_tomorrow: list[dict], slice_size: int
    ) -> list[list[dict]]:
        """
        Calculates all possible slices of prices which are <hours> long.
        Example:
            Input:
                [
                    {'total': 0.2903, 'startsAt': '2024-10-02T00:00:00.000+02:00'},
                    {'total': 0.2849, 'startsAt': '2024-10-02T01:00:00.000+02:00'},
                    {'total': 0.2804, 'startsAt': '2024-10-02T02:00:00.000+02:00'},
                    {'total': 0.2778, 'startsAt': '2024-10-02T03:00:00.000+02:00'}
                ]
                hours = 2
            Output:
                [
                    [{'total': 0.2903, 'startsAt': '2024-10-02T00:00:00.000+02:00'}, {'total': 0.2849, 'startsAt': '2024-10-02T01:00:00.000+02:00'}],
                    [{'total': 0.2849, 'startsAt': '2024-10-02T01:00:00.000+02:00'}, {'total': 0.2804, 'startsAt': '2024-10-02T02:00:00.000+02:00'}],
                    [{'total': 0.2804, 'startsAt': '2024-10-02T02:00:00.000+02:00'}, {'total': 0.2778, 'startsAt': '2024-10-02T03:00:00.000+02:00'}]
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
    def _determine_cheapest_price_slice(price_slices: list[list[dict]]) -> list[dict]:
        """
        :param price_slices: A list of lists, where each inner list contains dictionaries with price slot information.
        :return: The list of dictionaries representing the price slice with the lowest total cost.
        """
        return min(
            price_slices,
            key=lambda price_slice: sum(slot["total"] for slot in price_slice),
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
        starting_time = datetime.fromisoformat(cheapest_slice[0]["startsAt"])

        return starting_time, average_charging_price

    @staticmethod
    def _calculate_average_price_of_slice(price_slice: list[dict]) -> float:
        """
        :param price_slice: The list of dictionaries representing a price slice.
        :return: The average price calculated from the given price slice.
        """
        total_price = sum(slot["total"] for slot in price_slice)
        return total_price / len(price_slice)


if __name__ == "__main__":
    main = Main()
    asyncio.run(main.run())
