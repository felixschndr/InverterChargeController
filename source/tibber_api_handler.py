from datetime import datetime, timedelta

from database_handler import DatabaseHandler, InfluxDBField
from energy_classes import EnergyRate
from environment_variable_getter import EnvironmentVariableGetter
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from logger import LoggerMixin
from time_handler import TimeHandler


class TibberAPIHandler(LoggerMixin):
    MAXIMUM_THRESHOLD = 3  # in cents/kWh
    MINIMUM_CHARGING_DURATION = timedelta(hours=1)

    def __init__(self):
        super().__init__()

        transport = AIOHTTPTransport(
            url="https://api.tibber.com/v1-beta/gql",
            headers={"Authorization": EnvironmentVariableGetter.get("TIBBER_API_TOKEN")},
        )
        self.client = Client(transport=transport, fetch_schema_from_transport=True)

        self.database_handler = DatabaseHandler("energy_prices")

        self.energy_rates_are_in_15_minute_tacts = False

    def get_next_price_minimum(
        self, first_iteration: bool = False, upcoming_energy_rates: list[EnergyRate] = None
    ) -> EnergyRate:
        """
        This method performs a series of operations to determine the most cost-effective time to charge by analyzing
        upcoming energy rates retrieved from the Tibber API and returns its timestamp.

        Looking at the prices trends, it can be seen that the optimal time to charge is the minimum between the first
        maximum and the subsequent maximum.

        A maximum is set to only be a maximum if the price is at least MAXIMUM_THRESHOLD € higher than the minimum
        found until this point. This is done since sometimes there is a downward sloping trend in which there are one or
        two rates that are not smaller than the ones before but instead just a little higher (about 0.5-1.5 cents).
        Without this threshold, these values would be interpreted as maximums (that there are not).
        TLDR: Introduce a maximum threshold to better identify real maximum energy rates, preventing minor fluctuations
        from being misinterpreted as maxima.

        Steps:
        1. Fetches the upcoming energy prices from the API.
        2. Extracts energy rates from the API response.
        3. Filters out energy rates that are in the past.
        4. Gets energy rates up between the first and second maximum rate.
        5. Finds the minimum of the filtered energy rates.
        6. Determines the maximum duration for which charging is feasible under given energy rate constraints.

        Args:
            first_iteration: A boolean flag indicating whether this is the first iteration of fetching upcoming prices.

        Returns:
            EnergyRate: The next price minimum energy rate.
        """
        self.log.trace("Finding the price minimum...")
        if upcoming_energy_rates is None:
            upcoming_energy_rates = self.get_upcoming_energy_rates()
        if first_iteration and self._check_if_next_prices_are_on_a_decline(upcoming_energy_rates):
            self.log.debug(
                "This is the first time finding the minimum prices and the prices are currently on a decline. "
                "Thus the next price minimum is considered (instead of the one after the first maximum)."
            )
            energy_rates_between_first_and_second_maximum = self._find_energy_rates_till_first_maximum(
                upcoming_energy_rates
            )
        else:
            energy_rates_between_first_and_second_maximum = self._get_energy_rates_between_first_and_second_maximum(
                upcoming_energy_rates, first_iteration
            )
        minimum_of_energy_rates = self.get_global_minimum_of_energy_rates(
            energy_rates_between_first_and_second_maximum
        )

        if self._check_if_minimum_is_at_end_of_day_and_energy_rates_of_tomorrow_are_unavailable(
            minimum_of_energy_rates, upcoming_energy_rates
        ):
            minimum_of_energy_rates.has_to_be_rechecked = True

        return minimum_of_energy_rates

    def get_upcoming_energy_rates(self) -> list[EnergyRate]:
        self.log.debug("Fetching the upcoming energy rates from the Tibber API...")
        api_result = self._fetch_upcoming_prices_from_api()
        all_energy_rates = self._extract_energy_rates_from_api_response(api_result)

        self.energy_rates_are_in_15_minute_tacts = (
            all_energy_rates[0].timestamp + timedelta(minutes=20) > all_energy_rates[1].timestamp
        )
        self.log.debug(f"The energy rates are in 15 minute tacts: {self.energy_rates_are_in_15_minute_tacts}")

        self.write_energy_rates_to_database(all_energy_rates)
        return self._remove_energy_rates_from_the_past(all_energy_rates)

    @staticmethod
    def _check_if_next_prices_are_on_a_decline(all_upcoming_energy_rates: list[EnergyRate]) -> bool:
        """
        Args:
            all_upcoming_energy_rates (list[EnergyRate]): List of upcoming energy rates.

        Returns:
            bool: True if the average of the second, third, and fourth rates is higher than the first rate.
        """
        future_energy_rates_to_consider = 3
        if len(all_upcoming_energy_rates) < future_energy_rates_to_consider + 1:
            return False  # Not enough data to compare, should never happen

        considered_upcoming_energy_rates = all_upcoming_energy_rates[1 : future_energy_rates_to_consider + 1]
        average_of_considered_upcoming_energy_rates = sum(
            energy_rate.rate for energy_rate in considered_upcoming_energy_rates
        ) / len(considered_upcoming_energy_rates)
        return average_of_considered_upcoming_energy_rates < all_upcoming_energy_rates[0].rate

    def _fetch_upcoming_prices_from_api(self) -> dict:
        """
        This method constructs a GraphQL query to retrieve the electricity prices for the current day and the following
        day.

        Returns:
            dict: A dictionary containing the electricity prices for today and tomorrow.
        """
        query = gql(
            """
            {
                viewer {
                    homes {
                        currentSubscription {
                            priceInfo {
                                today {
                                    total
                                    startsAt
                                }
                                tomorrow {
                                    total
                                    startsAt
                                }
                            }
                        }
                    }
                }
            }
        """
        )
        self.log.trace("Crawling the Tibber API for the electricity prices")
        response = self.client.execute(query)
        self.log.trace(f"Retrieved data: {response}")
        return response

    def _extract_energy_rates_from_api_response(self, api_result: dict) -> list[EnergyRate]:
        """
        Extracts energy rates from the API response and returns them as a list of EnergyRate objects.

        Args:
            api_result: The dictionary containing the API response with energy rate information.

        Returns:
            A list of EnergyRate objects, each containing the rate and timestamp extracted from the API response.
        """
        prices_raw = api_result["viewer"]["homes"][0]["currentSubscription"]["priceInfo"]
        upcoming_energy_rates = []
        for price in [*(prices_raw["today"]), *(prices_raw["tomorrow"])]:
            upcoming_energy_rates.append(
                EnergyRate(
                    rate=round(price["total"] * 100, 2),
                    timestamp=datetime.fromisoformat(price["startsAt"]),
                )
            )

        self.log.trace(f"Extracted the the energy rates from the API response {upcoming_energy_rates}")
        return upcoming_energy_rates

    def _remove_energy_rates_from_the_past(self, all_energy_rates: list[EnergyRate]) -> list[EnergyRate]:
        """
        Returns a list of energy rates that are dated in the past relative to the current hour.

        Args:
            all_energy_rates: A list of EnergyRate objects where each object has a timestamp attribute.

        Returns:
            A list of EnergyRate objects that have timestamps in the future relative to the beginning of the current hour.
        """
        beginning_of_current_hour = TimeHandler.get_time(sanitize_seconds=True).replace(minute=0)

        upcoming_energy_rates = [
            energy_rate for energy_rate in all_energy_rates if energy_rate.timestamp > beginning_of_current_hour
        ]
        self.log.debug(f"The Upcoming energy rates are {upcoming_energy_rates}")
        return upcoming_energy_rates

    def _get_energy_rates_between_first_and_second_maximum(
        self, upcoming_energy_rates: list[EnergyRate], first_iteration: bool
    ) -> list[EnergyRate]:
        """
        Returns a list of the upcoming energy rates starting from the first maximum rate (excluding the rates leading up
        to the first maximum) and ending at the second minimum rate.

        Args:
            upcoming_energy_rates: List of EnergyRate objects representing the upcoming energy rates.

        Returns:
            List of EnergyRate objects that start between the first and second maximum energy rates.
        """
        energy_rates_ending_at_first_maximum = self._find_energy_rates_till_first_maximum(
            upcoming_energy_rates, first_iteration
        )

        first_maximum_energy_rate = energy_rates_ending_at_first_maximum.pop()
        energy_rates_starting_at_first_maximum = upcoming_energy_rates.copy()
        for energy_rate in energy_rates_ending_at_first_maximum:
            energy_rates_starting_at_first_maximum.remove(energy_rate)

        self.log.trace(f"Found {first_maximum_energy_rate} to be the first maximum of the upcoming energy rates")

        energy_rates_between_first_and_second_maximum = self._find_energy_rates_till_first_maximum(
            energy_rates_starting_at_first_maximum
        )
        self.log.trace(
            f"Found {energy_rates_between_first_and_second_maximum[-1]} to be the second maximum of the upcoming energy rates"
        )

        return energy_rates_between_first_and_second_maximum

    @staticmethod
    def _find_energy_rates_till_first_maximum(
        upcoming_energy_rates: list[EnergyRate], first_run: bool = False
    ) -> list[EnergyRate]:
        last_energy_rate = minimum_energy_rate_found_until_now = upcoming_energy_rates[0]
        last_energy_rate_was_maximum = False
        energy_rates_till_maximum = []

        for current_energy_rate in upcoming_energy_rates:
            if current_energy_rate < minimum_energy_rate_found_until_now:
                minimum_energy_rate_found_until_now = current_energy_rate

            if current_energy_rate > last_energy_rate and (
                first_run
                or current_energy_rate.rate
                > minimum_energy_rate_found_until_now.rate + TibberAPIHandler.MAXIMUM_THRESHOLD
            ):
                last_energy_rate_was_maximum = True

            if current_energy_rate < last_energy_rate and last_energy_rate_was_maximum:
                break

            energy_rates_till_maximum.append(current_energy_rate)
            last_energy_rate = current_energy_rate

        return energy_rates_till_maximum

    def get_global_minimum_of_energy_rates(self, energy_rates_till_maximum: list[EnergyRate]) -> EnergyRate:
        """
        Determines the global minimum energy rate from a list of energy rates (in this case up until the first maximum).

        Args:
            energy_rates_till_maximum: A list of EnergyRate objects from which the global minimum is to be determined.

        Returns:
            EnergyRate: The EnergyRate object that has the lowest rate from the provided list.
        """
        global_minimum_of_energy_rates = min(energy_rates_till_maximum, key=lambda energy_rate: energy_rate.rate)
        self.log.debug(
            f"Found {global_minimum_of_energy_rates} to be the global minimum of the energy rates between the first and second maximum"
        )
        return global_minimum_of_energy_rates

    def _check_if_minimum_is_at_end_of_day_and_energy_rates_of_tomorrow_are_unavailable(
        self, price_minimum: EnergyRate, upcoming_energy_rates: list[EnergyRate]
    ) -> bool:
        """
        This method determines whether the timestamp of the `price_minimum` is in the last hour of the day and checks if
        there are no energy rates available for the subsequent day.
        This is done since the price rates of the next day are only available after ~ 02:00 PM. If the price rates of
        the next day are unavailable while determining the price minimum, it is likely that the price minimum is just
        the last rate of the day but not actually the minimum.
        In this case, we have to check in later (at ~ 02:00 PM) to re-request the prices from the Tibber API to get
        the values of the next day.

        Args:
            price_minimum (EnergyRate): The energy rate with the minimum price.
            upcoming_energy_rates (list[EnergyRate]): List of upcoming energy rates.

        Returns:
            bool: True if the price minimum is in the last hour current day and there are no rates for
                the next day, otherwise False.
        """

        price_minimum_is_near_end_of_day = price_minimum.timestamp.hour == 23
        if self.energy_rates_are_in_15_minute_tacts:
            price_minimum_is_near_end_of_day = (
                price_minimum_is_near_end_of_day and price_minimum.timestamp.minute == 45
            )
        self.log.trace(
            f"The price minimum {price_minimum.timestamp} is at the end of the day: {price_minimum_is_near_end_of_day}"
        )

        today = datetime.now().date()
        are_tomorrows_rates_unavailable = all(rate.timestamp.date() == today for rate in upcoming_energy_rates)
        self.log.trace(f"The price rates for tomorrow are unavailable: {are_tomorrows_rates_unavailable}")

        return price_minimum_is_near_end_of_day and are_tomorrows_rates_unavailable

    def get_energy_rate_before_and_after_the_price_is_higher_than_the_average_until_timestamp(
        self, upcoming_energy_rates: list[EnergyRate], ending_timestamp: datetime
    ) -> tuple[EnergyRate, EnergyRate]:
        """
        Identifies two specific energy rates from a list of upcoming energy rates up to a given timestamp:
        the last rate before the price is higher than the average and the first rate

        Args:
            upcoming_energy_rates (list[EnergyRate]): The list of upcoming energy rates.
            ending_timestamp (datetime): A timestamp limiting the processing to only consider energy rates up to and
                including this time.

        Returns:
            tuple[EnergyRate, EnergyRate]: A tuple containing:
                - The energy rate before the price is higher than the average price up to the provided timestamp.
                - The energy rate after the price is higher than the average price up to the provided timestamp.
        """
        average_price = self._get_average_price_of_energy_rates(upcoming_energy_rates)
        self.log.debug(f"The average price of all upcoming energy rates is {average_price}")

        upcoming_energy_rates_until_ending_timestamp = [
            energy_rate for energy_rate in upcoming_energy_rates if energy_rate.timestamp <= ending_timestamp
        ]

        self.log.trace("Determining the last energy rate before the price is higher than the average price...")
        energy_rate_before_the_price_is_higher_than_the_average = upcoming_energy_rates_until_ending_timestamp[0]
        for energy_rate in upcoming_energy_rates_until_ending_timestamp:
            if energy_rate.rate < average_price:
                self.log.trace(f"The energy rate {energy_rate} is cheaper than the average price")
                energy_rate_before_the_price_is_higher_than_the_average = energy_rate
            else:
                self.log.trace(f"The energy rate {energy_rate} is more expensive than the average price")
                break

        self.log.trace("Determining the first energy rate after the price was higher than the average price...")
        energy_rate_after_the_price_is_higher_than_the_average = upcoming_energy_rates_until_ending_timestamp[-1]
        for energy_rate in reversed(upcoming_energy_rates_until_ending_timestamp):
            if energy_rate.rate < average_price:
                self.log.trace(f"The energy rate {energy_rate} is cheaper than the average price")
                energy_rate_after_the_price_is_higher_than_the_average = energy_rate
            else:
                self.log.trace(f"The energy rate {energy_rate} is more expensive than the average price")
                break

        return (
            energy_rate_before_the_price_is_higher_than_the_average,
            energy_rate_after_the_price_is_higher_than_the_average,
        )

    @staticmethod
    def _get_average_price_of_energy_rates(energy_rates: list[EnergyRate]) -> float:
        return sum(energy_rate.rate for energy_rate in energy_rates) / len(energy_rates)

    def set_maximum_charging_duration_of_current_energy_rate(
        self, current_energy_rate: EnergyRate, upcoming_energy_rates: list[EnergyRate]
    ) -> None:
        """
        Determines and sets the maximum possible charging duration for a given current energy rate based on the upcoming
        energy rates and a predefined rate threshold.

        The function compares the rate of the current energy rate with upcoming rates to find the first rate that
        exceeds the current rate by a specified maximum threshold. The difference between the timestamps of the current
        and identified rate is used to compute the charging duration. A minimum duration threshold of one hour is
        applied if the calculated duration is shorter. This charging duration is then assigned as the maximum charging
        duration for the current energy rate.

        Args:
            current_energy_rate (EnergyRate): The current energy rate input for which the maximum charging duration
                needs to be set.
            upcoming_energy_rates (list[EnergyRate]: A list of upcoming energy rates that are used to compare and
                calculate the charging duration.
        """
        upcoming_energy_rate = current_energy_rate
        for upcoming_energy_rate in upcoming_energy_rates:
            if upcoming_energy_rate.rate > current_energy_rate.rate + TibberAPIHandler.MAXIMUM_THRESHOLD:
                break

        cheap_energy_duration = upcoming_energy_rate.timestamp - current_energy_rate.timestamp
        if self.energy_rates_are_in_15_minute_tacts:
            cheap_energy_duration += timedelta(minutes=15)
        else:
            cheap_energy_duration += timedelta(hours=1)

        current_energy_rate.maximum_charging_duration = max(
            TibberAPIHandler.MINIMUM_CHARGING_DURATION, cheap_energy_duration
        )

    def write_energy_rates_to_database(self, energy_rates: list[EnergyRate]) -> None:
        """
        Writes the list of energy rates to the database while avoiding duplication of already existing data.

        For each energy rate, it checks if the rate's timestamp is newer than the most recently saved timestamp in the
        database. Only energy rates with a newer timestamp are written to the database.

        Args:
            energy_rates (list[EnergyRate]): A list of EnergyRate objects to be written to the database.
        """
        self.log.debug("Writing prices to database...")

        newest_saved_energy_rate = self.database_handler.get_newest_value_of_measurement("rate_start_timestamp")
        if newest_saved_energy_rate is None:
            return

        self.log.trace(f"Newest saved energy rate is from {newest_saved_energy_rate}")
        for energy_rate in energy_rates:
            if energy_rate.timestamp <= newest_saved_energy_rate:
                self.log.trace(f"Skipping energy rate {energy_rate} as it is already saved in the database")
                continue

            self.database_handler.write_to_database(
                [
                    InfluxDBField("price", energy_rate.rate),
                    InfluxDBField("rate_start_timestamp", energy_rate.timestamp.isoformat()),
                ]
            )
