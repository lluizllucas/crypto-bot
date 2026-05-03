import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.infra.persistence.entities.daily_loss_entity import DailyLossEntity
from src.infra.persistence.mappers.daily_loss_mapper import DailyLossMapper

log = logging.getLogger(__name__)


class DailyLossRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, date_str: str) -> float:
        try:
            row = self._session.query(DailyLossEntity).filter_by(date=date_str).first()
            return float(row.loss) if row else 0.0
        except Exception as e:
            log.error(f"Erro ao buscar daily_loss ({date_str}): {e}")
            return 0.0

    def upsert(self, date_str: str, loss: float) -> None:
        try:
            row = self._session.query(DailyLossEntity).filter_by(date=date_str).first()
            if row:
                row.loss = loss
                row.updated_at = datetime.now(timezone.utc)
            else:
                self._session.add(DailyLossMapper.to_persistence(date_str, loss))
            self._session.commit()
        except Exception as e:
            self._session.rollback()
            log.error(f"Erro ao salvar daily_loss ({date_str}): {e}")
