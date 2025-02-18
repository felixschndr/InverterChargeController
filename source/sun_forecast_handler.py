import json
import os.path
from datetime import datetime, time, timedelta
from pathlib import Path

import requests
from database_handler import DatabaseHandler, InfluxDBField
from energy_classes import EnergyAmount, Power, StateOfCharge
from environment_variable_getter import EnvironmentVariableGetter
from isodate import parse_duration
from logger import LoggerMixin
from time_handler import TimeHandler


class SunForecastHandler(LoggerMixin):
    POWER_USAGE_INCREASE_FACTOR = 1.25  # this factor is applied when the next price minimum has to be re-checked

    def __init__(self):
        super().__init__()

        self.timeframe_duration = None

        self.database_handler = DatabaseHandler("solar_forecast")

    def calculate_min_and_max_of_soc_in_timeframe(
        self,
        timeframe_start: datetime,
        timeframe_end: datetime,
        average_power_usage: Power,
        starting_soc: StateOfCharge,
        minimum_has_to_rechecked: bool,
    ) -> tuple[StateOfCharge, StateOfCharge]:
        """
        Calculates the minimum state of charge (SOC) and maximum state of charge within a specified timeframe.
        It considers average power usage, initial SOC and optionally adjusts for higher power usage in cases where the
        pricing for the next day is unavailable. This function uses solar data and iteratively computes power usage and
        generation for subintervals within the timeframe.

        Args:
            timeframe_start: The starting timestamp of the timeframe.
            timeframe_end: The ending timestamp of the timeframe.
            average_power_usage: The average power consumption over the timeframe.
            starting_soc: The battery's state of charge at the beginning of the timeframe.
            minimum_has_to_rechecked: Whether to increase the power usage by POWER_USAGE_INCREASE_FACTOR

        Returns:
            A tuple containing:
                - The minimum state of charge observed during the timeframe.
                - The maximum state of charge observed during the timeframe.
        """
        self.log.debug(
            "Calculating the estimated minimum of state of charge and power generation in the timeframe "
            f"{timeframe_start} to {timeframe_end}"
        )
        power_usage_increase_factor = 1.00
        if minimum_has_to_rechecked:
            power_usage_increase_factor = SunForecastHandler.POWER_USAGE_INCREASE_FACTOR
            self.log.info(
                "The upcoming price minimum has to be re-checked since it is at the end of a day and the price rates "
                "for tomorrow are unavailable --> The expected power usage is multiplied by "
                f"{SunForecastHandler.POWER_USAGE_INCREASE_FACTOR}"
            )

        solar_data = self.retrieve_solar_data(timeframe_start, timeframe_end)

        current_timeframe_start = timeframe_start
        soc_after_current_timeframe = starting_soc
        minimum_soc = starting_soc
        maximum_soc = starting_soc
        total_energy_used = EnergyAmount(0)
        total_energy_harvested = EnergyAmount(0)

        first_iteration = True
        while True:
            if first_iteration:
                next_step_minutes = int(self.timeframe_duration.total_seconds() / 60)
                next_half_hour_timestamp = timeframe_start.replace(minute=next_step_minutes, second=0)
                if timeframe_start.minute >= next_step_minutes:
                    next_half_hour_timestamp += self.timeframe_duration
                current_timeframe_duration = next_half_hour_timestamp - current_timeframe_start
                first_iteration = False
            else:
                current_timeframe_duration = self.timeframe_duration

            current_timeframe_end = current_timeframe_start + current_timeframe_duration

            energy_usage_during_timeframe = self._calculate_energy_usage_in_timeframe(
                current_timeframe_start, current_timeframe_duration, average_power_usage, power_usage_increase_factor
            )
            total_energy_used += energy_usage_during_timeframe
            energy_harvested_during_timeframe = self._get_energy_harvested_in_timeframe_from_solar_data(
                current_timeframe_end, current_timeframe_duration, solar_data
            )
            total_energy_harvested += energy_harvested_during_timeframe
            soc_after_current_timeframe = StateOfCharge(
                soc_after_current_timeframe.absolute
                - energy_usage_during_timeframe
                + energy_harvested_during_timeframe
            )

            if soc_after_current_timeframe < minimum_soc:
                log_text = " (new minimum)"
                minimum_soc = soc_after_current_timeframe
            elif soc_after_current_timeframe > maximum_soc:
                log_text = " (new maximum)"
                maximum_soc = soc_after_current_timeframe
            else:
                log_text = ""
            self.log.debug(
                f"{current_timeframe_end}"
                f" - estimated SOC: {soc_after_current_timeframe}{log_text}"
                f" - expected energy used: {energy_usage_during_timeframe}"
                f" - expected energy harvested: {energy_harvested_during_timeframe}"
            )
            current_timeframe_start += current_timeframe_duration

            if current_timeframe_start >= timeframe_end:
                break

        self.log.debug(
            f"From {timeframe_start} to {timeframe_end} the expected minimum of state of charge is {minimum_soc}, "
            f"the expected maximum of state of charge is {maximum_soc}, "
            f"the expected total amount of energy used is {total_energy_used} "
            f"and the expected total amount of energy harvested is {total_energy_harvested}"
        )
        return minimum_soc, maximum_soc

    def retrieve_solar_data(self, timeframe_start: datetime, timeframe_end: datetime) -> dict[str, Power]:
        """
        Retrieves solar data for a specified timeframe either from the solar forecast API or a debug solar output
        depending on the configuration and API response.

        If the environment variable "USE_DEBUG_SOLAR_OUTPUT" is set to True, or in the case of an HTTP 429 error
        (too many requests) from the solar forecast API, the method falls back to using a debug solar data output.

        Args:
            timeframe_start: Start date and time of the timeframe for which solar data is requested.
            timeframe_end: End date and time of the timeframe for which solar data is requested.

        Returns:
            A dictionary where keys represent specific times and values represent the forecasted power at those times.

        Raises:
            requests.exceptions.HTTPError: Raised if an HTTP error other than 429 occurs while fetching solar data from
                the API.
        """
        if EnvironmentVariableGetter.get("USE_DEBUG_SOLAR_OUTPUT", False):
            return self._get_debug_solar_data()

        try:
            return self.retrieve_solar_data_from_api(timeframe_start, timeframe_end)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code != 429:
                raise e
            self.log.warning("Too many requests to the solar forecast API, using the debug solar output instead")
            return self._get_debug_solar_data()

    def retrieve_solar_data_from_api(self, timeframe_start: datetime, timeframe_end: datetime) -> dict[str, Power]:
        """
        Retrieves solar data from an API over a specified timeframe. The function collects photovoltaic forecasts and/or
        historic data for multiple rooftops, processes the data into a dictionary mapping timestamps to cumulative power
        values, and writes relevant data to a database.

        Args:
            timeframe_start (datetime): The start of the timeframe for which to retrieve solar data.
            timeframe_end (datetime): The end of the timeframe for which to retrieve solar data.

        Returns:
            dict[str, Power]: A dictionary where keys represent timestamps (as ISO format strings) and values are Power
                objects corresponding to the cumulative power generation.
        """
        rooftop_ids = self._get_rooftop_ids()

        need_to_retrieve_forecast_data, need_to_retrieve_historic_data = self._need_to_retrieve_data(
            timeframe_start, timeframe_end
        )

        solar_data = {}

        now = TimeHandler.get_time().isoformat()
        for rooftop_id in rooftop_ids:
            data_for_rooftop = []
            if need_to_retrieve_historic_data:
                data_for_rooftop += self.retrieve_historic_data_from_api(rooftop_id)
            if need_to_retrieve_forecast_data:
                data_for_rooftop += self.retrieve_forecast_data_from_api(rooftop_id)
            self.timeframe_duration = parse_duration(data_for_rooftop[0]["period"])
            for timeslot in data_for_rooftop:
                period_start = (
                    datetime.fromisoformat(timeslot["period_end"]).astimezone() - self.timeframe_duration
                ).isoformat()
                if period_start not in solar_data.keys():
                    solar_data[period_start] = Power(0)
                solar_data[period_start] += Power.from_kilo_watts(timeslot["pv_estimate"])

                self.database_handler.write_to_database(
                    [
                        InfluxDBField("pv_estimate_in_watts", float(timeslot["pv_estimate"] * 1000)),
                        InfluxDBField("forecast_timestamp", period_start),
                        InfluxDBField("retrieval_timestamp", now),
                        InfluxDBField("rooftop_id", rooftop_id),
                    ]
                )

        return solar_data

    def retrieve_forecast_data_from_api(self, rooftop_id: str) -> list[dict]:
        return self._retrieve_data_from_api(rooftop_id, "forecasts")

    def retrieve_historic_data_from_api(self, rooftop_id: str) -> list[dict]:
        return self._retrieve_data_from_api(rooftop_id, "estimated_actuals")

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

    @staticmethod
    def _get_rooftop_ids() -> list[str]:
        """
        This static method retrieves rooftop IDs defined in environment variables and returns them as a list

        Returns:
            list[str]: A list containing one or two rooftop IDs retrieved from the environment variables.
        """
        rooftop_ids = [EnvironmentVariableGetter.get("ROOFTOP_ID_1")]
        rooftop_id_2 = EnvironmentVariableGetter.get("ROOFTOP_ID_2", None)
        if rooftop_id_2 is not None:
            rooftop_ids.append(rooftop_id_2)
        return rooftop_ids

    def _need_to_retrieve_data(self, timeframe_start: datetime, timeframe_end: datetime) -> tuple[bool, bool]:
        """
        This method evaluates whether either historic data or forecast data needs to be retrieved based on the given
        start and end timeframes in comparison to the current time.

        Args:
            timeframe_start (datetime): The start of the timeframe for evaluation.
            timeframe_end (datetime): The end of the timeframe for evaluation.

        Returns:
            tuple[bool, bool]: A tuple containing two boolean values:
                - The first boolean indicates whether retrieval of forecast data is required.
                - The second boolean indicates whether retrieval of historic data is required.
        """
        need_to_retrieve_historic_data = False
        need_to_retrieve_forecast_data = False
        now_minus_offset = TimeHandler.get_time(sanitize_seconds=True) - timedelta(seconds=1)
        if timeframe_start >= now_minus_offset or timeframe_end >= now_minus_offset:
            self.log.debug("Need to retrieve forecast data")
            need_to_retrieve_forecast_data = True
        if timeframe_start <= now_minus_offset:
            self.log.debug("Need to retrieve historic data")
            need_to_retrieve_historic_data = True
        return need_to_retrieve_forecast_data, need_to_retrieve_historic_data

    @staticmethod
    def _calculate_energy_usage_in_timeframe(
        timeframe_start: datetime,
        timeframe_duration: timedelta,
        average_power_consumption: Power,
        power_usage_increase_factor: float = 1.00,
    ) -> EnergyAmount:
        """
        Calculates the energy usage within a specific timeframe considering day and night power usage factors.

        The method calculates the energy consumption based on the specified start time, duration of the timeframe, and
        the average power consumption. It applies different power usage factors for daytime and nighttime, depending on
        the given timeframe.

        Args:
            timeframe_start (datetime): The starting datetime of the timeframe for which the energy usage needs to be
                calculated.
            timeframe_duration (timedelta): The duration of the timeframe for which the energy usage is to be calculated.
            average_power_consumption (Power): The average power consumption during the specified timeframe.

        Returns:
            EnergyAmount: The calculated energy usage in the provided timeframe.
        """
        day_start = time(6, 0)
        night_start = time(18, 0)
        factor_energy_usage_during_the_day = float(EnvironmentVariableGetter.get("POWER_USAGE_FACTOR", 0.6))
        factor_energy_usage_during_the_night = 1 - factor_energy_usage_during_the_day

        if not 0 <= factor_energy_usage_during_the_day <= 1:
            raise ValueError(
                f'The "POWER_USAGE_FACTOR" has to be between 0 and 1 (actual: {factor_energy_usage_during_the_day})!'
            )

        average_power_usage = EnergyAmount.from_watt_seconds(
            average_power_consumption.watts * timeframe_duration.total_seconds() * power_usage_increase_factor * 2
        )
        if day_start <= timeframe_start.time() < night_start:
            return average_power_usage * factor_energy_usage_during_the_day
        return average_power_usage * factor_energy_usage_during_the_night

    def _get_energy_harvested_in_timeframe_from_solar_data(
        self, timeframe_end: datetime, timeframe_duration: timedelta, solar_data: dict[str, Power]
    ) -> EnergyAmount:
        """
        Fetches the energy produced during a specific timeframe from the provided solar data. The method determines the
        power output at a given moment identified by `timeframe_end`, calculates the energy produced over the duration
        specified, and returns it.

        Args:
            timeframe_end (datetime): The end timestamp of the timeframe for which energy production is to be
                calculated, defined in ISO format.
            timeframe_duration (timedelta): The duration for which energy production is calculated, starting from
                `timeframe_end` and going backwards.
            solar_data (dict[str, Power]): A dictionary where keys are timestamps in ISO format and values represent the
                power output at those specific times.

        Returns:
            EnergyAmount: The energy produced during the specified timeframe, computed as the power at `timeframe_end`
                multiplied by the duration in seconds.

        Raises:
            KeyError: If the specified `timeframe_end` is not a key in the `solar_data` dictionary.
                This should never happen.
        """
        try:
            power_during_timeslot = solar_data[timeframe_end.isoformat()]
            return EnergyAmount.from_watt_seconds(power_during_timeslot.watts * timeframe_duration.total_seconds())
        except KeyError as e:
            # This should never happen
            self.log.critical(
                f"The timeframe end {timeframe_end} is not found in the provided solar data {solar_data}",
                exc_info=True,
            )
            raise e

    def _get_debug_solar_data(self) -> dict[str, Power]:
        """
        Retrieves debug solar data for testing or fallback purposes.

        This private method reads sample solar forecast data from a predefined JSON file
        and adjusts the timestamps to the current replaceable timestamp. It then converts
        the power estimate in kilowatts to the required `Power` object and organizes
        the data into a dictionary structured by time periods.

        Returns:
            dict[str, Power]: A dictionary where the keys are ISO-formatted timestamps and
            the values are `Power` objects representing the estimated solar power generation
            for the corresponding time period.
        """
        current_replace_timestamp = TimeHandler.get_time(sanitize_seconds=True).replace(minute=0)
        sample_data_path = os.path.join(Path(__file__).parent.parent, "sample_solar_forecast.json")
        sample_data = {}
        with open(sample_data_path, "r") as file:
            sample_input_data = json.load(file)["forecasts"]
        self.timeframe_duration = parse_duration(sample_input_data[0]["period"])
        for timeslot in sample_input_data:
            timeslot["period_end"] = current_replace_timestamp.isoformat()
            current_replace_timestamp += self.timeframe_duration
            sample_data[current_replace_timestamp.isoformat()] = Power.from_kilo_watts(timeslot["pv_estimate"])
        return sample_data
