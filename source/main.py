from goodwe import OperationMode

from source.inverter import Inverter
from source.logger import LoggerMixin
from source.sems_portal_api_handler import SemsPortalApiHandler
from source.sun_forecast_api_handler import SunForecastAPIHandler


class Main(LoggerMixin):
    def __init__(self, dry_run: bool = True):
        """
        :param dry_run: If True, the operation will be simulated and no changes to the operation mode of the inverter will be made. Defaults to True.
        """
        super().__init__()

        self.dry_run = dry_run

    def run(self) -> None:
        sems_portal_api_handler = SemsPortalApiHandler()
        sems_portal_api_handler.login()
        average_power_consumption = (
            sems_portal_api_handler.get_average_power_consumption_per_day()
        )
        self.log.info(
            f"The expected power consumption for tomorrow is {average_power_consumption:.2f} Wh"
        )

        sun_forecast_api_handler = SunForecastAPIHandler()
        # solar_output_tomorrow = sun_forecast.get_solar_output_in_watt_hours()
        solar_output_tomorrow = sun_forecast_api_handler._get_debug_solar_output_in_watt_hours()
        self.log.info(
            f"The expected solar output for tomorrow is {solar_output_tomorrow:.2f} Wh"
        )

        inverter = Inverter()
        if solar_output_tomorrow > average_power_consumption:
            self.log.info("The expected solar output is greater than the expected power consumption. Setting the inverter to normal operation mode.")
            if self.dry_run:
                self.log.info("Would set the inverter to mode GENERAL, but dry run is enabled.")
            else:
                inverter.set_operation_mode(OperationMode.GENERAL)
        else:
            self.log.info(
                "The expected solar output is less than the expected power consumption. We need to charge...")
            if self.dry_run:
                self.log.info("Would charge the inverter, but dry run is enabled.")
            else:
                pass  # TODO: Build the logic when to charge




if __name__ == "__main__":
    main = Main()
    main.run()
