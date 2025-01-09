import dataclasses

from environment_variable_getter import EnvironmentVariableGetter
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from logger import LoggerMixin
from urllib3.exceptions import NewConnectionError


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

    def write_to_database(self, fields_to_insert: InfluxDBField | list[InfluxDBField]) -> None:
        point = Point(self.measurement)
        if type(fields_to_insert) is not list:
            fields_to_insert = [fields_to_insert]
        for field_to_insert in fields_to_insert:
            point = point.field(field_to_insert.name, field_to_insert.value)

        self.log.trace(f"Writing to database: {point}")
        try:
            self.write_api.write(bucket=self.bucket, record=point)
        except NewConnectionError as e:
            self.log.warning(f"Connection to database failed (ignoring): {str(e)}")

    def close_connection(self) -> None:
        self.write_api.close()
