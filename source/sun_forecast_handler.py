import datetime
from datetime import timedelta

import requests
from dateutil.tz import tzfile
from environment_variable_getter import EnvironmentVariableGetter
from logger import LoggerMixin
from suntime import Sun


class SunForecastHandler(LoggerMixin):
    def __init__(self, timezone: tzfile):
        super().__init__()

        self.timezone = timezone
        self.forecast_api_url = self._forecast_api_url()

    def _forecast_api_url(self) -> str:
        api_base_url = "https://api.forecast.solar/estimate"

        latitude = EnvironmentVariableGetter.get("LOCATION_LATITUDE")
        longitude = EnvironmentVariableGetter.get("LOCATION_LONGITUDE")
        plane_declination = EnvironmentVariableGetter.get("LOCATION_PLANE_DECLINATION")
        plane_azimuth = EnvironmentVariableGetter.get("LOCATION_PLANE_AZIMUTH")
        number_of_panels = int(
            EnvironmentVariableGetter.get("LOCATION_NUMBER_OF_PANELS")
        )
        maximum_output_of_panel_in_watts = int(
            EnvironmentVariableGetter.get("LOCATION_MAXIMUM_POWER_OUTPUT_PER_PANEL")
        )

        maximum_output_of_all_panels_in_kw = (
            number_of_panels * maximum_output_of_panel_in_watts / 1000
        )

        url = f"{api_base_url}/{latitude}/{longitude}/{plane_declination}/{plane_azimuth}/{maximum_output_of_all_panels_in_kw}"
        self.log.trace(f'Set API URL to "{url}"')

        return url

    @staticmethod
    def _get_date_as_string() -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d")

    def _get_expected_solar_output_of_today_in_watt_hours(self) -> int:
        self.log.debug("Getting estimated solar output of today")

        response = requests.get(self.forecast_api_url, timeout=5)
        response.raise_for_status()

        data = response.json()
        self.log.trace(f"Retrieved data: {data}")
        return data["result"]["watt_hours_day"][self._get_date_as_string()]

    def _get_debug_solar_output_in_watt_hours(self) -> int:
        # We use a sample value for debugging the code since the API offers very limited call per day
        self.log.debug("Getting debug estimated solar output of today")
        return 10000

    def get_solar_output_in_timeframe_in_watt_hours(
        self, start_timestamp: datetime, end_timestamp: datetime
    ) -> int:
        self.log.debug(
            f"Getting estimated solar output between {start_timestamp} and {end_timestamp}"
        )

        sunrise_plus_offset, sunset_minus_offset = (
            self._get_sunset_and_sunrise_with_offset()
        )
        daylight_duration_in_seconds = (
            sunset_minus_offset - sunrise_plus_offset
        ).total_seconds()

        duration_of_timeframe_during_sunlight = (
            self._calculate_overlap_between_time_frames(
                start_timestamp, end_timestamp, sunrise_plus_offset, sunset_minus_offset
            )
        )
        self.log.info(
            f"There is {duration_of_timeframe_during_sunlight} of sunlight (with 10 % offsets) during the given timeframe"
        )
        if duration_of_timeframe_during_sunlight.total_seconds() == 0:
            return 0

        solar_output_today_in_watt_hours = (
            self._get_debug_solar_output_in_watt_hours()
            if EnvironmentVariableGetter.get(
                name_of_variable="USE_DEBUG_SOLAR_OUTPUT", default_value=False
            )
            else self._get_expected_solar_output_of_today_in_watt_hours()
        )
        self.log.debug(
            f"Expected solar output of today is {solar_output_today_in_watt_hours} Wh"
        )
        solar_output_today_in_watt_seconds = solar_output_today_in_watt_hours * 60 * 60
        average_solar_output_in_watts = (
            solar_output_today_in_watt_seconds / daylight_duration_in_seconds
        )
        self.log.debug(
            f"Average solar output today is {int(average_solar_output_in_watts)} W"
        )

        power_generation_during_sunlight_and_timeframe_in_watt_seconds = (
            average_solar_output_in_watts
            * duration_of_timeframe_during_sunlight.total_seconds()
        )
        power_generation_during_sunlight_and_timeframe_in_watt_hours = int(
            power_generation_during_sunlight_and_timeframe_in_watt_seconds / (60 * 60)
        )
        return power_generation_during_sunlight_and_timeframe_in_watt_hours

    @staticmethod
    def _calculate_overlap_between_time_frames(
        start_timestamp_1: datetime,
        end_timestamp_1: datetime,
        start_timestamp_2: datetime,
        end_timestamp_2: datetime,
    ) -> timedelta:
        overlap_start = max(start_timestamp_1, start_timestamp_2)
        overlap_end = min(end_timestamp_1, end_timestamp_2)

        if overlap_start < overlap_end:
            return overlap_end - overlap_start
        else:
            return timedelta(seconds=0)

    def _get_sunset_and_sunrise_with_offset(self) -> tuple[datetime, datetime]:
        sun = Sun(
            float(EnvironmentVariableGetter.get("LOCATION_LATITUDE")),
            float(EnvironmentVariableGetter.get("LOCATION_LONGITUDE")),
        )

        sunrise = sun.get_sunrise_time(time_zone=self.timezone)
        sunset = sun.get_sunset_time(
            at_date=datetime.datetime.now() + timedelta(days=1), time_zone=self.timezone
        )
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
