from dataclasses import dataclass
from datetime import datetime


@dataclass
class EnergyRate:
    rate: float
    timestamp: datetime

    def __repr__(self):
        return f"{self.rate} € at {self.timestamp.strftime('%H:%M')}"


@dataclass
class ConsecutiveEnergyRates:
    slices: list[EnergyRate]

    def __len__(self):
        return len(self.slices)

    def __getitem__(self, index: int):
        return self.slices[index]
