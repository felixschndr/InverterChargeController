import json

from requests.exceptions import HTTPError
from datetime import datetime, timedelta

import requests

from source.environment_variable_getter import EnvironmentVariableGetter


class SemsPortalApiHandler:
    def __init__(self):
        self.api_url = None
        self.token = None
        self.timestamp = None
        self.user_id = None

    def login(self) -> None:
        """
        Sets the SEMS token and API URL by making a POST request to the SEMS portal cross-login API.

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

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        self.api_url = response.json()["api"]
        self.token = response.json()["data"]["token"]
        self.timestamp = response.json()["data"]["timestamp"]
        self.user_id = response.json()["data"]["uid"]

    def get_average_power_consumption_per_day_of_last_week(self) -> float:
        """
        Retrieves the average power consumption per day in kWh of the last week from the sems API.

        :return: The average power consumption per day of the last week as a float.
        """
        url = "https://eu.semsportal.com/api/v2/Charts/GetChartByPlant"
        headers = {
            "Content-Type": "application/json",
            "Token": f'{{"version":"v2.1.0","client":"ios","language":"en", "timestamp": "{self.timestamp}", "uid": "{self.user_id}", "token": "{self.token}"}}',
        }
        payload = json.dumps({
            "id": EnvironmentVariableGetter.get("SEMSPORTAL_POWERSTATION_ID"),
            "range": 2,
            "chartIndexId": "8",
            "date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
        })
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()

        if "100001" in response.text or "100002" in response.text:
            raise HTTPError("HTTP Unauthorized: The provided token is invalid or expired.")

        return self._extract_consumption_data_of_response(response.json())

    @staticmethod
    def _extract_consumption_data_of_response(response_json: dict) -> float:
        """
        :param response_json: A dictionary representing the JSON response received.
        :return: The average consumption data of the last week.

        This method extracts the consumption data from the given JSON response and calculates the average consumption per day of the last week in kWh.
        """
        lines = response_json["data"]["lines"]
        consumption_data_raw = [line for line in lines if "Verbrauch" in line["label"]][
            0
        ]["xy"]

        consumption_data_raw_sorted = sorted(consumption_data_raw, key=lambda d: d["x"])

        last_week_consumption_data = [
            data_point["y"] for data_point in consumption_data_raw_sorted[-7:]
        ]

        return sum(last_week_consumption_data) / len(last_week_consumption_data)

sems_portal_api_handler = SemsPortalApiHandler()
sems_portal_api_handler.login()
print(sems_portal_api_handler.get_average_power_consumption_per_day_of_last_week())
