import json
import os.path
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from database_handler import DatabaseHandler, InfluxDBField
from energy_classes import EnergyAmount, Power
from environment_variable_getter import EnvironmentVariableGetter
from isodate import parse_duration
from logger import LoggerMixin
from time_handler import TimeHandler


class SunForecastHandler(LoggerMixin):
    def __init__(self):
        super().__init__()

        self.database_handler = DatabaseHandler("sun_forecast")

    def _retrieve_data_from_api(self, rooftop_id: str, path: str) -> list[dict]:
        """
        Retrieves data from the Solcast API for a given rooftop site and data path.

        Args:
            rooftop_id (str): The unique identifier for the rooftop site.
            path (str): The specific data path to retrieve from the API.

        Returns:
            list[dict]: A list of dictionaries containing the retrieved data.
        """
        api_base_url = "https://api.solcast.com.au/rooftop_sites/{0}/{1}?format=json"
        url = api_base_url.format(rooftop_id, path)
        headers = {"Authorization": f"Bearer {EnvironmentVariableGetter.get('SOLCAST_API_KEY')}"}
        response = requests.get(url, timeout=5, headers=headers)
        response.raise_for_status()

        data = response.json()
        self.log.trace(f"Retrieved data: {data}")
        return data[path]

    def retrieve_solar_forecast_data(self, rooftop_id: str) -> list[dict]:
        return self._retrieve_data_from_api(rooftop_id, "forecasts")

    def retrieve_historic_data(self, rooftop_id: str) -> list[dict]:
        return self._retrieve_data_from_api(rooftop_id, "estimated_actuals")

    def _calculate_energy_produced_in_timeframe(
        self,
        solar_data: list[dict],
        timestamp_start: datetime,
        timestamp_end: datetime,
        rooftop_id: Optional[str] = None,
        write_to_database: bool = True,
    ) -> EnergyAmount:
        """
        Calculates the expected energy produced within a specified timeframe using given solar data.

        This function processes a list of solar data entries, evaluates the energy output for each timeslot, and
        calculates the total energy produced in the given timeframe.
        Additionally, it optionally logs the data into a database, if not specified otherwise.

        Args:
            solar_data: A list of dictionaries containing information about solar data timeslots. Each dictionary must
                include "period" (duration of the timeslot), "period_end" (end time of the timeslot in ISO 8601 format),
                and "pv_estimate" (estimated power generation in kilowatts for the timeslot).
            timestamp_start: Start of the desired timeframe for solar energy calculation.
            timestamp_end: End of the desired timeframe for solar energy calculation.
            rooftop_id: The identifier of the rooftop installation associated with the solar data.
                Must only be provided if write_to_database is True.
            write_to_database: A flag indicating whether to log processed data into a database. If set to `True`, the
                function writes the solar data to the database for each timeslot.

        Returns:
            The total energy produced within the specified timeframe, represented as an EnergyAmount object. This value
            is calculated based on the overlap between the input timeframe and the available timeslots in the solar data.
        """
        expected_solar_output = EnergyAmount(0)
        timeslot_duration = parse_duration(solar_data[0]["period"])

        now = TimeHandler.get_time().isoformat()
        for timeslot in solar_data:
            timeslot_end = datetime.fromisoformat(timeslot["period_end"]).astimezone()
            timeslot_start = timeslot_end - timeslot_duration

            if write_to_database:
                self.database_handler.write_to_database(
                    [
                        InfluxDBField("pv_estimate_in_watts", float(timeslot["pv_estimate"] * 1000)),
                        InfluxDBField("forecast_timestamp", timeslot_start.isoformat()),
                        InfluxDBField("retrieval_timestamp", now),
                        InfluxDBField("rooftop_id", rooftop_id),
                    ]
                )

            overlap = TimeHandler.calculate_overlap_between_time_frames(
                timestamp_start, timestamp_end, timeslot_start, timeslot_end
            )
            if overlap.total_seconds() == 0:
                continue

            power_in_timeslot = Power.from_kilo_watts(timeslot["pv_estimate"])
            energy_produced_in_timeslot = EnergyAmount.from_watt_seconds(
                power_in_timeslot.watts * overlap.total_seconds()
            )
            self.log.trace(
                f"There is an estimated power generation of {power_in_timeslot} "
                f"from {max(timeslot_start, timestamp_start)} to {min(timeslot_end, timestamp_end)}, thus producing "
                f"{energy_produced_in_timeslot} in that timeframe"
            )
            expected_solar_output += energy_produced_in_timeslot

        return expected_solar_output

    def get_solar_output_in_timeframe_for_rooftop(
        self, timestamp_start: datetime, timestamp_end: datetime, rooftop_id: str
    ) -> EnergyAmount:
        """
        Calculates the solar energy output within a specified timeframe for a given rooftop. It retrieves historical
        solar data if the timeframe includes past periods and forecast data for future periods.

        Args:
            timestamp_start: Start of the desired timeframe for solar energy calculation.
            timestamp_end: End of the desired timeframe for solar energy calculation.
            rooftop_id: The unique identifier of the rooftop for which the solar energy output needs to be calculated.

        Returns:
            EnergyAmount: The aggregated solar output from the specified rooftop within the given timeframe.
        """
        solar_data = []

        # TODO: Check the logic here
        now = TimeHandler.get_time().replace(second=0, microsecond=0) - timedelta(
            seconds=1
        )  # Account for execution times of the program
        self.log.debug(f"Time values: {timestamp_start}, {timestamp_end}, {now}")
        if timestamp_start >= now or timestamp_end >= now:
            self.log.debug("Need to retrieve forecast data")
            solar_data += self.retrieve_solar_forecast_data(rooftop_id)
        if timestamp_start <= now:
            self.log.debug("Need to retrieve historic data")
            solar_data += self.retrieve_historic_data(rooftop_id)
        solar_data.sort(key=lambda x: x["period_end"])

        return self._calculate_energy_produced_in_timeframe(solar_data, timestamp_start, timestamp_end, rooftop_id)

    def get_solar_output_in_timeframe(self, timestamp_start: datetime, timestamp_end: datetime) -> EnergyAmount:
        """
        Calculates the estimated solar output over a specified time frame by aggregating the solar output from one or
        two rooftop solar installations.I t iteratively fetches solar output for each rooftop and aggregates the
        result into a single value.

        Args:
            timestamp_start: Start of the desired timeframe for solar energy calculation.
            timestamp_end: End of the desired timeframe for solar energy calculation.

        Returns:
            EnergyAmount: The aggregated solar output from all specified rooftops within the given timeframe.
        """
        try:
            expected_solar_output = EnergyAmount(0)
            rooftop_ids = [EnvironmentVariableGetter.get("ROOFTOP_ID_1")]
            rooftop_id_2 = EnvironmentVariableGetter.get("ROOFTOP_ID_2", None)
            if rooftop_id_2 is not None:
                rooftop_ids.append(rooftop_id_2)

            for rooftop_id in rooftop_ids:
                self.log.debug(f'Getting the estimated solar output for rooftop "{rooftop_id}"')
                solar_forecast_for_rooftop = self.get_solar_output_in_timeframe_for_rooftop(
                    timestamp_start, timestamp_end, rooftop_id
                )
                self.log.debug(f'The expected solar output for rooftop "{rooftop_id}" is {solar_forecast_for_rooftop}')
                expected_solar_output += solar_forecast_for_rooftop

            return expected_solar_output

        except requests.exceptions.HTTPError as e:
            if e.response.status_code != 429:
                raise e
            self.log.warning("Too many requests to the solar forecast API, using the debug solar output instead")
            return self._get_debug_solar_output_in_timeframe(timestamp_start, timestamp_end)

    def _get_debug_solar_output_in_timeframe(self, timestamp_start: datetime, timestamp_end: datetime) -> EnergyAmount:
        """
        Fetches the solar energy production for a specified timeframe using sample solar
        forecast data from disk. The function adjusts the provided time range to use data from a
        predetermined day and calculates the energy produced in the adjusted timeframe.
        The results are not stored in any database.

        This value is also used when the API returns a 429 (Too Many Requests) error.

        Args:
            timestamp_start: Start of the desired timeframe for solar energy calculation.
            timestamp_end: End of the desired timeframe for solar energy calculation.

        Returns:
            EnergyAmount: The aggregated solar output from all specified rooftops within the given timeframe.
        """

        sample_data_path = os.path.join(Path(__file__).parent.parent, "sample_solar_forecast.json")
        with open(sample_data_path, "r") as file:
            sample_data = json.load(file)["forecasts"]
        duration = timestamp_end - timestamp_start
        timestamp_start = timestamp_start.replace(year=2025, month=1, day=6)
        timestamp_end = timestamp_start + duration

        return self._calculate_energy_produced_in_timeframe(
            sample_data, timestamp_start, timestamp_end, write_to_database=False
        )


if __name__ == "__main__":
    s = SunForecastHandler()
    start = TimeHandler.get_time() + timedelta(hours=1)
    ende = start + timedelta(hours=5)
    s.get_solar_output_in_timeframe(start, ende)
