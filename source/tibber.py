from environment_variable_getter import EnvironmentVariableGetter
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from logger import LoggerMixin


class TibberAPI(LoggerMixin):
    def __init__(self):
        super().__init__()

        api_token = EnvironmentVariableGetter.get("TIBBER_API_TOKEN")

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
                                consumptionUnit
                            }
                        }
                    }
                }
            }
        """
        )

        self.log.debug(
            "Calling the Tibber API to get the power consumption of last week"
        )
        result = self.client.execute(query)

        consumption_data = result["viewer"]["homes"][0]["consumption"]["nodes"][0]
        if consumption_data["consumptionUnit"] == "kWh":
            consumption_in_watt_hours = consumption_data["consumption"] * 1000
        elif consumption_data["consumptionUnit"] == "Wh":
            consumption_in_watt_hours = consumption_data["consumption"]
        else:
            raise ValueError(
                f'Unexpected unit of consumption from Tibber: {consumption_data["consumptionUnit"]}'
            )

        consumption_in_watt_hours = int(consumption_in_watt_hours)
        self.log.info(
            f"The power consumption of the last week is {consumption_in_watt_hours} Wh"
        )
        return consumption_in_watt_hours

    def get_average_consumption_of_day_in_watt_hours(self) -> float:
        self.log.debug("Getting the average power consumption per day")
        average_power_consumption_per_day = (
            self.get_consumption_of_last_week_in_watt_hours() / 7
        )
        self.log.info(
            f"The average power consumption per day is {average_power_consumption_per_day:.1f} Wh"
        )
        return average_power_consumption_per_day

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
