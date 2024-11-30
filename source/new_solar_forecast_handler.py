from datetime import datetime, timedelta

import requests
from energy_amount import EnergyAmount, Power
from environment_variable_getter import EnvironmentVariableGetter
from isodate import parse_duration
from logger import LoggerMixin
from time_handler import TimeHandler


class NewSolarForecastHandler(LoggerMixin):
    API_BASE_URL = "https://api.solcast.com.au/rooftop_sites/{0}/forecasts?format=json"

    def retrieve_solar_forecast_data(self) -> list[dict]:
        url = NewSolarForecastHandler.API_BASE_URL.format(EnvironmentVariableGetter.get("ROOFTOP_ID"))
        headers = {"Authorization": f"Bearer {EnvironmentVariableGetter.get('SOLCAST_API_KEY')}"}
        response = requests.get(url, timeout=5, headers=headers)
        response.raise_for_status()

        data = response.json()
        self.log.trace(f"Retrieved data: {data}")
        return data["forecasts"]

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
        timezone = TimeHandler.get_timezone()
        expected_solar_output = EnergyAmount(0)

        forecast_data = self.retrieve_solar_forecast_data()

        timeslot_duration = parse_duration(forecast_data[0]["period"])
        for timeslot in forecast_data:
            timeslot_end = datetime.fromisoformat(timeslot["period_end"]).replace(tzinfo=timezone)
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
    new_solar_forecast_handler = NewSolarForecastHandler()
    start = datetime.now(tz=TimeHandler.get_timezone()).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
        days=1
    )
    end = start + timedelta(days=1)

    print(new_solar_forecast_handler.get_solar_output_in_timeframe(start, end))
