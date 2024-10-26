import signal
import sys
from types import FrameType

from dateutil.tz import tz
from environment_variable_getter import EnvironmentVariableGetter
from inverter_charge_controller import InverterChargeController
from logger import LoggerMixin
from sun_forecast_handler import SunForecastHandler


def log_solar_forecast(log_as_review: bool = False) -> None:
    sun_forecast_handler = SunForecastHandler(tz.gettz(EnvironmentVariableGetter.get("TIMEZONE")))

    solar_output_today = sun_forecast_handler.get_expected_solar_output_of_today()
    if log_as_review:
        sun_forecast_handler.log.info(f"The actual solar output of today was {solar_output_today}")
    else:
        sun_forecast_handler.log.info(f"The expected solar output of today is {solar_output_today}")


def handle_stop_signal(signal_number: int, _frame: FrameType) -> None:
    logger = LoggerMixin()
    logger.log.info(f"Received {signal.Signals(signal_number).name}. Exiting now...")
    exit(0)


for signal_to_catch in [signal.SIGINT, signal.SIGTERM]:
    signal.signal(signal_to_catch, handle_stop_signal)

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
    inverter_charge_controller.start()
