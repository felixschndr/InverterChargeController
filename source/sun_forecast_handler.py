from datetime import datetime, timedelta

import requests
from energy_amount import EnergyAmount, Power
from environment_variable_getter import EnvironmentVariableGetter
from isodate import parse_duration
from logger import LoggerMixin
from time_handler import TimeHandler


class SunForecastHandler(LoggerMixin):
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

    def _get_debug_solar_output(self) -> EnergyAmount:
        """
        Returns a sample debug value for solar energy output.

        Returns:
            EnergyAmount: A sample energy amount of 10,000 watt-hours.
        """
        # We use a sample value for debugging the code since the API offers very limited call per day
        self.log.debug("Getting debug estimated solar output of today")
        return EnergyAmount(watt_hours=10000)

    def get_solar_output_in_timeframe_for_rooftop(
        self, timestamp_start: datetime, timestamp_end: datetime, rooftop_id: str
    ) -> EnergyAmount:
        """
        Retrieves the solar energy output within a specific timeframe for a given rooftop
        identifier by combining historical data and forecast data as needed.

        This method calculates the expected solar energy output for a rooftop in the
        specified timeframe. It retrieves historical solar data if the timeframe includes
        past periods, and forecast data for future periods. The retrieved data is used
        to compute the overlap between the requested timeframe and each data timeslot,
        determining the energy produced during those overlapping intervals.

        Args:
            timestamp_start: Start of the desired timeframe for solar energy calculation.
            timestamp_end: End of the desired timeframe for solar energy calculation.
            rooftop_id: Identifier of the rooftop for which the solar output is being calculated.

        Returns:
            EnergyAmount: The total expected solar energy output in the specified timeframe.
        """
        solar_data = []

        now = TimeHandler.get_time().replace(second=0, microsecond=0) - timedelta(
            seconds=1
        )  # Account for execution times of the program
        if timestamp_start >= now or timestamp_end >= now:
            self.log.trace("Need to retrieve forecast data")
            solar_data += self.retrieve_solar_forecast_data(rooftop_id)
        if timestamp_start <= now:
            self.log.trace("Need to retrieve historic data")
            solar_data += self.retrieve_historic_data(rooftop_id)
        solar_data.sort(key=lambda x: x["period_end"])

        expected_solar_output = EnergyAmount(0)
        timeslot_duration = parse_duration(solar_data[0]["period"])
        for timeslot in solar_data:
            timeslot_end = datetime.fromisoformat(timeslot["period_end"]).astimezone()
            timeslot_start = timeslot_end - timeslot_duration
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
                + f"from {max(timeslot_start, timestamp_start)} to {min(timeslot_end, timestamp_end)}, thus producing "
                + f"{energy_produced_in_timeslot} in that timeframe"
            )
            expected_solar_output += energy_produced_in_timeslot

        return expected_solar_output

    def get_solar_output_in_timeframe(self, timestamp_start: datetime, timestamp_end: datetime) -> EnergyAmount:
        """
        Calculates the estimated solar output over a specified time frame by aggregating the
        solar output from one or more rooftop solar installations.

        This method retrieves the solar output for a given time frame across a collection of
        rooftop installations specified via environment variables. It iteratively fetches solar
        output for each rooftop and aggregates the result into a single value.

        Args:
            timestamp_start (datetime): The start timestamp of the timeframe for which expected
                solar output is to be calculated.
            timestamp_end (datetime): The end timestamp of the timeframe for which expected
                solar output is to be calculated.

        Returns:
            EnergyAmount: The aggregated solar output from all specified rooftops within the given
                timeframe.
        """
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
