from aiographql.client import GraphQLClient, GraphQLRequest
from environment_variable_getter import EnvironmentVariableGetter
from logger import LoggerMixin


class TibberAPIHandler(LoggerMixin):
    def __init__(self):
        super().__init__()

        self.client = GraphQLClient(
            endpoint="https://api.tibber.com/v1-beta/gql",
            headers={
                "Authorization": (EnvironmentVariableGetter.get("TIBBER_API_TOKEN"))
            },
        )

    async def get_prices_of_tomorrow(self) -> list[dict]:
        query = GraphQLRequest(
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
        self.log.debug("Crawling the Tibber API for the electricity prices")
        result = await self.client.query(query)
        prices_of_tomorrow = result.data["viewer"]["homes"][0]["currentSubscription"][
            "priceInfo"
        ]["tomorrow"]
        self.log.debug(f"Retrieved prices of tomorrow: {prices_of_tomorrow}")
        return prices_of_tomorrow
