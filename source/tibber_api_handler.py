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
