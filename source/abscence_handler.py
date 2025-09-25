from datetime import datetime

from source.environment_variable_getter import EnvironmentVariableGetter
from source.logger import LoggerMixin
from source.time_handler import TimeHandler


class AbsenceHandler(LoggerMixin):
    DELIMITER = ";"

    def __init__(self):
        super().__init__()

    def check_for_current_absence(self) -> bool:
        absence_input = ""
        try:
            absence_input = EnvironmentVariableGetter.get("ABSENCE_TIMEFRAME", "")
            return self._check_for_current_absence(absence_input)
        except ValueError:
            self.log.error(
                f'Improperly configured: "{absence_input}" is not a valid configuration! '
                "Read the README for instructions.",
                exc_info=True,
            )
            return False

    def _check_for_current_absence(self, absence_input: str) -> bool:
        if not absence_input:
            self.log.debug("Absence input is empty")
            return False
        if absence_input.count(self.DELIMITER) != 1:
            raise ValueError(f'The amount of "{self.DELIMITER}" in the input MUST be 1')

        self.log.trace(f'Raw input is "{absence_input}"')
        absence_start_raw, absence_end_raw = absence_input.replace(" ", "").split(self.DELIMITER)
        absence_start = datetime.fromisoformat(absence_start_raw)
        absence_end = datetime.fromisoformat(absence_end_raw)
        self.log.debug(f"Absence start is {absence_start}, absence end is {absence_end}")

        for timestamp in [absence_start, absence_end]:
            if timestamp.tzinfo is None:
                raise ValueError(f'"{absence_start_raw}" has no timezone information')

        if absence_start < TimeHandler.get_time() < absence_end:
            return True

        return absence_start < TimeHandler.get_time() < absence_end
