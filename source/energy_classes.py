from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from environment_variable_getter import EnvironmentVariableGetter


@dataclass
class EnergyAmount:
    watt_hours: float

    def __str__(self):
        return f"{int(self.watt_hours)} Wh"

    def __repr__(self):
        return self.__str__()

    def __add__(self, other: EnergyAmount | int | float) -> EnergyAmount | None:
        if isinstance(other, EnergyAmount):
            return EnergyAmount(self.watt_hours + other.watt_hours)
        if isinstance(other, int) or isinstance(other, float):
            return EnergyAmount(self.watt_hours + other)
        self._raise_type_error("+", other)

    def __sub__(self, other: EnergyAmount | int | float) -> EnergyAmount | None:
        if isinstance(other, EnergyAmount):
            return EnergyAmount(self.watt_hours - other.watt_hours)
        if isinstance(other, int) or isinstance(other, float):
            return EnergyAmount(self.watt_hours - other)
        self._raise_type_error("-", other)

    def __mul__(self, other: EnergyAmount | int | float) -> EnergyAmount | None:
        if isinstance(other, EnergyAmount):
            return EnergyAmount(self.watt_hours * other.watt_hours)
        if isinstance(other, int) or isinstance(other, float):
            return EnergyAmount(self.watt_hours * other)
        self._raise_type_error("*", other)

    def __lt__(self, other: EnergyAmount | int | float) -> bool | None:
        if isinstance(other, EnergyAmount):
            return self.watt_hours < other.watt_hours
        if isinstance(other, int) or isinstance(other, float):
            return self.watt_hours < other
        self._raise_type_error("<", other)

    def __gt__(self, other: EnergyAmount | int | float) -> bool | None:
        if isinstance(other, EnergyAmount):
            return self.watt_hours > other.watt_hours
        if isinstance(other, int) or isinstance(other, float):
            return self.watt_hours > other
        self._raise_type_error(">", other)

    def __ge__(self, other: EnergyAmount | int | float) -> bool | None:
        if isinstance(other, EnergyAmount):
            return self.watt_hours >= other.watt_hours
        if isinstance(other, int) or isinstance(other, float):
            return self.watt_hours >= other
        self._raise_type_error(">=", other)

    def _raise_type_error(self, operation: str, other: object) -> None:
        raise TypeError(
            f"unsupported operand type(s) for {operation}: '{self.__class__.__name__}' and '{type(other)}'"
        )

    @property
    def watt_seconds(self) -> float:
        return self.watt_hours * 60 * 60

    @staticmethod
    def from_watt_seconds(watt_seconds: float) -> EnergyAmount:
        return EnergyAmount(watt_hours=watt_seconds / (60 * 60))

    @staticmethod
    def from_kilo_watt_hours(kilo_watt_hours: float) -> EnergyAmount:
        return EnergyAmount(watt_hours=kilo_watt_hours * 1000)


@dataclass
class Power:
    watts: float

    def __str__(self):
        return f"{int(self.watts)} W"

    @staticmethod
    def from_kilo_watts(kilo_watts: float) -> Power:
        return Power(watts=kilo_watts * 1000)


@dataclass
class EnergyRate:
    rate: float
    timestamp: datetime
    maximum_charging_duration: timedelta = timedelta(hours=1)
    has_to_be_rechecked: bool = False

    def __repr__(self):
        return f"{self.rate} ct/kWh at {self.timestamp}"

    def __lt__(self, other: EnergyRate) -> bool:
        return self.rate < other.rate

    def __gt__(self, other: EnergyRate) -> bool:
        return self.rate > other.rate

    def format_maximum_charging_duration(self) -> str:
        charging_duration_in_hours = int(self.maximum_charging_duration.total_seconds() // 3600)
        if charging_duration_in_hours == 1:
            return "1 hour"
        return f"{charging_duration_in_hours} hours"


battery_capacity = EnergyAmount(int(EnvironmentVariableGetter.get("INVERTER_BATTERY_CAPACITY")))


@dataclass
class StateOfCharge:
    absolute: EnergyAmount

    def __repr__(self):
        return f"{self.in_percentage:.2f} % ({self.absolute})"

    def __add__(self, other: StateOfCharge) -> StateOfCharge:
        return StateOfCharge(self.absolute + other.absolute)

    def __sub__(self, other: StateOfCharge) -> StateOfCharge:
        return StateOfCharge(self.absolute - other.absolute)

    def __lt__(self, other: StateOfCharge) -> bool:
        return self.absolute < other.absolute

    def __gt__(self, other: StateOfCharge) -> bool:
        return self.absolute > other.absolute

    def __ge__(self, other: StateOfCharge) -> bool:
        return self.absolute >= other.absolute

    @property
    def in_percentage(self) -> int:
        return int(self.absolute.watt_hours / battery_capacity.watt_hours * 100)

    @staticmethod
    def from_percentage(percentage: float) -> StateOfCharge:
        return StateOfCharge(absolute=EnergyAmount(battery_capacity.watt_hours * percentage / 100))
