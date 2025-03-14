from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from environment_variable_getter import EnvironmentVariableGetter
from logger import LoggerMixin


@dataclass
class EnergyAmount:
    watt_hours: float

    def __repr__(self):
        return f"{int(self.watt_hours)} Wh"

    def __add__(self, other: EnergyAmount) -> EnergyAmount:
        return EnergyAmount(self.watt_hours + other.watt_hours)

    def __sub__(self, other: EnergyAmount) -> EnergyAmount:
        return EnergyAmount(self.watt_hours - other.watt_hours)

    def __mul__(self, other: float) -> EnergyAmount:
        return EnergyAmount(self.watt_hours * other)

    def __lt__(self, other: EnergyAmount) -> bool:
        return self.watt_hours < other.watt_hours

    def __le__(self, other: EnergyAmount) -> bool:
        return self.watt_hours <= other.watt_hours

    def __gt__(self, other: EnergyAmount) -> bool:
        return self.watt_hours > other.watt_hours

    def __ge__(self, other: EnergyAmount) -> bool:
        return self.watt_hours >= other.watt_hours

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

    def __iadd__(self, other: Power) -> Power:
        return Power(self.watts + other.watts)

    @staticmethod
    def from_kilo_watts(kilo_watts: float) -> Power:
        return Power(watts=kilo_watts * 1000)


@dataclass
class EnergyRate:
    rate: float
    timestamp: datetime
    has_to_be_rechecked: bool = False

    def __repr__(self):
        return f"{self.rate} ct/kWh at {self.timestamp}"

    def __lt__(self, other: EnergyRate) -> bool:
        return self.rate < other.rate

    def __le__(self, other: EnergyRate) -> bool:
        return self.rate <= other.rate

    def __gt__(self, other: EnergyRate) -> bool:
        return self.rate > other.rate

    def __ge__(self, other: EnergyRate) -> bool:
        return self.rate >= other.rate


soc_logger = LoggerMixin("StateOfCharge")
battery_capacity = EnergyAmount(int(EnvironmentVariableGetter.get("INVERTER_BATTERY_CAPACITY")))


@dataclass
class StateOfCharge:
    absolute: EnergyAmount

    def __repr__(self):
        return f"{self.in_percentage} % ({self.absolute})"

    def __post_init__(self):
        if self.absolute.watt_hours > battery_capacity.watt_hours:
            soc_logger.log.debug(f"Capping the state of charge at the battery capacity (would be {self.absolute})")
            self.absolute = EnergyAmount(battery_capacity.watt_hours)

        if self.absolute.watt_hours < 0:
            soc_logger.log.debug(f"Capping the state of charge at 0 (would be {self.absolute})")
            self.absolute = EnergyAmount(0)

    def __add__(self, other: StateOfCharge) -> StateOfCharge:
        return StateOfCharge(self.absolute + other.absolute)

    def __sub__(self, other: StateOfCharge) -> StateOfCharge:
        return StateOfCharge(self.absolute - other.absolute)

    def __lt__(self, other: StateOfCharge) -> bool:
        return self.absolute < other.absolute

    def __le__(self, other: StateOfCharge) -> bool:
        return self.absolute <= other.absolute

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
