from datetime import datetime, time, timedelta

import requests
from dateutil.tz import tzfile
from energy_amount import EnergyAmount, Power
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
        response = response.json()

        if response["code"] != 0:
            # The API always return a 200 status code, even if something went wrong
            raise RuntimeError(
                f"There was a problem logging in into the SEMSPortal: {response['msg']} (Code: {response['code']})"
            )

        self.api_url = response["api"]
        self.token = response["data"]["token"]
        self.timestamp = response["data"]["timestamp"]
        self.user_id = response["data"]["uid"]

        self.log.debug("Login successful")

    def get_average_energy_consumption_per_day(self) -> EnergyAmount:
        """
        Retrieves energy consumption data, extracts the relevant data, and computes the average power consumption per day.

        Returns:
            EnergyAmount: An object containing the average energy consumption per day.
        """
        self.log.debug("Determining average energy consumption per day")

        self.login()

        api_response = self._retrieve_energy_consumption_data()
        consumption_data = self._extract_energy_usage_data_of_response(api_response)
        average_consumption_per_day = sum([consumption.watt_hours for consumption in consumption_data]) / len(
            consumption_data
        )
        return EnergyAmount(watt_hours=average_consumption_per_day)

    def _retrieve_energy_consumption_data(self) -> dict:
        """
        Retrieves energy consumption data from the SEMSPORTAL API.

        This method sends a POST request to the SEMSPORTAL API to fetch the energy consumption data of a specified plant station.
        It constructs the necessary headers and payload required by the API and handles the response appropriately.

        Returns:
            dict: A dictionary containing the energy consumption data retrieved from the SEMSPORTAL API.
        """
        self.log.debug("Crawling the SEMSPORTAL API for energy consumption data...")

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
        response = response.json()

        self.log.trace(f"Retrieved data: {response}")

        return response

    def _extract_energy_usage_data_of_response(self, response_json: dict) -> list[EnergyAmount]:
        """
        Args:
            response_json: JSON response from the SEMSPORTAL API containing detailed energy usage data.

        Returns:
            A list of EnergyAmount objects representing energy usage for the last week.
        """
        lines = response_json["data"]["lines"]

        # This is a list of dicts, each dict looks as follows
        # {"x": "<date in YYYY-MM-DD>", "y": <energy usage in kWh>, "z": None}
        consumption_data_raw = [line for line in lines if "Consumption" in line["label"]][0]["xy"]

        # Sort the list of dicts by date
        consumption_data_raw_sorted = sorted(consumption_data_raw, key=lambda d: d["x"])

        # Create a list with the values of the last week
        # Since we run some at any point during the day, we want to exclude the current day
        last_weeks_energy_usage = [
            EnergyAmount.from_kilo_watt_hours(data_point["y"]) for data_point in consumption_data_raw_sorted[-9:-2]
        ]

        self.log.debug(f"Extracted last weeks energy usage: {last_weeks_energy_usage}")

        return last_weeks_energy_usage

    def get_energy_buy_of_today(self) -> EnergyAmount:
        """
        Crawls the SEMSPORTAL API for the amount of energy bought today until this point in time.

        Returns:
            EnergyAmount: The amount of energy bought today.
        """
        self.log.debug("Determining the amount of energy bought today")

        self.login()

        api_response = self._retrieve_energy_consumption_data()
        lines = api_response["data"]["lines"]
        buy_line = [line for line in lines if "buy" in line["label"].lower()][0]

        return EnergyAmount.from_kilo_watt_hours(buy_line["xy"][-1]["y"])

    def get_energy_usage_in_timeframe(self, timestamp_start: datetime, timestamp_end: datetime) -> EnergyAmount:
        """
        This method estimates the energy usage between the provided start and end timestamps by considering
        different energy consumption rates during the day and night. The day is defined as starting at 6:00 AM
        and ending at 6:00 PM, while the night includes the remaining hours.

        It follows these steps:
        1. Retrieve the energy usage factors for day and night from environment variables.
        2. Calculate the total durations of day and night within the given timeframe.
        3. Get the average daily energy consumption.
        4. Calculate the average power consumption (in Watts) for the day.
        5. Compute energy usage during the day and night separately by multiplying the average power consumption with
            the duration of the respective time frame.
        6. Return the total estimated energy usage by summing the day and night values.

        Similar to SunForecastHandler.get_solar_output_in_timeframe().

        Args:
            timestamp_start: The start time of the period for which energy consumption is to be calculated.
            timestamp_end: The end time of the period for which energy consumption is to be calculated.

        Returns:
            EnergyAmount: The estimated total energy usage within the given timeframe.
        """
        day_start = time(6, 0)
        night_start = time(18, 0)
        factor_energy_usage_during_the_day = float(EnvironmentVariableGetter.get("POWER_USAGE_FACTOR", 0.6))
        factor_energy_usage_during_the_night = 1 - factor_energy_usage_during_the_day

        if not 0 <= factor_energy_usage_during_the_day <= 1:
            raise ValueError(
                f'The "POWER_USAGE_FACTOR" has to be between 0 and 1 (actual: {factor_energy_usage_during_the_day})!'
            )

        self.log.debug(f"Getting estimated energy usage between {timestamp_start} and {timestamp_end}")

        day_duration, night_duration = self.calculate_day_night_duration(
            timestamp_start, timestamp_end, day_start, night_start
        )

        energy_usage_of_today = self.get_average_energy_consumption_per_day()
        self.log.debug(f"Expected energy usage of the day is {energy_usage_of_today}")

        average_power_consumption = Power(watts=energy_usage_of_today.watt_seconds / (60 * 60 * 24))
        self.log.debug(f"Average power consumption today is {average_power_consumption}")

        energy_usage_during_the_day = EnergyAmount.from_watt_seconds(
            average_power_consumption.watts * day_duration.total_seconds() * 2 * factor_energy_usage_during_the_day
        )
        energy_usage_during_the_night = EnergyAmount.from_watt_seconds(
            average_power_consumption.watts * night_duration.total_seconds() * 2 * factor_energy_usage_during_the_night
        )
        self.log.info(
            f"Energy usage during daytime is expected to be {energy_usage_during_the_day}, energy usage during nighttime is expected to be {energy_usage_during_the_night}"
        )

        return energy_usage_during_the_day + energy_usage_during_the_night

    def calculate_day_night_duration(
        self,
        timestamp_start: datetime,
        timestamp_end: datetime,
        day_start: time,
        night_start: time,
    ) -> tuple[timedelta, timedelta]:
        """
        Calculates the total duration of daytime and nighttime within a given timeframe.

        This method divides the timeframe between `timestamp_start` and `timestamp_end` into daytime and nighttime
        based on the provided day and night start times.

        Example:
            timestamp_start=04:00 AM
            timestamp_end=10:00 PM
            day_start=06:00 AM
            night_start=06:00 PM

            duration of daytime = 12 hours
            duration of nighttime = 2 hours + 4 hours = 6 hours

        Args:
            timestamp_start: The starting timestamp of the timeframe to be analyzed.
            timestamp_end: The ending timestamp of the timeframe to be analyzed.
            day_start: The time of day when daytime begins.
            night_start: The time of day when nighttime begins.

        Returns:
            A tuple containing the total duration of daytime and the total duration of nighttime.
        """
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
