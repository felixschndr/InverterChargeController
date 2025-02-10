from datetime import date, datetime, timedelta

from dateutil.tz import tz, tzfile


class TimeHandler:
    @staticmethod
    def calculate_overlap_between_time_frames(
        timestamp_start_1: datetime,
        timestamp_end_1: datetime,
        timestamp_start_2: datetime,
        timestamp_end_2: datetime,
    ) -> timedelta:
        """
        Calculate the overlapping duration between two time frames.

        Args:
            timestamp_start_1: Start of the first time frame.
            timestamp_end_1: End of the first time frame.
            timestamp_start_2: Start of the second time frame.
            timestamp_end_2: End of the second time frame.

        Returns:
            A timedelta object representing the duration of the overlap between the two time frames.
            If there is no overlap, returns a timedelta of zero seconds.
        """
        overlap_start = max(timestamp_start_1, timestamp_start_2)
        overlap_end = min(timestamp_end_1, timestamp_end_2)

        if overlap_start < overlap_end:
            return overlap_end - overlap_start
        else:
            return timedelta(seconds=0)

    @staticmethod
    def get_timezone() -> tzfile:
        return tz.gettz()

    @staticmethod
    def get_time(sanitize_seconds: bool = False) -> datetime:
        timestamp = datetime.now(tz=(TimeHandler.get_timezone())).replace(microsecond=0)
        if not sanitize_seconds:
            return timestamp
        else:
            return timestamp.replace(second=0)

    @staticmethod
    def get_date() -> date:
        return TimeHandler.get_time().date()

    @staticmethod
    def get_date_as_string() -> str:
        return TimeHandler.get_date().strftime("%Y-%m-%d")
