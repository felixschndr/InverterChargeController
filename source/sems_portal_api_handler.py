from datetime import datetime, timedelta

import requests
from environment_variable_getter import EnvironmentVariableGetter
from logger import LoggerMixin


class SemsPortalApiHandler(LoggerMixin):
    def __init__(self):
        super().__init__()

        self.api_url = None
        self.token = None
        self.timestamp = None
        self.user_id = None

    def login(self) -> None:
        """
        Authenticates a user by sending a POST request to the SEMS Portal API and retrieves
        necessary tokens and API URL for subsequent requests. The user's credentials are
        fetched from the environment variables.
        This has to be done every time a request is made to the API since the authentication tokens expire after a few
        seconds.

        :return: None
        """
        self.log.debug("Logging in into the SEMSPORTAL...")
        url = "https://www.semsportal.com/api/v1/Common/CrossLogin"
        headers = {
            "Content-Type": "application/json",
            "Token": '{"version":"v2.1.0","client":"ios","language":"en"}',
        }
        payload = {
            "account": EnvironmentVariableGetter.get("SEMSPORTAL_USERNAME"),
            "pwd": EnvironmentVariableGetter.get("SEMSPORTAL_PASSWORD"),
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()

        self.api_url = response.json()["api"]
        self.token = response.json()["data"]["token"]
        self.timestamp = response.json()["data"]["timestamp"]
        self.user_id = response.json()["data"]["uid"]

        self.log.debug("Login successful")

    def get_average_power_consumption_per_day(self) -> int:
        """
        Retrieves power consumption data, extracts the relevant data, and computes the average power consumption per day.

        :return: The average power consumption in Wh per day.
        """
        self.log.info("Determining average power consumption per day")

        self.login()

        api_response = self._retrieve_power_consumption_data()
        consumption_data = self._extract_consumption_data_of_response(api_response)
        average_consumption_per_day_in_kwh = sum(consumption_data) / len(
            consumption_data
        )
        return int(average_consumption_per_day_in_kwh * 1000)

    def _retrieve_power_consumption_data(self) -> dict:
        """
        Retrieves power consumption data from the SEMSPORTAL API.

        This method sends a POST request to the SEMSPORTAL API to fetch the power consumption data of a specified plant station.
        It constructs the necessary headers and payload required by the API and handles the response appropriately.

        Returns:
            dict: A dictionary containing the power consumption data retrieved from the SEMSPORTAL API.
        """
        self.log.debug("Crawling the SEMSPORTAL API for power consumption data...")

        url = "https://eu.semsportal.com/api/v2/Charts/GetChartByPlant"
        headers = {
            "Content-Type": "application/json",
            "Token": f'{{"version":"v2.1.0","client":"ios","language":"en", "timestamp": "{self.timestamp}", "uid": "{self.user_id}", "token": "{self.token}"}}',
        }
        payload = {
            "id": EnvironmentVariableGetter.get("SEMSPORTAL_POWERSTATION_ID"),
            "range": 2,
            "chartIndexId": "8",
            "date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
        }

        response = requests.post(url, headers=headers, json=payload, timeout=20)
        response.raise_for_status()

        self.log.debug(f"Retrieved data: {response.json()}")

        return response.json()

    def _extract_consumption_data_of_response(self, response_json: dict) -> list[float]:
        """
        :param response_json: Dictionary containing the JSON response with power consumption data.
        :return: List of the most recent 7 daily power consumption values in kWh.
        """
        lines = response_json["data"]["lines"]

        # This is a list of dicts, each dict looks as follows
        # {"x": "<date in YYYY-MM-DD>", "y": <power consumption in kWh>, "z": None}
        consumption_data_raw = [
            line for line in lines if "Consumption" in line["label"]
        ][0]["xy"]

        # Sort the list of dicts by date
        consumption_data_raw_sorted = sorted(consumption_data_raw, key=lambda d: d["x"])

        # Create a list with the values of the last week
        # Since we run some minutes after midnight we want to exclude the current day
        last_week_consumption_data = [
            data_point["y"] for data_point in consumption_data_raw_sorted[-8:-1]
        ]

        self.log.debug(
            f"Extracted last weeks consumption data (in kWh): {last_week_consumption_data}"
        )

        return last_week_consumption_data

    def get_state_of_charge(self) -> int:
        """
        Fetches the current state of charge from the SEMSPORTAL API.

        Returns:
            int: The current state of charge as an integer percentage.
        """
        self.log.debug("Crawling the SEMSPORTAL API for current state of charge...")

        self.login()

        url = "https://eu.semsportal.com/api/v3/PowerStation/GetPlantDetailByPowerstationId"
        headers = {
            "Content-Type": "application/json",
            "Token": f'{{"version":"v2.1.0","client":"ios","language":"en", "timestamp": "{self.timestamp}", "uid": "{self.user_id}", "token": "{self.token}"}}',
        }
        payload = {
            "powerStationId": EnvironmentVariableGetter.get(
                "SEMSPORTAL_POWERSTATION_ID"
            ),
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()

        self.log.debug(f"Retrieved data: {response.json()}")

        state_of_charge = int(response.json()["data"]["soc"][0]["power"])

        return state_of_charge
