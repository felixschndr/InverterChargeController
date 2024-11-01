from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class EnergyAmount:
    watt_hours: float

    def __str__(self):
        return f"{int(self.watt_hours)} Wh"

    def __repr__(self):
        return self.__str__()

    def __add__(self, other: EnergyAmount | int | float) -> EnergyAmount:
        if isinstance(other, EnergyAmount):
            return EnergyAmount(self.watt_hours + other.watt_hours)
        if isinstance(other, int) or isinstance(other, float):
            return EnergyAmount(self.watt_hours + other)
        self._raise_type_error("+", other)

    def __sub__(self, other: EnergyAmount | int | float) -> EnergyAmount:
        if isinstance(other, EnergyAmount):
            return EnergyAmount(self.watt_hours - other.watt_hours)
        if isinstance(other, int) or isinstance(other, float):
            return EnergyAmount(self.watt_hours - other)
        self._raise_type_error("-", other)

    def __mul__(self, other: EnergyAmount | int | float) -> EnergyAmount:
        if isinstance(other, EnergyAmount):
            return EnergyAmount(self.watt_hours * other.watt_hours)
        if isinstance(other, int) or isinstance(other, float):
            return EnergyAmount(self.watt_hours * other)
        self._raise_type_error("*", other)

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


@dataclass
class EnergyRate:
    rate: float
    timestamp: datetime

    def __repr__(self):
        return f"{self.rate} € at {self.timestamp}"
