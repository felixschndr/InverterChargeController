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
    def __init__(self):
        super().__init__()

        self.default_timeframe_duration = timedelta(minutes=30)

        self.database_handler = DatabaseHandler("solar_forecast")

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

    def retrieve_forecast_data(self, rooftop_id: str) -> list[dict]:
        return self._retrieve_data_from_api(rooftop_id, "forecasts")

    def retrieve_historic_data(self, rooftop_id: str) -> list[dict]:
        return self._retrieve_data_from_api(rooftop_id, "estimated_actuals")

    def retrieve_solar_data(self, timeframe_start: datetime, timeframe_end: datetime) -> dict[str, float]:
        rooftop_ids = [EnvironmentVariableGetter.get("ROOFTOP_ID_1")]
        rooftop_id_2 = EnvironmentVariableGetter.get("ROOFTOP_ID_2", None)
        if rooftop_id_2 is not None:
            rooftop_ids.append(rooftop_id_2)

        need_to_retrieve_historic_data = False
        need_to_retrieve_forecast_data = False
        now = TimeHandler.get_time(sanitize_seconds=True)
        now_minus_offset = now - timedelta(seconds=1)
        if timeframe_start >= now_minus_offset or timeframe_end >= now_minus_offset:
            self.log.debug("Need to retrieve forecast data")
            need_to_retrieve_forecast_data = True
        if timeframe_start <= now_minus_offset:
            self.log.debug("Need to retrieve historic data")
            need_to_retrieve_historic_data = True

        solar_data = {}

        for rooftop_id in rooftop_ids:
            data_for_rooftop = []
            if need_to_retrieve_historic_data:
                data_for_rooftop += self.retrieve_historic_data(rooftop_id)
            if need_to_retrieve_forecast_data:
                data_for_rooftop += self.retrieve_forecast_data(rooftop_id)
            period_duration = parse_duration(data_for_rooftop[0]["period"])
            for timeslot in data_for_rooftop:
                period_start = (
                    datetime.fromisoformat(timeslot["period_end"]).astimezone() - period_duration
                ).isoformat()
                if timeslot[period_start] not in solar_data.keys():
                    solar_data[timeslot[period_start]] = timeslot["pv_estimate"]
                else:
                    solar_data[timeslot[period_start]] += timeslot["pv_estimate"]

                self.database_handler.write_to_database(
                    [
                        InfluxDBField("pv_estimate_in_watts", float(timeslot["pv_estimate"] * 1000)),
                        InfluxDBField("forecast_timestamp", period_start),
                        InfluxDBField("retrieval_timestamp", now.isoformat()),
                        InfluxDBField("rooftop_id", rooftop_id),
                    ]
                )

        return solar_data

    def calculate_minimum_of_soc_and_power_generation_in_timeframe(
        self,
        timeframe_start: datetime,
        timeframe_end: datetime,
        average_power_usage: Power,
        starting_soc: StateOfCharge,
    ) -> tuple[StateOfCharge, EnergyAmount]:
        if EnvironmentVariableGetter.get("USE_DEBUG_SOLAR_OUTPUT", False):
            solar_data = self._get_debug_solar_data()
        else:
            try:
                solar_data = self.retrieve_solar_data(timeframe_start, timeframe_end)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code != 429:
                    raise e
                self.log.warning("Too many requests to the solar forecast API, using the debug solar output instead")
                solar_data = self._get_debug_solar_data()

        current_timeframe_start = timeframe_start
        soc_after_current_timeframe = starting_soc
        minimum_soc = starting_soc
        total_power_usage = EnergyAmount(0)
        total_power_generation = EnergyAmount(0)

        first_iteration = True
        while True:
            if first_iteration:
                next_half_hour_timestamp = timeframe_start.replace(minute=30, second=0)
                if timeframe_start.minute >= 30:
                    next_half_hour_timestamp += self.default_timeframe_duration
                current_timeframe_duration = next_half_hour_timestamp - current_timeframe_start
                first_iteration = False
            else:
                current_timeframe_duration = self.default_timeframe_duration

            current_timeframe_end = current_timeframe_start + current_timeframe_duration

            power_usage_during_timeframe = self._calculate_energy_usage_in_timeframe(
                current_timeframe_start, current_timeframe_duration, average_power_usage
            )
            total_power_usage += power_usage_during_timeframe
            power_generation_during_timeframe = self._calculate_energy_produced_in_timeframe(
                current_timeframe_end, current_timeframe_duration, solar_data
            )
            total_power_generation += power_generation_during_timeframe
            soc_after_current_timeframe = StateOfCharge(
                soc_after_current_timeframe.absolute - power_usage_during_timeframe + power_generation_during_timeframe
            )

            if soc_after_current_timeframe < minimum_soc:
                log_text = "This is a new minimum in the amount of energy stored. "
                minimum_soc = soc_after_current_timeframe
            else:
                log_text = ""
            self.log.trace(
                f"The estimated energy saved in the battery at {current_timeframe_end} is "
                f"{soc_after_current_timeframe}. "
                f"{log_text}"
                f"The expected power usage during this slot is {power_usage_during_timeframe}. "
                f"The expected power generation during this slot is {power_generation_during_timeframe}. "
            )
            current_timeframe_start += current_timeframe_duration

            if current_timeframe_start > timeframe_end:
                break

        self.log.debug(
            f"From {timeframe_start} to {timeframe_end} the expected minimum of state of charge is {minimum_soc}, the "
            f"expected amount of power generated is {total_power_generation} and the expected amount of power used is "
            f"{total_power_usage}."
        )
        return minimum_soc, total_power_generation

    @staticmethod
    def _calculate_energy_usage_in_timeframe(
        timeframe_start: datetime, timeframe_duration: timedelta, average_power_consumption: Power
    ) -> EnergyAmount:
        day_start = time(6, 0)
        night_start = time(18, 0)
        factor_energy_usage_during_the_day = float(EnvironmentVariableGetter.get("POWER_USAGE_FACTOR", 0.6))
        factor_energy_usage_during_the_night = 1 - factor_energy_usage_during_the_day

        if not 0 <= factor_energy_usage_during_the_day <= 1:
            raise ValueError(
                f'The "POWER_USAGE_FACTOR" has to be between 0 and 1 (actual: {factor_energy_usage_during_the_day})!'
            )

        average_power_usage = EnergyAmount.from_watt_seconds(
            average_power_consumption.watts * timeframe_duration.total_seconds() * 2
        )
        if day_start <= timeframe_start.time() <= night_start:
            return average_power_usage * factor_energy_usage_during_the_day
        return average_power_usage * factor_energy_usage_during_the_night

    @staticmethod
    def _calculate_energy_produced_in_timeframe(
        timeframe_end: datetime, timeframe_duration: timedelta, solar_data: dict[str, float]
    ) -> EnergyAmount:
        power_during_timeslot = Power.from_kilo_watts(solar_data[timeframe_end.isoformat()])
        return EnergyAmount.from_watt_seconds(power_during_timeslot.watts * timeframe_duration.total_seconds())

    def _get_debug_solar_data(self) -> dict[str, float]:
        current_replace_timestamp = TimeHandler.get_time(sanitize_seconds=True).replace(minute=0)
        sample_data_path = os.path.join(Path(__file__).parent.parent, "sample_solar_forecast.json")
        sample_data = {}
        with open(sample_data_path, "r") as file:
            sample_input_data = json.load(file)["forecasts"]
        for timeslot in sample_input_data:
            timeslot["period_end"] = current_replace_timestamp.isoformat()
            current_replace_timestamp += self.default_timeframe_duration
            sample_data[current_replace_timestamp.isoformat()] = timeslot["pv_estimate"]
        return sample_data
