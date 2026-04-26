import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from src.infra.persistence.entities.base import Base


class LlmLogEntity(Base):
    __tablename__ = "llm_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    context: Mapped[dict] = mapped_column(JSON, nullable=False)
    response: Mapped[dict] = mapped_column(JSON, nullable=False)
    tool_called: Mapped[str | None] = mapped_column(String, nullable=True)
    process: Mapped[str | None] = mapped_column(Text, nullable=True, server_default=text("''"))
    position_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
