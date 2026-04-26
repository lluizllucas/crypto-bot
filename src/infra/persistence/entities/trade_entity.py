import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Double, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from src.infra.persistence.entities.base import Base


class TradeEntity(Base):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Double, nullable=False, server_default=text("0"))
    entry_price: Mapped[float] = mapped_column(Double, nullable=False, server_default=text("0"))
    exit_price: Mapped[float] = mapped_column(Double, nullable=False, server_default=text("0"))
    qty: Mapped[float] = mapped_column(Double, nullable=False, server_default=text("0"))
    sl: Mapped[float] = mapped_column(Double, nullable=False, server_default=text("0"))
    tp: Mapped[float] = mapped_column(Double, nullable=False, server_default=text("0"))
    pnl: Mapped[float] = mapped_column(Double, nullable=False, server_default=text("0"))
    reason: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    llm_log_id: Mapped[str | None] = mapped_column(String, nullable=True)
    exit_llm_log_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
