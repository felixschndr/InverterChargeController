from datetime import datetime

from energy_amount import EnergyRate
from environment_variable_getter import EnvironmentVariableGetter
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from logger import LoggerMixin


class TibberAPIHandler(LoggerMixin):
    def __init__(self):
        super().__init__()

        transport = AIOHTTPTransport(
            url="https://api.tibber.com/v1-beta/gql",
            headers={"Authorization": EnvironmentVariableGetter.get("TIBBER_API_TOKEN")},
        )
        self.client = Client(transport=transport, fetch_schema_from_transport=True)
        self.maximum_threshold = 0.03  # in €

    def get_timestamp_of_next_price_minimum(self, first_iteration: bool = False) -> datetime:
        """
        This method performs a series of operations to determine the most cost-effective time to charge by analyzing
        upcoming energy rates retrieved from the Tibber API and returns its timestamp.

        Looking at the prices trends, it can be seen that the optimal time to charge is the minimum between the first
        maximum and the subsequent maximum.

        A maximum is set to only be a maximum if the price is at least self.maximum_threshold € higher than the minimum
        found until this point. This is done since sometimes there is a downward sloping trend in which there are one or
        two rates that are not smaller than the ones before but instead just a little higher (about 0.5-1.5 cents).
        Without this threshold these values would be interpreted as maximums (that there are not).
        TLDR: Introduce a maximum threshold to better identify real maximum energy rates, preventing minor fluctuations
        from being misinterpreted as maxima.


        Steps:
        1. Fetches the upcoming energy prices from the API.
        2. Extracts energy rates from the API response.
        3. Filters out energy rates that are in the past.
        4. Gets energy rates up between the first and second maximum rate.
        5. Finds the minimum of the filtered energy rates.

        Args:
            first_iteration: A boolean flag indicating whether this is the first iteration of fetching upcoming prices.

        Returns:
            datetime: The timestamp of the next minimum energy rate.
        """
        self.log.debug("Finding the price minimum...")
        api_result = self._fetch_upcoming_prices_from_api()
        all_energy_rates = self._extract_energy_rates_from_api_response(api_result)
        upcoming_energy_rates = self._remove_energy_rates_from_the_past(all_energy_rates)
        energy_rates_between_first_and_second_maximum = self._get_energy_rates_between_first_and_second_maximum(
            upcoming_energy_rates, first_iteration
        )
        minimum_of_energy_rates = self.get_global_minimum_of_energy_rates(
            energy_rates_between_first_and_second_maximum
        )

        return minimum_of_energy_rates.timestamp

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
        # Note: Sometimes we only get the prices for today from the tibber api and the prices for tomorrow stay empty
        # I guess they are not determined yet...?
        self.log.debug("Crawling the Tibber API for the electricity prices")
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
                    rate=price["total"],
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
        current_time = datetime.now(tz=all_energy_rates[0].timestamp.tzinfo)
        beginning_of_current_hour = current_time.replace(minute=0, second=0, microsecond=0)

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

        self.log.debug(f"Found {first_maximum_energy_rate} to be the first maximum of the upcoming energy rates")

        energy_rates_between_first_and_second_maximum = self._find_energy_rates_till_first_maximum(
            energy_rates_starting_at_first_maximum
        )
        self.log.debug(
            f"Found {energy_rates_between_first_and_second_maximum[-1]} to be the second maximum of the upcoming energy rates"
        )

        return energy_rates_between_first_and_second_maximum

    def _find_energy_rates_till_first_maximum(
        self, upcoming_energy_rates: list[EnergyRate], first_run: bool = False
    ) -> list[EnergyRate]:
        last_energy_rate = upcoming_energy_rates[0]
        minimum_energy_rate_found_until_now = upcoming_energy_rates[0]
        last_energy_rate_was_maximum = False
        energy_rates_till_maximum = []
        for current_energy_rate in upcoming_energy_rates:
            if current_energy_rate < minimum_energy_rate_found_until_now:
                minimum_energy_rate_found_until_now = current_energy_rate

            if current_energy_rate > last_energy_rate:
                if (
                    first_run
                    or current_energy_rate.rate > minimum_energy_rate_found_until_now.rate + self.maximum_threshold
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
