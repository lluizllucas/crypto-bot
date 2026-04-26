from datetime import datetime
from dataclasses import dataclass


@dataclass
class Trade:
    symbol: str
    action: str
    confidence: float
    entry_price: float
    exit_price: float
    qty: float
    sl: float
    tp: float
    pnl: float
    reason: str
    id: str = ""
    llm_log_id: str | None = None
    exit_llm_log_id: str | None = None
    created_at: datetime | None = None
