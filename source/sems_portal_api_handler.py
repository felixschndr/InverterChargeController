import base64
import hashlib
import json
import time as time_module
from datetime import date, datetime, time, timedelta

import requests

from source.database_handler import DatabaseHandler, InfluxDBField
from source.energy_classes import EnergyAmount, Power
from source.environment_variable_getter import EnvironmentVariableGetter
from source.logger import LoggerMixin
from source.time_handler import TimeHandler


class SemsPortalApiHandler(LoggerMixin):
    LOGIN_URL = "https://eu-semsplus.goodwe.com/web/sems/sems-user/api/v1/auth/cross-login"
    BROWSER_HEADERS = {
        "Content-Type": "application/json",
        "Origin": "https://eu-semsplus.goodwe.com",
        "Referer": "https://eu-semsplus.goodwe.com/",
        "User-Agent": "Mozilla/5.0",
    }

    def __init__(self):
        super().__init__()

        self.token = None

        self.database_handler = DatabaseHandler("power")

    def _login(self) -> None:
        """
        Authenticates the user at the SEMS+ API, the credentials are fetched from the environment variables.
        This is done before every request to the API, so an expired session never has to be handled.
        """
        self.log.trace("Logging in into SEMS+")
        token_before_login = {
            "uid": "",
            "timestamp": 0,
            "token": "",  # nosec B105
            "client": "semsPlusWeb",
            "version": "",
            "language": "en",
        }
        payload = {
            "account": EnvironmentVariableGetter.get("SEMSPORTAL_USERNAME"),
            "pwd": self._hash_password(EnvironmentVariableGetter.get("SEMSPORTAL_PASSWORD")),
            "agreement": 1,
            "isLocal": False,
            "isChinese": False,
        }

        self.token = self._post(self.LOGIN_URL, token_before_login, payload)

        self.log.trace("Login successful")

    def _request(self, path: str, payload: dict) -> dict:
        """
        Logs in and sends a POST request to the given path of the SEMS+ API.

        Returns:
            dict: The "data" part of the response.
        """
        self._login()
        return self._post(self.token["api"] + path, self.token, payload)

    def _post(self, url: str, token: dict, payload: dict) -> dict:
        headers = {
            **self.BROWSER_HEADERS,
            "token": json.dumps(token),
            "X-Signature": self._signature(token["uid"], token["token"]),
        }

        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        response = response.json()
        self.log.trace(f"Retrieved data: {response}")

        if response["code"] != "00000":
            # The API always returns a 200 status code, even if something went wrong
            raise RuntimeError(
                f"There was a problem with the SEMS+ API: {response.get('description')} (Code: {response['code']})"
            )

        return response["data"]

    @staticmethod
    def _hash_password(password: str) -> str:
        """The SEMS+ login expects the password as base64(md5 hex digest)."""
        md5_hex_digest = hashlib.md5(password.encode(), usedforsecurity=False).hexdigest()
        return base64.b64encode(md5_hex_digest.encode()).decode()

    @staticmethod
    def _signature(uid: str, token: str) -> str:
        """The SEMS+ API silently ignores requests without this X-Signature header."""
        timestamp_in_ms = str(round(time_module.time() * 1000))
        sha256_hex_digest = hashlib.sha256(f"{timestamp_in_ms}@{uid}@{token}".encode()).hexdigest()
        return base64.b64encode(f"{sha256_hex_digest}@{timestamp_in_ms}".encode()).decode()

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

        day = TimeHandler.get_date() - timedelta(days=days_in_past)
        data = self._request(
            "/sems-plant/api/stations/statistics",
            {
                "stationId": EnvironmentVariableGetter.get("SEMSPORTAL_POWERSTATION_ID"),
                "isReport": False,
                "items": ["proPurchaseStats"],
                "dimension": "day",
                "startTime": f"{day} 00:00:00",
                "endTime": f"{day} 23:59:59",
            },
        )

        return EnergyAmount.from_kilo_watt_hours(data["dataList"][0]["statisticsList"][0]["val"])

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

        today = TimeHandler.get_date()
        days_since_newest_value = (today - newest_value_saved_date).days
        maximum_fetch_days = 31
        if days_since_newest_value > maximum_fetch_days:
            days_since_newest_value = maximum_fetch_days

        days_since_newest_value += 1  # Since range starts at 0 and does not include the end
        self.log.debug(f"Writing values to the database for the last {days_since_newest_value} day(s)")

        for days_in_past in range(days_since_newest_value):
            date_to_crawl = today - timedelta(days=days_in_past)
            try:
                data = self._retrieve_power_data(date_to_crawl)
                # {"<item>": {"<YYYY-MM-DD HH:MM:SS>": <value in kW or % for "soc">, ...}, ...}
                # Points in the future (of today) have no values yet, so they are left out
                values = {
                    line["item"]: {
                        point["tp"]: point["power"] for point in line["powerData"] if point["power"] is not None
                    }
                    for line in data["dataList"]
                }
                items = ("pSystem", "pBat", "pGrid", "pConsum", "soc")
                time_keys = sorted(set.intersection(*(set(values[item]) for item in items)))
            except (RuntimeError, TypeError, KeyError) as error:
                self.log.warning(f"Error retrieving power data for {date_to_crawl}: {error!r}")
                continue

            for time_key in time_keys:
                solar, battery, grid, consumption, state_of_charge = (values[item][time_key] for item in items)

                timestamp = datetime.fromisoformat(time_key).replace(tzinfo=TimeHandler.get_timezone())
                if timestamp <= newest_value_saved_timestamp:
                    self.log.trace(f"Skipping values of {timestamp} as they are already saved in the database")
                    continue

                # The API counts battery discharge and grid feed as positive
                self.database_handler.write_to_database(
                    [
                        InfluxDBField("solar_generation_in_watts", self._kilo_watts_to_watts(solar)),
                        InfluxDBField("battery_charge_in_watts", self._kilo_watts_to_watts(battery) * -1),
                        InfluxDBField("grid_usage_in_watts", self._kilo_watts_to_watts(grid) * -1),
                        InfluxDBField("power_usage_in_watts", self._kilo_watts_to_watts(consumption)),
                        InfluxDBField("state_of_charge_in_percent", int(state_of_charge)),
                        InfluxDBField("timestamp", timestamp.isoformat()),
                    ]
                )

    def _retrieve_power_data(self, date_to_crawl: date) -> dict:
        """
        Retrieves the power data of one day in a 5 minute resolution from the SEMS+ API. This includes:
         - solar generation (pSystem)
         - battery charge/discharge (pBat)
         - grid consumption/feed (pGrid)
         - power usage (pConsum)
         - state of charge (soc)

        Returns:
            dict: The "data" part of the response, containing a "dataList" with one entry per item.
        """
        self.log.debug(f"Crawling the SEMS+ API for power data of {date_to_crawl}...")

        return self._request(
            "/sems-plant/api/v1/hems/power/statisticsAndPreV2",
            {
                "stationId": EnvironmentVariableGetter.get("SEMSPORTAL_POWERSTATION_ID"),
                "items": ["pSystem", "pBat", "pGrid", "pConsum", "soc"],
                "timeScale": 5,
                "timeZone": 0,  # Without it the response is empty, but its value does not change the data
                "startTime": f"{date_to_crawl} 00:00:00",
                "endTime": f"{date_to_crawl} 23:59:59",
            },
        )

    @staticmethod
    def _kilo_watts_to_watts(kilo_watts: float) -> int:
        return round(kilo_watts * 1000)

    def get_average_power_consumption_per_time_of_day_since(self, timestamp_in_past: datetime) -> dict[time, Power]:
        """
        Processes power consumption data from the database and calculates average power usage by time of day.

        This method:
        1. Retrieves power data from the database for now - time_in_past
        2. Groups the data by the time part of the timestamp (ignoring the date)
        3. Calculates the average power consumption for each time group

        Returns:
            dict: A dictionary with times as keys and average power usage as values
        """
        power_data = self.database_handler.get_values_since(timestamp_in_past, "timestamp")
        self.log.debug(f"Retrieved {len(power_data)} power data records from database since {timestamp_in_past}")

        time_groups = {}

        for record in power_data:
            timestamp = record.values.get("timestamp")
            if not timestamp:
                continue
            time_of_day = datetime.fromisoformat(timestamp).time()

            if time_of_day not in time_groups:
                time_groups[time_of_day] = []
            time_groups[time_of_day].append(record)

        result = {}
        for time_of_day, records in sorted(time_groups.items()):
            total_power = sum(Power(record.values.get("power_usage_in_watts", 0)) for record in records)
            result[time_of_day] = total_power / len(records) if records else Power(0)

        result_human_readable = ", ".join(f"{t}: {p}" for t, p in result.items())
        self.log.trace(f"Calculated average power consumption for each time of day: {result_human_readable}")

        return result
