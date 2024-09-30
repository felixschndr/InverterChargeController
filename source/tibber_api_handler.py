from environment_variable_getter import EnvironmentVariableGetter
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from logger import LoggerMixin


class TibberAPIHandler(LoggerMixin):
    def __init__(self):
        super().__init__()

        api_token = EnvironmentVariableGetter.get("TIBBER_API_TOKEN")

        transport = AIOHTTPTransport(
            url="https://api.tibber.com/v1-beta/gql",
            headers={"Authorization": api_token},
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
        return result["viewer"]["homes"][0]["currentSubscription"]["priceInfo"][
            "tomorrow"
        ]

    @staticmethod
    def get_slices(prices_of_tomorrow: list[dict], hours: int) -> list[list[dict]]:
        slices = []
        for i in range(len(prices_of_tomorrow) - hours + 1):
            slices.append(prices_of_tomorrow[i:i + hours])

        return slices

if __name__ == "__main__":
    tibber_api_handler = TibberAPIHandler()
    prices = tibber_api_handler.get_prices_of_tomorrow()
    # print(prices)
    tibber_api_handler.get_slices(prices, 2)
