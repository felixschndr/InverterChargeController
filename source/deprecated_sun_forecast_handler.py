import datetime

import requests
from energy_amount import EnergyAmount, Power
from environment_variable_getter import EnvironmentVariableGetter
from logger import LoggerMixin
from suntimes import SunTimes
from time_handler import TimeHandler


class DeprecatedSunForecastHandler(LoggerMixin):
    API_BASE_URL = "https://api.forecast.solar/estimate/watthours/day"

    def __init__(self):
        super().__init__()

    @staticmethod
    def _get_date_as_string() -> str:
        """
        Returns:
            str: The current date formatted as 'YYYY-MM-DD'.
        """
        return datetime.datetime.now().strftime("%Y-%m-%d")

    def get_expected_solar_output_of_today(self) -> EnergyAmount:
        """
        Gets the expected solar energy output for the current day.

        Returns:
            EnergyAmount: The projected solar energy output for today in watt-hours.
        """
        self.log.debug("Getting estimated solar output of today")

        solar_pack_indices = [1]
        if EnvironmentVariableGetter.get("PANELS_PACK2_INSTALLED", False):
            solar_pack_indices.append(2)

        total_solar_forecast = EnergyAmount(0)
        latitude = EnvironmentVariableGetter.get("LOCATION_LATITUDE")
        longitude = EnvironmentVariableGetter.get("LOCATION_LONGITUDE")
        for index in solar_pack_indices:
            plane_declination = EnvironmentVariableGetter.get(f"PANELS_PACK{index}_PLANE_DECLINATION")
            plane_azimuth = EnvironmentVariableGetter.get(f"PANELS_PACK{index}_PLANE_AZIMUTH")
            number_of_panels = int(EnvironmentVariableGetter.get(f"PANELS_PACK{index}_NUMBER_OF_PANELS"))
            maximum_output_of_panel_in_watts = int(
                EnvironmentVariableGetter.get(f"PANELS_PACK{index}_MAXIMUM_POWER_OUTPUT_PER_PANEL")
            )
            maximum_output_of_all_panels_in_kw = number_of_panels * maximum_output_of_panel_in_watts / 1000
            url = f"{self.API_BASE_URL}/{latitude}/{longitude}/{plane_declination}/{plane_azimuth}/{maximum_output_of_all_panels_in_kw}"
            self.log.trace(f'Set API URL to "{url}"')

            response = requests.get(url, timeout=5)
            response.raise_for_status()

            data = response.json()
            self.log.trace(f"Retrieved data: {data}")

            total_solar_forecast += data["result"][self._get_date_as_string()]

        return total_solar_forecast

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
        """
        This method calculates the estimated solar power output within a specified time frame.
        It first determines the duration of daylight (sun is up) within the given timeframe.
        If there is no overlap between the given timeframe and the calculated daylight duration,
            it returns zero energy output.
        Otherwise, it calculates the expected solar output based on the average solar power output of the day and the
            duration of sunlight overlap in the specified timeframe.

        Similar to SemsPortalAPIHandler.get_energy_usage_in_timeframe().

        Args:
            timestamp_start: The starting timestamp of the timeframe for which to calculate the solar output.
            timestamp_end: The ending timestamp of the timeframe for which to calculate the solar output.

        Returns:
            EnergyAmount:
            The estimated amount of energy generated from solar output within the specified timeframe.

        """
        self.log.debug(f"Calculating estimated solar output between {timestamp_start} and {timestamp_end}")

        sunrise_plus_offset, sunset_minus_offset = self._get_sunset_and_sunrise_with_offset()
        daylight_duration_in_seconds = (sunset_minus_offset - sunrise_plus_offset).total_seconds()

        duration_of_timeframe_during_sunlight = TimeHandler.calculate_overlap_between_time_frames(
            timestamp_start, timestamp_end, sunrise_plus_offset, sunset_minus_offset
        )
        self.log.info(
            f"There is {duration_of_timeframe_during_sunlight} of sunlight (with 10 % offsets) during the given timeframe"
        )
        if duration_of_timeframe_during_sunlight.total_seconds() == 0:
            return EnergyAmount(0)

        solar_output_today = (
            self._get_debug_solar_output()
            if EnvironmentVariableGetter.get(name_of_variable="USE_DEBUG_SOLAR_OUTPUT", default_value=False)
            else self.get_expected_solar_output_of_today()
        )
        self.log.debug(f"Expected solar output of today is {solar_output_today}")
        average_solar_output = Power(watts=solar_output_today.watt_seconds / daylight_duration_in_seconds)
        self.log.debug(f"Average solar output today is {average_solar_output}")

        return EnergyAmount.from_watt_seconds(
            average_solar_output.watts * duration_of_timeframe_during_sunlight.total_seconds()
        )

    def _get_sunset_and_sunrise_with_offset(self) -> tuple[datetime, datetime]:
        """
        Calculates and returns the sunrise and sunset times with an offset.

        This method retrieves the current geographical location's latitude and longitude
        from environment variables, then calculates the sunrise and sunset times for the
        next day.
        It adds a 10% offset to the duration of sunlight to both the sunrise and
        sunset times since this is when the sun is at its lowest points and thus weakest.

        Returns:
            tuple[datetime, datetime]: A tuple containing the adjusted sunrise and sunset times.
        """
        date = datetime.datetime.now()
        sun = SunTimes(
            float(EnvironmentVariableGetter.get("LOCATION_LONGITUDE")),
            float(EnvironmentVariableGetter.get("LOCATION_LATITUDE")),
            int(EnvironmentVariableGetter.get("LOCATION_HEIGHT", 0)),
        )

        sunrise = sun.riselocal(date)
        sunset = sun.setlocal(date)
        sun_light_duration = sunset - sunrise
        sun_light_duration_offset = sun_light_duration * 0.1
        sunrise_plus_offset = sunrise + sun_light_duration_offset
        sunset_minus_offset = sunset - sun_light_duration_offset

        self.log.debug(
            f"Sunrise is at {sunrise}, sunset is at {sunset}, "
            + f"duration of sunlight is {sun_light_duration}, offset is {sun_light_duration_offset}, "
            + f"sunrise with offset is at {sunrise_plus_offset}, sunset with offset is at {sunset_minus_offset}"
        )

        return sunrise_plus_offset, sunset_minus_offset
