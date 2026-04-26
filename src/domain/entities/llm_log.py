from typing import Any
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class LlmLog:
    symbol: str
    context: dict[str, Any]
    response: dict[str, Any]
    id: str = ""
    tool_called: str | None = None
    process: str = ""
    position_id: str | None = None
    created_at: datetime | None = None
