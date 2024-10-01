from datetime import datetime

from aiographql.client import GraphQLClient, GraphQLRequest
from environment_variable_getter import EnvironmentVariableGetter
from logger import LoggerMixin

from source.price_slice import PriceSlice


class TibberAPIHandler(LoggerMixin):
    def __init__(self):
        super().__init__()

        self.client = GraphQLClient(
            endpoint="https://api.tibber.com/v1-beta/gql",
            headers={
                "Authorization": (EnvironmentVariableGetter.get("TIBBER_API_TOKEN"))
            },
        )

    async def get_prices_of_tomorrow(self) -> list[PriceSlice]:
        """
        Fetches electricity prices for today from the Tibber API.

        :return: A list of PriceSlice objects containing the prices and their corresponding start times for tomorrow.
        """
        query = GraphQLRequest(
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
                            }
                        }
                    }
                }
            }
        """
        )
        self.log.debug("Crawling the Tibber API for the electricity prices")
        result = await self.client.query(query)
        prices_of_tomorrow_raw = result.data["viewer"]["homes"][0][
            "currentSubscription"
        ]["priceInfo"]["today"]

        prices_of_tomorrow_parsed = []
        for price in prices_of_tomorrow_raw:
            prices_of_tomorrow_parsed.append(
                PriceSlice(
                    rate=price["total"],
                    timestamp=datetime.fromisoformat(price["startsAt"]),
                )
            )

        self.log.debug(f"Retrieved prices of today: {prices_of_tomorrow_parsed}")
        return prices_of_tomorrow_parsed
