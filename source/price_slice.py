from dataclasses import dataclass
from datetime import datetime


@dataclass
class PriceSlice:
    rate: float
    timestamp: datetime

    def __repr__(self):
        return f"{self.rate} € at {self.timestamp.strftime('%H:%M')}"
