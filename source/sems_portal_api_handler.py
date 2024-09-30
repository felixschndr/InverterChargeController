from datetime import datetime, timedelta

import requests
from requests.exceptions import HTTPError

from source.environment_variable_getter import EnvironmentVariableGetter


class SemsPortalApiHandler:
    def __init__(self):
        self.api_url = None
        self.token = None
        self.timestamp = None
        self.user_id = None

    def login(self) -> None:
        """
        Authenticates a user by sending a POST request to the SEMS Portal API and retrieves
        necessary tokens and API URL for subsequent requests. The user's credentials are
        fetched from the environment variables.

        :return: None
        """
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

    def get_average_power_consumption_per_day(self) -> float:
        """
        Retrieves power consumption data, extracts the relevant data, and computes the average power consumption per day.

        :return: The average power consumption in Wh per day as a float.
        """
        api_response = self._retrieve_power_consumption_data()
        consumption_data = self._extract_consumption_data_of_response(api_response)
        average_consumption_per_day_in_kwh = sum(consumption_data) / len(
            consumption_data
        )
        return average_consumption_per_day_in_kwh * 1000

    def _retrieve_power_consumption_data(self) -> dict:
        """
        :return: A dictionary containing the power consumption data in kWh retrieved from the SEMSPORTAL API.
        :raises HTTPError: If the provided token is invalid or expired.
        """
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

        if "100001" in response.text or "100002" in response.text:
            raise HTTPError(
                "HTTP Unauthorized: The provided token is invalid or expired."
            )

        return response.json()

    @staticmethod
    def _extract_consumption_data_of_response(response_json: dict) -> list[float]:
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

        # Create a list with the most recent 7 values
        last_week_consumption_data = [
            data_point["y"] for data_point in consumption_data_raw_sorted[-7:]
        ]

        return last_week_consumption_data
