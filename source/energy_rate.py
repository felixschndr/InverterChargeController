from dataclasses import dataclass
from datetime import datetime


@dataclass
class EnergyRate:
    rate: float
    timestamp: datetime

    def __repr__(self):
        return f"{self.rate} € at {self.timestamp}"


@dataclass
class ConsecutiveEnergyRates:
    energy_rates: list[EnergyRate]

    def __len__(self):
        return len(self.energy_rates)

    def __getitem__(self, index: int):
        return self.energy_rates[index]

    def __str__(self):
        return str(self.energy_rates)
