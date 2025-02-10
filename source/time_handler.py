from datetime import date, datetime, time, timedelta

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
    def calculate_day_night_duration(
        timestamp_start: datetime, timestamp_end: datetime, day_start: time, night_start: time
    ) -> tuple[timedelta, timedelta]:
        """
        Calculates the total duration of daytime and nighttime within a given timeframe.

        This method divides the timeframe between `timestamp_start` and `timestamp_end` into daytime and nighttime
        based on the provided day and night start times.

        Example:
            timestamp_start=04:00 AM
            timestamp_end=10:00 PM
            day_start=06:00 AM
            night_start=06:00 PM

            duration of daytime = 12 hours
            duration of nighttime = 2 hours + 4 hours = 6 hours

        Args:
            timestamp_start: The starting timestamp of the timeframe to be analyzed.
            timestamp_end: The ending timestamp of the timeframe to be analyzed.
            day_start: The time of day when daytime begins.
            night_start: The time of day when nighttime begins.

        Returns:
            A tuple containing the total duration of daytime and the total duration of nighttime.
        """
        duration_day = timedelta(seconds=0)
        duration_night = timedelta(seconds=0)

        timezone = TimeHandler.get_timezone()

        current_time = timestamp_start

        while current_time < timestamp_end:
            # Calculate day and night start timestamp depending on the current time
            day_start_time = datetime.combine(current_time.date(), day_start, tzinfo=timezone)
            night_start_time = datetime.combine(current_time.date(), night_start, tzinfo=timezone)
            next_day_start_time = day_start_time + timedelta(days=1)

            if current_time < day_start_time or current_time >= night_start_time:
                # Duration of the night
                if current_time < day_start_time:
                    night_end = min(day_start_time, timestamp_end)
                else:
                    night_end = min(next_day_start_time, timestamp_end)
                slot_duration = night_end - current_time
                duration_night += slot_duration
                current_time = night_end

            else:
                # Duration of the day
                day_end = min(night_start_time, timestamp_end)
                slot_duration = day_end - current_time
                duration_day += slot_duration
                current_time = day_end

        return duration_day, duration_night

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
