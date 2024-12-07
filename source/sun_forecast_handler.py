from datetime import datetime, timedelta

import requests
from energy_amount import EnergyAmount, Power
from environment_variable_getter import EnvironmentVariableGetter
from isodate import parse_duration
from logger import LoggerMixin
from time_handler import TimeHandler


class SunForecastHandler(LoggerMixin):
    def _retrieve_data_from_api(self, path: str) -> list[dict]:
        api_base_url = "https://api.solcast.com.au/rooftop_sites/{0}/{1}?format=json"
        url = api_base_url.format(EnvironmentVariableGetter.get("ROOFTOP_ID"), path)
        headers = {"Authorization": f"Bearer {EnvironmentVariableGetter.get('SOLCAST_API_KEY')}"}
        response = requests.get(url, timeout=5, headers=headers)
        response.raise_for_status()

        data = response.json()
        self.log.trace(f"Retrieved data: {data}")
        return data[path]

    def retrieve_solar_forecast_data(self) -> list[dict]:
        return self._retrieve_data_from_api("forecasts")

    def retrieve_historic_data(self) -> list[dict]:
        return self._retrieve_data_from_api("estimated_actuals")

    def _get_debug_solar_output(self) -> EnergyAmount:
        """
        Returns a sample debug value for solar energy output.

        Returns:
            EnergyAmount: A sample energy amount of 10,000 watt-hours.
        """
        # We use a sample value for debugging the code since the API offers very limited call per day
        self.log.debug("Getting debug estimated solar output of today")
        return EnergyAmount(watt_hours=10000)

    def get_solar_output_in_timeframe(self, timestamp_start: datetime, timestamp_end: datetime) -> EnergyAmount:
        solar_data = []

        now = datetime.now(tz=(TimeHandler.get_timezone())).replace(second=0, microsecond=0) - timedelta(
            seconds=1
        )  # Account for execution times of the program
        if timestamp_start >= now or timestamp_end >= now:
            self.log.trace("Need to retrieve forecast data")
            solar_data += self.retrieve_solar_forecast_data()
        if timestamp_start <= now:
            self.log.trace("Need to retrieve historic data")
            solar_data += self.retrieve_historic_data()
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


if __name__ == "__main__":
    new_solar_forecast_handler = SunForecastHandler()
    start = datetime.now(tz=TimeHandler.get_timezone()).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    # end = start + timedelta(hours=10)
    # start = datetime.now(tz=TimeHandler.get_timezone())
    # end = start + timedelta(hours=4)

    print(new_solar_forecast_handler.get_solar_output_in_timeframe(start, end))
