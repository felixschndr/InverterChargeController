from datetime import date, datetime, time, timedelta

import requests
from database_handler import DatabaseHandler, InfluxDBField
from energy_classes import EnergyAmount, Power
from environment_variable_getter import EnvironmentVariableGetter
from logger import LoggerMixin
from time_handler import TimeHandler


class SemsPortalApiHandler(LoggerMixin):
    def __init__(self):
        super().__init__()

        self.api_url = None
        self.token = None
        self.timestamp = None
        self.user_id = None

        self.database_handler = DatabaseHandler("power")

    def login(self) -> None:
        """
        Authenticates a user by sending a POST request to the SEMS Portal API and retrieves
        the necessary tokens and API URL for subsequent requests. The user's credentials are fetched from the
        environment variables.
        This has to be done every time a request is made to the API since the authentication tokens expire after a few
        seconds.

        :return: None
        """
        self.log.trace("Logging in into the SEMSPORTAL...")
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
            # The API always returns a 200 status code, even if something went wrong
            raise RuntimeError(
                f"There was a problem logging in into the SEMSPortal: {response['msg']} (Code: {response['code']})"
            )

        self.api_url = response["api"]
        self.token = response["data"]["token"]
        self.timestamp = response["data"]["timestamp"]
        self.user_id = response["data"]["uid"]

        self.log.trace("Login successful")

    def get_average_energy_consumption_per_day(self) -> EnergyAmount:
        """
        Retrieves energy consumption data, extracts the relevant data, and computes the average power consumption per day.

        Returns:
            EnergyAmount: An object containing the average energy consumption per day.
        """
        self.log.debug("Determining average energy consumption per day")

        api_response = self._retrieve_energy_consumption_data()
        consumption_data = self._extract_energy_usage_data_of_response(api_response)
        average_consumption_per_day = sum([consumption.watt_hours for consumption in consumption_data]) / len(
            consumption_data
        )
        return EnergyAmount(watt_hours=average_consumption_per_day)

    def _retrieve_power_data(self, date_to_crawl: date) -> dict:
        """
        Retrieves the power data from the SEMSPORTAL API. This includes:
         - solar generation
         - battery charge/discharge
         - grid consumption/feed
         - power usage
         - state of charge

        This method sends a POST request to the SEMSPORTAL API to fetch the energy consumption data of a specified plant station.
        It constructs the necessary headers and payload required by the API and handles the response appropriately.

        Returns:
            dict: A dictionary containing the power data retrieved from the SEMSPORTAL API.
        """
        self.login()

        self.log.debug(f"Crawling the SEMSPORTAL API for power data of {date_to_crawl}...")

        url = "https://eu.semsportal.com/api/v2/Charts/GetPlantPowerChart"
        headers = {
            "Content-Type": "application/json",
            "Token": f'{{"version":"v2.1.0","client":"ios","language":"en", "timestamp": "{self.timestamp}", "uid": "{self.user_id}", "token": "{self.token}"}}',
        }
        payload = {
            "id": EnvironmentVariableGetter.get("SEMSPORTAL_POWERSTATION_ID"),
            "date": date_to_crawl.strftime("%Y-%m-%d"),
            "full_script": False,
        }

        response = requests.post(url, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        response = response.json()

        self.log.trace(f"Retrieved data: {response}")

        return response

    def _retrieve_energy_consumption_data(self) -> dict:
        """
        Retrieves energy consumption data from the SEMSPORTAL API.

        This method sends a POST request to the SEMSPORTAL API to fetch the energy consumption data of a specified plant station.
        It constructs the necessary headers and payload required by the API and handles the response appropriately.

        Returns:
            dict: A dictionary containing the energy consumption data retrieved from the SEMSPORTAL API.
        """
        self.login()

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
            "date": TimeHandler.get_date_as_string(),
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

    def get_energy_buy(self, days_in_past: int = 0) -> EnergyAmount:
        """
        Determines the amount of energy bought for a specified day in the past.

        The argument days_in_past specifies how many days to look for in the past. E.g.,
         - days_in_past = 0 --> energy bought today until this point in time
         - days_in_past = 1 --> energy bought yesterday

        Args:
            days_in_past: The number of days in the past to retrieve data for. Default is 0, which means today.

        Returns:
            An instance of EnergyAmount representing the energy bought.
        """
        self.log.debug(f"Determining the amount of energy bought {days_in_past} days ago")

        self.login()

        api_response = self._retrieve_energy_consumption_data()
        lines = api_response["data"]["lines"]
        buy_line = [line for line in lines if "buy" in line["label"].lower()][0]
        if days_in_past != 0:
            self.log.debug(f"Buy line is {buy_line}, days in past: {days_in_past}")

        return EnergyAmount.from_kilo_watt_hours(buy_line["xy"][-1 - days_in_past]["y"])

    def estimate_energy_usage_in_timeframe(self, timestamp_start: datetime, timestamp_end: datetime) -> EnergyAmount:
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

        day_duration, night_duration = TimeHandler.calculate_day_night_duration(
            timestamp_start, timestamp_end, day_start, night_start
        )
        self.log.debug(
            f"The time between the given timeframe is split across {day_duration} of daytime and {night_duration} of nighttime"
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

    def write_values_to_database(self) -> None:
        """
        Writes energy-related metrics to the database for the last three days.

        This method retrieves and processes energy data for the past three days, including solar generation, battery
        discharge, grid feed, power usage and state of charge. It writes the resulting records to the database.
        """
        self.log.debug("Writing values to database...")
        today = date.today()
        for days_in_past in range(3):
            date_to_crawl = today - timedelta(days=days_in_past)
            data = self._retrieve_power_data(date_to_crawl)
            lines = data["data"]["lines"]

            time_keys = [line["x"] for line in lines[0]["xy"]]
            for time_key in time_keys:
                timestamp = datetime.combine(date_to_crawl, datetime.strptime(time_key, "%H:%M").time())
                timestamp = timestamp.replace(tzinfo=TimeHandler.get_timezone())
                self.database_handler.write_to_database(
                    [
                        InfluxDBField(
                            "solar_generation", self._get_value_of_line_by_line_index_and_time_key(lines, 0, time_key)
                        ),
                        InfluxDBField(
                            "battery_charge",
                            self._get_value_of_line_by_line_index_and_time_key(lines, 1, time_key) * -1,
                        ),
                        InfluxDBField(
                            "grid_usage", self._get_value_of_line_by_line_index_and_time_key(lines, 2, time_key) * -1
                        ),
                        InfluxDBField(
                            "power_usage", self._get_value_of_line_by_line_index_and_time_key(lines, 3, time_key)
                        ),
                        InfluxDBField(
                            "state_of_charge", self._get_value_of_line_by_line_index_and_time_key(lines, 4, time_key)
                        ),
                    ],
                    timestamp,
                )

    @staticmethod
    def _get_value_of_line_by_line_index_and_time_key(lines: dict, line_index: int, time_key: str) -> int:
        """
        Retrieves the value associated with a specific time key from a line in a nested dictionary structure.

        This method searches for a specific time key ('x') within the 'xy' list of dictionaries
        contained in a given line at a specified index. It extracts the associated value ('y')
        for the matching time key and converts it to an integer.

        Args:
            lines (dict): A dictionary where each key corresponds to a line index. Each line index
                maps to a dictionary containing a key 'xy', which is a list of dictionaries.
                Each dictionary within 'xy' contains keys 'x' and 'y'.
            line_index (int): The index of the line to search within the 'lines' dictionary.
            time_key (str): The time key to search for, used to identify the specific dictionary in
                the 'xy' list where the 'x' value matches.

        Returns:
            int: The integer representation of the value ('y') corresponding to the provided time key.
        """
        return int([line for line in lines[line_index]["xy"] if line["x"] == time_key][0]["y"])
