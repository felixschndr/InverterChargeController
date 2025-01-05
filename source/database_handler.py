import dataclasses
from datetime import datetime

from environment_variable_getter import EnvironmentVariableGetter
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from logger import LoggerMixin
from time_handler import TimeHandler


@dataclasses.dataclass
class InfluxDBComponent:  # TODO: Find better name
    name: str
    value: float | str


@dataclasses.dataclass
class InfluxDBField(InfluxDBComponent):
    pass


@dataclasses.dataclass
class InfluxDBTag(InfluxDBComponent):
    pass


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
        self, field_to_insert: InfluxDBField, tags: list[InfluxDBTag] = None, timestamp: datetime = None
    ) -> None:
        if timestamp is not None and timestamp.tzinfo is None:
            self.log.warning(f"Timestamp {timestamp} has no timezone information, adding it")
            timestamp = timestamp.replace(tzinfo=TimeHandler.get_timezone())
        if timestamp is None:
            timestamp = datetime.now(tz=TimeHandler.get_timezone())

        point = Point(self.measurement).field(field_to_insert.name, field_to_insert.value)
        if tags is not None:
            for tag in tags:
                point = point.tag(tag.name, tag.value)
        point = point.time(timestamp)

        self.log.trace(f"Writing to database: {point}")
        self.write_api.write(bucket=self.bucket, record=point)

    def close_connection(self) -> None:
        self.write_api.close()
