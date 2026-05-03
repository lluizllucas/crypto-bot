from datetime import datetime, timezone

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infra.persistence.entities.base import Base


class DailyLossEntity(Base):
    __tablename__ = "daily_loss"

    date: Mapped[str] = mapped_column(String, primary_key=True)
    loss: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=lambda: datetime.now(timezone.utc),
    )
