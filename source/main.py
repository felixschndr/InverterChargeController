import asyncio
import sys

from inverter_charge_controller import InverterChargeController
from sun_forecast_api_handler import SunForecastAPIHandler


def log_solar_forecast(log_as_review: bool = False) -> None:
    sun_forecast_api_handler = SunForecastAPIHandler()

    solar_output_today = sun_forecast_api_handler.get_solar_output_in_watt_hours()
    if log_as_review:
        sun_forecast_api_handler.log.info(
            f"The actual solar output of today was {solar_output_today} Wh"
        )
    else:
        sun_forecast_api_handler.log.info(
            f"The expected solar output of today is {solar_output_today} Wh"
        )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--solar-forecast":
            """
            This allows you to simply log today's solar forecast and do nothing else.
            This can also be used to log the solar prediction after the sun has set to see how far off the solar prediction
            from before the sun has risen was. See below.
            """
            log_solar_forecast()
            exit(0)
        if sys.argv[1] == "--solar-review":
            log_solar_forecast(log_as_review=True)
            exit(0)

        raise RuntimeError(f"Unknown argument {sys.argv[1]}!")

    inverter_charge_controller = InverterChargeController()
    asyncio.run(inverter_charge_controller.run())
