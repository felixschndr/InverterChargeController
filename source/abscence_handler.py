from datetime import datetime

from dateutil.tz import tzfile
from energy_amount import EnergyAmount, Power
from environment_variable_getter import EnvironmentVariableGetter
from logger import LoggerMixin


class AbsenceHandler(LoggerMixin):
    DELIMITER = ";"

    def __init__(self, timezone: tzfile):
        super().__init__()

        self.timezone = timezone

    def check_for_current_absence(self) -> bool:
        absence_input = ""
        try:
            absence_input = EnvironmentVariableGetter.get("ABSENCE_TIMEFRAME", "")
            return self._check_for_current_absence(absence_input)
        except ValueError as e:
            self.log.warning(
                f'Improperly configured: "{absence_input}" is not a valid configuration: {e}! Read the README for instructions.'
            )
            return False

    def _check_for_current_absence(self, absence_input: str) -> bool:
        if not absence_input:
            self.log.debug("Absence input is empty")
            return False
        if absence_input.count(self.DELIMITER) != 1:
            raise ValueError(f'The amount of "{self.DELIMITER}" MUST be 1')

        self.log.trace(f'Raw input is "{absence_input}"')
        absence_start_raw, absence_end_raw = absence_input.replace(" ", "").split(self.DELIMITER)
        absence_start = datetime.fromisoformat(absence_start_raw)
        absence_end = datetime.fromisoformat(absence_end_raw)
        self.log.debug(f"Absence start is {absence_start}, absence end is {absence_end}")

        for timestamp in [absence_start, absence_end]:
            if timestamp.tzinfo is None:
                raise ValueError(f'"{absence_start_raw}" has no timezone information')

        if absence_start < datetime.now(tz=self.timezone) < absence_end:
            return True

        return False

    def calculate_power_usage_for_absence(self, timestamp_start: datetime, timestamp_end: datetime) -> EnergyAmount:
        absence_power_consumption = Power(float(EnvironmentVariableGetter.get("ABSENCE_POWER_CONSUMPTION", 150)))
        self.log.debug(f"Power consumption during absence is {absence_power_consumption}")
        timeframe = timestamp_end - timestamp_start
        self.log.debug(f"Duration until next minimum is {timeframe}")
        energy_usage = EnergyAmount.from_watt_seconds(absence_power_consumption.watts * timeframe.total_seconds())
        self.log.debug(f"Energy usage during absence is {energy_usage}")
        return energy_usage
