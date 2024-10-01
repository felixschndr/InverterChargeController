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

        self.dry_run = dry_run

        self.sems_portal_api_handler = SemsPortalApiHandler()
        self.sems_portal_api_handler.login()

        self.sun_forecast_api_handler = SunForecastAPIHandler()

        self.inverter = Inverter()

        self.tibber_api_handler = TibberAPIHandler()

    def run(self) -> None:
        average_power_consumption = (
            self.sems_portal_api_handler.get_average_power_consumption_per_day()
        )
        self.log.info(
            f"The expected power consumption for tomorrow is {average_power_consumption:.2f} Wh"
        )

        # solar_output_tomorrow = sun_forecast.get_solar_output_in_watt_hours()
        solar_output_tomorrow = (
            self.sun_forecast_api_handler._get_debug_solar_output_in_watt_hours()
        )
        self.log.info(
            f"The expected solar output for tomorrow is {solar_output_tomorrow:.2f} Wh"
        )

        if solar_output_tomorrow > average_power_consumption:
            self.log.info(
                "The expected solar output is greater than the expected power consumption. Setting the inverter to normal operation mode."
            )
            if self.dry_run:
                self.log.info(
                    "Would set the inverter to mode GENERAL, but dry run is enabled."
                )
            else:
                self.inverter.set_operation_mode(OperationMode.GENERAL)
        else:
            self.log.info(
                "The expected solar output is less than the expected power consumption. We need to charge..."
            )
            if self.dry_run:
                self.log.info("Would charge the inverter, but dry run is enabled.")
            else:
                pass  # TODO: Build the logic when to charge

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

    def _find_start_time_to_charge(self, charging_duration: int) -> str:
        """
        :param charging_duration: The number of hours for which charging is required.
        :return: The starting timestamp to begin charging, based on the cheapest price slice of electricity for the next day
            in the format YYYY-MM-DDTHH:MM:SS+HH:MM
        """
        prices_of_tomorrow = self.tibber_api_handler.get_prices_of_tomorrow()
        price_slices = self._calculate_price_slices(
            prices_of_tomorrow=prices_of_tomorrow, slice_size=charging_duration
        )
        cheapest_slice = self._determine_cheapest_price_slice(price_slices)

        return cheapest_slice[0]["startsAt"]


if __name__ == "__main__":
    main = Main()
    main.run()
