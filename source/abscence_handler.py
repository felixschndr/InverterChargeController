from datetime import datetime
from typing import Optional

from source.environment_variable_getter import EnvironmentVariableGetter
from source.logger import LoggerMixin
from source.time_handler import TimeHandler


class AbsenceHandler(LoggerMixin):
    DELIMITER = ";"

    def __init__(self):
        super().__init__()

        self.absence_input = EnvironmentVariableGetter.get("ABSENCE_TIMEFRAME", "")
        try:
            self.absence_start, self.absence_end = self._parse_absence_input(self.absence_input)
        except ValueError as e:
            self.log.error(
                f'Improperly configured: "{self.absence_input}" is not a valid configuration! '
                "Read the README for instructions.",
                exc_info=True,
            )
            raise e

    def currently_is_an_absence(self) -> bool:
        if not self.absence_start:
            return False
        return self.absence_start < TimeHandler.get_time() < self.absence_end

    def _parse_absence_input(self, absence_input: str) -> Optional[tuple[datetime, datetime]]:
        if not absence_input:
            self.log.debug("Absence input is empty")
            return None
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

        return absence_start, absence_end
