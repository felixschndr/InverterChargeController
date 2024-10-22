from datetime import datetime, timedelta


class TimeHandler:
    @staticmethod
    def calculate_overlap_between_time_frames(
        start_timestamp_1: datetime,
        end_timestamp_1: datetime,
        start_timestamp_2: datetime,
        end_timestamp_2: datetime,
    ) -> timedelta:
        overlap_start = max(start_timestamp_1, start_timestamp_2)
        overlap_end = min(end_timestamp_1, end_timestamp_2)

        if overlap_start < overlap_end:
            return overlap_end - overlap_start
        else:
            return timedelta(seconds=0)
