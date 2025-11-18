import dataclasses
from datetime import datetime
from typing import Optional

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.flux_table import FluxRecord
from influxdb_client.client.write_api import SYNCHRONOUS
from urllib3.exceptions import NewConnectionError

from source.environment_variable_getter import EnvironmentVariableGetter
from source.logger import LoggerMixin
from source.time_handler import TimeHandler


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
        self.query_api = client.query_api()

    def write_to_database(self, fields_to_insert: InfluxDBField | list[InfluxDBField]) -> None:
        point = Point(self.measurement)
        if type(fields_to_insert) is not list:
            fields_to_insert = [fields_to_insert]
        for field_to_insert in fields_to_insert:
            point = point.field(field_to_insert.name, field_to_insert.value)

        self.log.trace(f"Writing to the database: {point}")
        try:
            self.write_api.write(bucket=self.bucket, record=point)
        except NewConnectionError:
            self.log.warning("Connection to database failed (ignoring)", exc_info=True)

    def get_newest_value_of_measurement(self, field_to_sort_by: str) -> Optional[datetime]:
        """
        Gets the newest value of the specified measurement by sorting based on a given field and processes the query
        result to return the corresponding timestamp. If no results are found, it returns the epoch timestamp.

        Args:
            field_to_sort_by (str): The field name to sort the measurement data by.

        Returns:
            datetime: The timestamp of the newest measurement value, or the epoch timestamp if no results are found.
        """
        self.log.trace(f"Getting newest value of measurement {self.measurement}")
        query = f"""
        from(bucket: "{self.bucket}")
        |> range(start: 0)
        |> filter(fn: (r) => r._measurement == "{self.measurement}")
        |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
        |> sort(columns: ["{field_to_sort_by}"], desc: true)
        |> limit(n: 1)
        """
        try:
            result = self.query_api.query(query)
        except NewConnectionError:
            self.log.warning("Connection to database failed (ignoring)", exc_info=True)
            return None

        if len(result) == 0:
            return datetime.fromtimestamp(0, tz=TimeHandler.get_timezone())

        return datetime.fromisoformat(result[0].records[0].values[field_to_sort_by])

    def get_values_since(self, since_datetime: datetime, column_name: str) -> list[FluxRecord]:
        """
        Gets all values from the measurement where the specified column has a value greater than the given datetime.

        Args:
            since_datetime (datetime): The datetime to filter values by.
            column_name (str): The column name to compare with the datetime.

        Returns:
            list: A list of records where the specified column value is greater than the given datetime.
                 Returns an empty list if no results are found or if there's a connection error.
        """
        self.log.trace(f"Getting values from {self.measurement} since {since_datetime} for column {column_name}")
        query = f"""
        from(bucket: "{self.bucket}")
        |> range(start: 0)
        |> filter(fn: (r) => r._measurement == "{self.measurement}")
        |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
        |> filter(fn: (r) => r["{column_name}"] > "{since_datetime.isoformat()}")
        """

        try:
            result = self.query_api.query(query)
        except NewConnectionError:
            self.log.warning("Connection to database failed (ignoring)", exc_info=True)
            return []

        if len(result) == 0:
            return []

        return list(result[0].records)
