import os

from dotenv import load_dotenv
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

load_dotenv()


class TibberAPI:
    def __init__(self):
        api_token_variable_name = "TIBBER_API_TOKEN"
        try:
            api_token = os.environ[api_token_variable_name]
        except KeyError:
            raise RuntimeError(
                f"Environment variable {api_token_variable_name} is not set!"
            )

        transport = AIOHTTPTransport(
            url="https://api.tibber.com/v1-beta/gql",
            headers={"Authorization": api_token},
        )
        self.client = Client(transport=transport, fetch_schema_from_transport=True)

    def get_consumption_of_last_week_in_watt_hours(self) -> int:
        query = gql(
            """
            {
                viewer {
                    homes {
                        consumption (resolution: WEEKLY, last: 1) {
                            nodes {
                                consumption
                            }
                        }
                    }
                }
            }
        """
        )

        result = self.client.execute(query)
        consumption_in_kilo_watt_hours = result["viewer"]["homes"][0]["consumption"][
            "nodes"
        ][0]["consumption"]
        return int(consumption_in_kilo_watt_hours * 1000)

    def get_average_consumption_of_day_in_last_week_in_watt_hours(self) -> float:
        return self.get_consumption_of_last_week_in_watt_hours() / 7

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
