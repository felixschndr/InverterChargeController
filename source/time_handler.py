from datetime import date, datetime

from dateutil.tz import tz, tzfile


class TimeHandler:
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

    @staticmethod
    def floor_to_quarter(timestamp: datetime) -> datetime:
        minutes = (timestamp.minute // 15) * 15
        return timestamp.replace(minute=minutes, second=0, microsecond=0)
