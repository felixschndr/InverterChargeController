from environment_variable_getter import EnvironmentVariableGetter
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from logger import LoggerMixin


class TibberAPIHandler(LoggerMixin):
    def __init__(self):
        super().__init__()

        transport = AIOHTTPTransport(
            url="https://api.tibber.com/v1-beta/gql",
            headers={
                "Authorization": (EnvironmentVariableGetter.get("TIBBER_API_TOKEN"))
            },
        )
        self.client = Client(transport=transport, fetch_schema_from_transport=True)

    def get_prices_of_tomorrow(self) -> list[dict]:
        query = gql(
            """
            {
            viewer {
                homes {
                    currentSubscription {
                        priceInfo {
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
        result = self.client.execute(query)
        prices_of_tomorrow = result["viewer"]["homes"][0]["currentSubscription"][
            "priceInfo"
        ]["tomorrow"]
        self.log.debug(f"Retrieved prices of tomorrow: {prices_of_tomorrow}")
        return prices_of_tomorrow

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

    def find_start_time_to_charge(self, charging_duration: int) -> str:
        """
        :param charging_duration: The number of hours for which charging is required.
        :return: The starting timestamp to begin charging, based on the cheapest price slice of electricity for the next day
            in the format YYYY-MM-DDTHH:MM:SS+HH:MM
        """
        prices_of_tomorrow = self.get_prices_of_tomorrow()
        price_slices = self._calculate_price_slices(
            prices_of_tomorrow=prices_of_tomorrow, slice_size=charging_duration
        )
        cheapest_slice = self._determine_cheapest_price_slice(price_slices)

        return cheapest_slice[0]["startsAt"]


if __name__ == "__main__":
    tibber_api_handler = TibberAPIHandler()
    print(tibber_api_handler.find_start_time_to_charge(4))
