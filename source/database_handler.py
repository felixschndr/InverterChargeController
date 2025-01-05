import dataclasses
from datetime import datetime

from environment_variable_getter import EnvironmentVariableGetter
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from logger import LoggerMixin
from time_handler import TimeHandler


@dataclasses.dataclass
class InfluxDBField:
    name: str
    value: float | str


class DatabaseHandler(LoggerMixin):
    def __init__(self, measurement: str):
        super().__init__()

        self.url = "http://localhost:8086"
        self.token = EnvironmentVariableGetter.get("INFLUXDB_TOKEN")
        self.org = "default"
        self.bucket = "default"
        self.measurement = measurement

        client = InfluxDBClient(url=self.url, token=self.token, org=self.org)

        self.write_api = client.write_api(write_options=SYNCHRONOUS)

    def write_to_database(
        self, fields_to_insert: InfluxDBField | list[InfluxDBField], timestamp: datetime = None
    ) -> None:
        if timestamp is not None and timestamp.tzinfo is None:
            self.log.warning(f"Timestamp {timestamp} has no timezone information, adding it")
            timestamp = timestamp.replace(tzinfo=TimeHandler.get_timezone())
        if timestamp is None:
            timestamp = datetime.now(tz=TimeHandler.get_timezone())

        point = Point(self.measurement)
        if type(fields_to_insert) is not list:
            fields_to_insert = [fields_to_insert]
        for field_to_insert in fields_to_insert:
            point = point.field(field_to_insert.name, field_to_insert.value)
        point = point.time(timestamp)
        # point = Point("sun_forecast").field("pv_estimate", 20.52).time(TimeHandler.get_time())

        self.log.trace(f"Writing to database: {point}")
        self.write_api.write(bucket=self.bucket, record=point)

    def close_connection(self) -> None:
        self.write_api.close()
