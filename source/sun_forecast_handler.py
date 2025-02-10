import json
import os.path
from datetime import datetime, time, timedelta
from pathlib import Path

import requests
from database_handler import DatabaseHandler
from energy_classes import EnergyAmount, Power, StateOfCharge
from environment_variable_getter import EnvironmentVariableGetter
from logger import LoggerMixin
from time_handler import TimeHandler


class SunForecastHandler(LoggerMixin):
    def __init__(self):
        super().__init__()

        self.timeslot_duration = timedelta(minutes=30)

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

    def retrieve_solar_forecast_data(self, rooftop_id: str) -> list[dict]:
        return self._retrieve_data_from_api(rooftop_id, "forecasts")

    def retrieve_historic_data(self, rooftop_id: str) -> list[dict]:
        return self._retrieve_data_from_api(rooftop_id, "estimated_actuals")

    def calculate_minimum_of_soc_until_next_price_minimum(
        self,
        next_price_minimum_timestamp: datetime,
        average_power_usage: Power,
        starting_soc: StateOfCharge,
    ) -> StateOfCharge:
        if EnvironmentVariableGetter.get("USE_DEBUG_SOLAR_OUTPUT", False):
            solar_data = self._get_debug_solar_data()
        else:
            try:
                # TODO: Aggregate the two rooftops
                # TODO: Write values to DB
                solar_data = self.retrieve_solar_forecast_data(EnvironmentVariableGetter.get("ROOFTOP_ID_1"))
            except requests.exceptions.HTTPError as e:
                if e.response.status_code != 429:
                    raise e
                self.log.warning("Too many requests to the solar forecast API, using the debug solar output instead")
                solar_data = self._get_debug_solar_data()

        now = TimeHandler.get_time()
        current_timeframe_start = now
        soc_after_current_timeframe = starting_soc
        minimum_soc = starting_soc

        first_iteration = True
        while True:
            if first_iteration:
                next_half_hour_timestamp = now.replace(minute=30, second=0)
                if now.minute >= 30:
                    next_half_hour_timestamp += self.timeslot_duration
                timeslot_duration = next_half_hour_timestamp - current_timeframe_start
                first_iteration = False
            else:
                timeslot_duration = self.timeslot_duration

            current_timeframe_end = current_timeframe_start + timeslot_duration

            power_usage_during_timeframe = self._calculate_energy_usage_in_timeframe(
                current_timeframe_start, timeslot_duration, average_power_usage
            )
            power_generation_during_timeframe = self._calculate_energy_produced_in_timeframe(
                current_timeframe_start, timeslot_duration, solar_data
            )
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
            current_timeframe_start += timeslot_duration

            if current_timeframe_start > next_price_minimum_timestamp:
                break

        return minimum_soc

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
        timeframe_start: datetime, timeframe_duration: timedelta, solar_data: list[dict]
    ) -> EnergyAmount:
        expected_solar_output = EnergyAmount(0)
        for timeslot in solar_data:
            timeslot_end = datetime.fromisoformat(timeslot["period_end"]).astimezone()
            timeslot_start = timeslot_end - timeframe_duration

            overlap = TimeHandler.calculate_overlap_between_time_frames(
                timeframe_start, timeframe_start + timeframe_duration, timeslot_start, timeslot_end
            )
            if overlap.total_seconds() == 0:
                continue

            power_during_timeslot = Power.from_kilo_watts(timeslot["pv_estimate"])
            energy_produced_in_timeslot = EnergyAmount.from_watt_seconds(
                power_during_timeslot.watts * overlap.total_seconds()
            )
            expected_solar_output += energy_produced_in_timeslot
        return expected_solar_output

    def _get_debug_solar_data(self) -> list[dict]:
        current_replace_timestamp = TimeHandler.get_time(sanitize_seconds=True).replace(minute=0)
        sample_data_path = os.path.join(Path(__file__).parent.parent, "sample_solar_forecast.json")
        with open(sample_data_path, "r") as file:
            sample_data = json.load(file)["forecasts"]
        for timeslot in sample_data:
            timeslot["period_end"] = current_replace_timestamp.isoformat()
            current_replace_timestamp += self.timeslot_duration
        return sample_data


if __name__ == "__main__":
    handler = SunForecastHandler()
    next_price_minimum_timestamp = (TimeHandler.get_time() + timedelta(hours=12)).replace(minute=0, second=0)
    print(
        handler.calculate_minimum_of_soc_until_next_price_minimum(
            next_price_minimum_timestamp, Power(150), EnergyAmount(4000)
        )
    )
