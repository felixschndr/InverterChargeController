from datetime import datetime, time, timedelta

import requests
from dateutil.tz import tzfile
from environment_variable_getter import EnvironmentVariableGetter
from logger import LoggerMixin


class SemsPortalApiHandler(LoggerMixin):
    def __init__(self, timezone: tzfile):
        super().__init__()

        self.api_url = None
        self.token = None
        self.timestamp = None
        self.user_id = None

        self.timezone = timezone

    def login(self) -> None:
        """
        Authenticates a user by sending a POST request to the SEMS Portal API and retrieves
        the necessary tokens and API URL for subsequent requests. The user's credentials are fetched from the
        environment variables.
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
        self.log.debug("Determining average power consumption per day")

        self.login()

        api_response = self._retrieve_power_consumption_data()
        consumption_data = self._extract_consumption_data_of_response(api_response)
        average_consumption_per_day_in_kwh = sum(consumption_data) / len(consumption_data)
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
            "date": datetime.now().strftime("%Y-%m-%d"),
        }

        response = requests.post(url, headers=headers, json=payload, timeout=20)
        response.raise_for_status()

        self.log.trace(f"Retrieved data: {response.json()}")

        return response.json()

    def _extract_consumption_data_of_response(self, response_json: dict) -> list[float]:
        """
        :param response_json: Dictionary containing the JSON response with power consumption data.
        :return: List of the most recent seven daily power consumption values in kWh.
        """
        lines = response_json["data"]["lines"]

        # This is a list of dicts, each dict looks as follows
        # {"x": "<date in YYYY-MM-DD>", "y": <power consumption in kWh>, "z": None}
        consumption_data_raw = [line for line in lines if "Consumption" in line["label"]][0]["xy"]

        # Sort the list of dicts by date
        consumption_data_raw_sorted = sorted(consumption_data_raw, key=lambda d: d["x"])

        # Create a list with the values of the last week
        # Since we run some minutes after midnight, we want to exclude the current day
        last_week_consumption_data = [data_point["y"] for data_point in consumption_data_raw_sorted[-9:-2]]

        self.log.debug(f"Extracted last weeks consumption data (in kWh): {last_week_consumption_data}")

        return last_week_consumption_data

    def get_power_buy_of_today(self) -> int:
        """
        Retrieves the amount of power bought today.

        :return: The amount of power bought today in Wh.
        """
        self.log.info("Determining amount of power bought today")

        self.login()

        api_response = self._retrieve_power_consumption_data()
        lines = api_response["data"]["lines"]
        buy_line = [line for line in lines if "buy" in line["label"].lower()][0]
        power_buy_of_today_in_kwh = buy_line["xy"][-1]["y"]

        return int(power_buy_of_today_in_kwh * 1000)

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
            "powerStationId": EnvironmentVariableGetter.get("SEMSPORTAL_POWERSTATION_ID"),
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()

        self.log.trace(f"Retrieved data: {response.json()}")

        state_of_charge = int(response.json()["data"]["soc"][0]["power"])

        return state_of_charge

    def get_power_usage_in_timeframe_in_watt_hours(self, timestamp_start: datetime, timestamp_end: datetime) -> int:
        day_start = time(6, 0)
        night_start = time(18, 0)
        # 60 % power usage during the day, 40 % power usage during the night
        factor_power_usage_during_the_day = 0.6
        factor_power_usage_during_the_night = 1 - factor_power_usage_during_the_day

        self.log.debug(f"Getting estimated power usage between {timestamp_start} and {timestamp_end}")

        day_duration, night_duration = self.calculate_day_night_duration(
            timestamp_start, timestamp_end, day_start, night_start
        )

        power_usage_of_today_in_watt_hours = self.get_average_power_consumption_per_day()
        self.log.debug(f"Expected power usage of the day is {power_usage_of_today_in_watt_hours} Wh")
        power_usage_of_today_in_watt_seconds = power_usage_of_today_in_watt_hours * 60 * 60

        average_power_usage_in_watts = power_usage_of_today_in_watt_seconds / (60 * 60 * 24)
        self.log.debug(f"Average power consumption today is {average_power_usage_in_watts} W")

        power_usage_during_the_day_in_watt_seconds = (
            average_power_usage_in_watts * day_duration.total_seconds() * 2 * factor_power_usage_during_the_day
        )
        power_usage_during_the_night_in_watt_seconds = (
            average_power_usage_in_watts * night_duration.total_seconds() * 2 * factor_power_usage_during_the_night
        )
        power_usage_during_the_day_in_watt_hours = int(power_usage_during_the_day_in_watt_seconds / (60 * 60))
        power_usage_during_the_night_in_watt_hours = int(power_usage_during_the_night_in_watt_seconds / (60 * 60))
        self.log.info(
            f"Power usage during daytime is {power_usage_during_the_day_in_watt_hours} Wh, power usage during nightime is {power_usage_during_the_night_in_watt_hours} Wh"
        )

        return power_usage_during_the_day_in_watt_hours + power_usage_during_the_night_in_watt_hours

    def calculate_day_night_duration(
        self,
        timestamp_start: datetime,
        timestamp_end: datetime,
        day_start: time,
        night_start: time,
    ) -> tuple[timedelta, timedelta]:
        duration_day = timedelta(seconds=0)
        duration_night = timedelta(seconds=0)

        current_time = timestamp_start

        while current_time < timestamp_end:
            self.log.trace(f"current_time is {current_time}")
            # Calculate day and night start timestamp depending on the current time
            day_start_time = datetime.combine(current_time.date(), day_start, tzinfo=self.timezone)
            night_start_time = datetime.combine(current_time.date(), night_start, tzinfo=self.timezone)
            next_day_start_time = day_start_time + timedelta(days=1)

            if current_time < day_start_time or current_time >= night_start_time:
                # Duration of the night
                if current_time < day_start_time:
                    night_end = min(day_start_time, timestamp_end)
                else:
                    night_end = min(next_day_start_time, timestamp_end)
                slot_duration = night_end - current_time
                duration_night += slot_duration
                self.log.trace(f"Adding {slot_duration} to the night duration (now: {duration_night}")
                current_time = night_end

            else:
                # Duration of the day
                day_end = min(night_start_time, timestamp_end)
                slot_duration = day_end - current_time
                duration_day += slot_duration
                self.log.trace(f"Adding {slot_duration} to the day duration (now: {duration_day}")
                current_time = day_end

        self.log.debug(
            f"The time between the given timeframe is split across {duration_day} of daytime and {duration_night} of nighttime"
        )

        return duration_day, duration_night


if __name__ == "__main__":

    start = datetime(2024, 10, 22, 19, 0)  # Startzeitpunkt
    end = datetime(2024, 10, 23, 20, 0)  # Endzeitpunkt

    sems_portal_api_handler = SemsPortalApiHandler()
    sems_portal_api_handler.get_power_usage_in_timeframe_in_watt_hours(start, end)
