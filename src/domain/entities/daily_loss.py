from datetime import datetime
from dataclasses import dataclass


@dataclass
class DailyLoss:
    date: str
    loss: float
    updated_at: datetime | None = None
