from datetime import datetime

from energy_amount import ConsecutiveEnergyRates, EnergyRate
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

    def get_timestamp_of_next_price_maximum(self) -> datetime:
        """
        Fetches the upcoming energy rates, filters out past rates, and returns the timestamp of the first maximum rate.

        Returns:
            datetime: The timestamp of the first maximum energy rate among the upcoming rates.
        """
        self.log.debug("Finding the next price maximum...")
        api_result = self._fetch_upcoming_prices_from_api()
        all_energy_rates = self._extract_energy_rates_from_api_response(api_result)
        upcoming_energy_rates = self._remove_energy_rates_from_the_past(all_energy_rates)
        maximum_of_energy_rates = self._get_energy_rates_till_first_maximum(upcoming_energy_rates)[-1]

        return maximum_of_energy_rates.timestamp

    def get_timestamp_of_next_price_minimum(self) -> datetime:
        """
        Find the next optimal charging time based on upcoming energy prices.

        This method performs a series of operations to determine the most cost-effective
        time to charge by analyzing upcoming energy rates retrieved from the Tibber API.

        Looking at the prices trends, it can be seen that the optimal time to charge is the minimum between now and the
            next maximum.

        Steps:
        1. Fetches the upcoming energy prices from the API asynchronously.
        2. Extracts energy rates from the API response.
        3. Filters out energy rates that are in the past.
        4. Gets energy rates up until the first maximum rate.
        5. Finds the minimum of the filtered energy rates.

        Returns:
            datetime: The timestamp of the next optimal charging time.
        """
        self.log.debug("Finding the price minimum...")
        api_result = self._fetch_upcoming_prices_from_api()
        all_energy_rates = self._extract_energy_rates_from_api_response(api_result)
        upcoming_energy_rates = self._remove_energy_rates_from_the_past(all_energy_rates)
        upcoming_energy_rates_till_maximum = self._get_energy_rates_till_first_maximum(upcoming_energy_rates)
        minimum_of_energy_rates = self.get_global_minimum_of_energy_rates(upcoming_energy_rates_till_maximum)

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
        self.log.debug("Crawling the Tibber API for the electricity prices")
        response = self.client.execute(query)
        self.log.trace(f"Retrieved data: {response}")
        return response

    def _extract_energy_rates_from_api_response(self, api_result: dict) -> ConsecutiveEnergyRates:
        """
        Extracts the raw energy rate information from the provided API response.

        Args:
            api_result: The API response containing energy rate information.

        Returns:
            ConsecutiveEnergyRates: A list of energy rates with associated timestamps.
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

        upcoming_energy_rates = ConsecutiveEnergyRates(upcoming_energy_rates)

        self.log.trace(f"Extracted the the energy rates from the API response {upcoming_energy_rates}")
        return upcoming_energy_rates

    def _remove_energy_rates_from_the_past(self, all_energy_rates: ConsecutiveEnergyRates) -> ConsecutiveEnergyRates:
        """
        Args:
            all_energy_rates: A ConsecutiveEnergyRates object.

        Returns:
            ConsecutiveEnergyRates: A new ConsecutiveEnergyRates object containing only the energy rates that are
                later than the beginning of the current hour.
        """
        current_time = datetime.now(tz=all_energy_rates[0].timestamp.tzinfo)
        beginning_of_current_hour = current_time.replace(minute=0, second=0, microsecond=0)

        upcoming_energy_rates = [
            energy_rate for energy_rate in all_energy_rates if energy_rate.timestamp > beginning_of_current_hour
        ]
        upcoming_energy_rates = ConsecutiveEnergyRates(upcoming_energy_rates)
        self.log.trace(f"Removed the energy rates from the past. Upcoming energy rates are {upcoming_energy_rates}")
        return upcoming_energy_rates

    def _get_energy_rates_till_first_maximum(
        self, upcoming_energy_rates: ConsecutiveEnergyRates
    ) -> ConsecutiveEnergyRates:
        """
        Extracts energy rates up until the first maximum is reached from a sequence of upcoming energy rates.
        It iterates through the provided energy rates, appending each rate to a list until a rate lower than the last
        maximum rate is found, indicating the first peak is reached.

        Args:
            upcoming_energy_rates: A sequence of consecutive energy rates to be analyzed.

        Returns:
            A sequence of energy rates up to the first encountered maximum rate.
        """
        last_energy_rate = upcoming_energy_rates[0]
        last_energy_rate_was_maximum = False
        energy_rates_till_maximum = []
        for current_energy_rate in upcoming_energy_rates:
            if current_energy_rate.rate > last_energy_rate.rate:
                last_energy_rate_was_maximum = True

            if current_energy_rate.rate < last_energy_rate.rate and last_energy_rate_was_maximum:
                break

            energy_rates_till_maximum.append(current_energy_rate)
            last_energy_rate = current_energy_rate

        energy_rates_till_maximum = ConsecutiveEnergyRates(energy_rates_till_maximum)

        self.log.debug(
            f"Found {last_energy_rate} to be the first maximum of the upcoming energy rates ({upcoming_energy_rates})"
        )
        return energy_rates_till_maximum

    def get_global_minimum_of_energy_rates(self, energy_rates_till_maximum: ConsecutiveEnergyRates) -> EnergyRate:
        """
        Args:
            energy_rates_till_maximum: A collection of ConsecutiveEnergyRates representing energy rates until the first maximum.

        Returns:
            EnergyRate: The global minimum energy rate from the provided collection.
        """
        global_minimum_of_energy_rates = min(energy_rates_till_maximum, key=lambda energy_rate: energy_rate.rate)
        self.log.debug(
            f"Found {global_minimum_of_energy_rates} to be the global minimum of the energy rates till the first maximum ({energy_rates_till_maximum})"
        )
        return global_minimum_of_energy_rates
