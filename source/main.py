import signal
import sys
from types import FrameType

from deprecated_sun_forecast_handler import DeprecatedSunForecastHandler
from inverter_charge_controller import InverterChargeController
from logger import LoggerMixin


def log_solar_forecast(log_as_review: bool = False) -> None:
    deprecated_sun_forecast_handler = DeprecatedSunForecastHandler()

    solar_output_today = deprecated_sun_forecast_handler.get_expected_solar_output_of_today()
    if log_as_review:
        deprecated_sun_forecast_handler.log.info(f"The actual solar output of today was {solar_output_today}")
    else:
        deprecated_sun_forecast_handler.log.info(f"The expected solar output of today is {solar_output_today}")


def handle_stop_signal(signal_number: int, _frame: FrameType) -> None:
    """
    Logs the signals SIGINT and SIGTERM and then exits.

    Args:
        signal_number: The number representing the signal received.
        _frame: The current stack frame when the signal was received.
    """
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
