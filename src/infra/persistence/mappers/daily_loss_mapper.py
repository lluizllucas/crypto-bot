from src.domain.entities.daily_loss import DailyLoss
from src.infra.persistence.entities.daily_loss_entity import DailyLossEntity


class DailyLossMapper:
    @staticmethod
    def to_domain(orm: DailyLossEntity) -> DailyLoss:
        return DailyLoss(
            date=orm.date,
            loss=float(orm.loss),
            updated_at=orm.updated_at,
        )

    @staticmethod
    def to_persistence(date: str, loss: float) -> DailyLossEntity:
        return DailyLossEntity(date=date, loss=loss)
