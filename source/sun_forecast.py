import datetime
import os

import requests
from dotenv import load_dotenv

load_dotenv()

FORECAST_API_BASE_URL = "https://api.forecast.solar/estimate"

LOCATION_LATITUDE = os.environ.get("LOCATION_LATITUDE")
LOCATION_LONGITUDE = os.environ.get("LOCATION_LONGITUDE")
LOCATION_PLANE_DECLINATION = os.environ.get("LOCATION_PLANE_DECLINATION")
LOCATION_PLANE_AZIMUTH = os.environ.get("LOCATION_PLANE_AZIMUTH")
LOCATION_NUMBER_OF_PANELS = os.environ.get("LOCATION_NUMBER_OF_PANELS")
LOCATION_MAXIMUM_OUTPUT_IN_WATTS = os.environ.get("LOCATION_MAXIMUM_OUTPUT_IN_WATTS")

maximum_output_of_all_panels_in_kw = (
    int(LOCATION_NUMBER_OF_PANELS) * int(LOCATION_MAXIMUM_OUTPUT_IN_WATTS) / 1000
)

url = f"{FORECAST_API_BASE_URL}/{LOCATION_LATITUDE}/{LOCATION_LONGITUDE}/{LOCATION_PLANE_DECLINATION}/{LOCATION_PLANE_AZIMUTH}/{maximum_output_of_all_panels_in_kw}"


def _get_date_as_string() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")


def get_solar_output_in_watt_hours() -> int:
    response = requests.get(url, timeout=5)

    if response.status_code == 200:
        data = response.json()
        return data["result"]["watt_hours_day"][_get_date_as_string()]
    else:
        raise ValueError(
            f"There was a problem with getting the solar forecast: {response.content} (Code: {response.status_code})"
        )
