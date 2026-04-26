from src.domain.entities.position import Position
from src.infra.persistence.entities.open_position_entity import OpenPositionEntity


class OpenPositionMapper:
    @staticmethod
    def to_domain(orm: OpenPositionEntity) -> Position:
        return Position(
            entry_price=orm.entry_price,
            qty=orm.qty,
            sl=orm.sl,
            tp=orm.tp,
            ts=orm.created_at,
            db_id=orm.id,
            llm_log_id=orm.llm_log_id or "",
            original_sl=orm.original_sl or orm.sl,
            original_tp=orm.original_tp or orm.tp,
            tp_hold_count=orm.tp_hold_count or 0,
        )

    @staticmethod
    def to_persistence(symbol: str, domain: Position) -> OpenPositionEntity:
        entity = OpenPositionEntity(
            symbol=symbol,
            entry_price=domain.entry_price,
            qty=domain.qty,
            sl=domain.sl,
            tp=domain.tp,
            original_sl=domain.original_sl,
            original_tp=domain.original_tp,
            tp_hold_count=domain.tp_hold_count,
            llm_log_id=domain.llm_log_id or None,
        )

        if domain.db_id:
            entity.id = domain.db_id
            
        return entity
