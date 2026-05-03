import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Double, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.infra.persistence.entities.base import Base


class OpenPositionEntity(Base):
    __tablename__ = "open_positions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    entry_price: Mapped[float] = mapped_column(Double, nullable=False)
    qty: Mapped[float] = mapped_column(Double, nullable=False)
    sl: Mapped[float] = mapped_column(Double, nullable=False)
    tp: Mapped[float] = mapped_column(Double, nullable=False)
    original_sl: Mapped[float | None] = mapped_column(Double, nullable=True)
    original_tp: Mapped[float | None] = mapped_column(Double, nullable=True)
    tp_hold_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    llm_log_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
