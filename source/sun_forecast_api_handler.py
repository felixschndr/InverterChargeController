import datetime

import requests
from environment_variable_getter import EnvironmentVariableGetter
from logger import LoggerMixin


class SunForecastAPIHandler(LoggerMixin):
    def __init__(self):
        super().__init__()

        self.url = self._get_url()

    def _get_url(self) -> str:
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
        self.log.debug(f'Set API URL to "{url}"')

        return url

    @staticmethod
    def _get_date_as_string() -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d")

    def get_solar_output_in_watt_hours(self) -> int:
        self.log.debug("Getting estimated solar output of today")

        response = requests.get(self.url, timeout=5)
        response.raise_for_status()

        data = response.json()
        self.log.debug(f"Retrieved data: {data}")
        return data["result"]["watt_hours_day"][self._get_date_as_string()]

    def _get_debug_solar_output_in_watt_hours(self) -> int:
        # We use a sample value for debugging the code since the API offers very limited call per day
        self.log.debug("Getting debug estimated solar output of today")
        return 23000
