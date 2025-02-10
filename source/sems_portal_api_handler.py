from datetime import date, datetime, timedelta

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

    def get_average_power_consumption(self) -> Power:
        """
        Calculates the average power consumption from the average of the energy usage data of the last week.

        Returns:
            Power: An instance of the `Power` class, representing the average power consumption at any time.
        """
        self.log.debug("Determining average energy consumption per day")

        api_response = self._retrieve_energy_consumption_data()
        consumption_data = self._extract_energy_usage_data_of_response(api_response)
        average_energy_usage_per_day = EnergyAmount(
            sum([consumption.watt_hours for consumption in consumption_data]) / len(consumption_data)
        )
        return Power(watts=average_energy_usage_per_day.watt_seconds / (60 * 60 * 24))

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
        if days_in_past == 0:
            timeframe_as_string = "today (until now)"
        elif days_in_past == 1:
            timeframe_as_string = "yesterday"
        else:
            timeframe_as_string = f"{days_in_past} days ago"
        self.log.debug(f"Determining the amount of energy bought {timeframe_as_string}")

        api_response = self._retrieve_energy_consumption_data()
        lines = api_response["data"]["lines"]
        buy_line = [line for line in lines if "buy" in line["label"].lower()][0]
        if days_in_past != 0:
            self.log.debug(f"Buy line is {buy_line}, days in past: {days_in_past}")

        return EnergyAmount.from_kilo_watt_hours(buy_line["xy"][-1 - days_in_past]["y"])

    def write_values_to_database(self) -> None:
        """
        Writes power data values to the database.

        This method retrieves power data for the specified number of days starting from the most recently saved
        timestamp in the database. It calculates the required range of days to fetch the data and processes each day's
        data in reverse chronological order. It ensures that only new values, not yet saved in the database, are
        inserted. The method retrieves and processes data fields including solar generation, battery charge, grid usage,
        grid feed, power usage, state of charge, and timestamp, and writes them into the database.
        """
        newest_value_saved_timestamp = self.database_handler.get_newest_value_of_measurement("timestamp")
        if newest_value_saved_timestamp is None:
            return

        self.log.trace(f"Newest value saved in the database is from {newest_value_saved_timestamp}")
        newest_value_saved_date = newest_value_saved_timestamp.date()

        today = date.today()
        days_since_newest_value = (today - newest_value_saved_date).days
        maximum_fetch_days = 31
        if days_since_newest_value > maximum_fetch_days:
            days_since_newest_value = maximum_fetch_days

        days_since_newest_value += 1  # Since range starts at 0 and does not include the end
        self.log.debug(f"Writing values to database for the last {days_since_newest_value} day(s)")

        for days_in_past in range(days_since_newest_value):
            date_to_crawl = today - timedelta(days=days_in_past)
            data = self._retrieve_power_data(date_to_crawl)
            lines = data["data"]["lines"]

            time_keys = [line["x"] for line in lines[0]["xy"]]
            for time_key in time_keys:
                timestamp = datetime.combine(date_to_crawl, datetime.strptime(time_key, "%H:%M").time())
                timestamp = timestamp.replace(tzinfo=TimeHandler.get_timezone())
                if timestamp <= newest_value_saved_timestamp:
                    self.log.trace(f"Skipping values of {timestamp} as they are already saved in the database")
                    continue

                self.database_handler.write_to_database(
                    [
                        InfluxDBField(
                            "solar_generation_in_watts",
                            self._get_value_of_line_by_line_index_and_time_key(lines, 0, time_key),
                        ),
                        InfluxDBField(
                            "battery_charge_in_watts",
                            self._get_value_of_line_by_line_index_and_time_key(lines, 1, time_key) * -1,
                        ),
                        InfluxDBField(
                            "grid_usage_in_watts",
                            self._get_value_of_line_by_line_index_and_time_key(lines, 2, time_key) * -1,
                        ),
                        InfluxDBField(
                            "power_usage_in_watts",
                            self._get_value_of_line_by_line_index_and_time_key(lines, 3, time_key),
                        ),
                        InfluxDBField(
                            "state_of_charge_in_percent",
                            self._get_value_of_line_by_line_index_and_time_key(lines, 4, time_key),
                        ),
                        InfluxDBField(
                            "timestamp",
                            timestamp.isoformat(),
                        ),
                    ]
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

    def get_battery_capacity(self) -> EnergyAmount:
        """
        Retrieves the battery capacity from the SEMSPORTAL API.

        Returns:
            EnergyAmount: The battery capacity retrieved from the SEMSPORTAL API.
        """
        self.login()

        self.log.debug("Crawling the SEMSPORTAL API for the capacity of the battery...")

        url = "https://eu.semsportal.com/api/v3/PowerStation/GetPlantDetailByPowerstationId"
        headers = {
            "Content-Type": "application/json",
            "Token": f'{{"version":"v2.1.0","client":"ios","language":"en", "timestamp": "{self.timestamp}", "uid": "{self.user_id}", "token": "{self.token}"}}',
        }
        payload = {
            "powerStationId": EnvironmentVariableGetter.get("SEMSPORTAL_POWERSTATION_ID"),
        }

        response = requests.post(url, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        response = response.json()

        self.log.trace(f"Retrieved data: {response}")

        try:
            return EnergyAmount.from_kilo_watt_hours(response["data"]["info"]["battery_capacity"])
        except (KeyError, TypeError):
            # This is not that bad as we pull the battery capacity every iteration
            # If this is the first time after starting we don't even use the value
            self.log.warning(
                "Unable to retrieve battery capacity from SEMSPORTAL API, using a default value", exc_info=True
            )
            return EnergyAmount.from_kilo_watt_hours(10)
