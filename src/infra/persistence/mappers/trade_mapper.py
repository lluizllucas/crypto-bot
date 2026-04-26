from src.domain.entities.trade import Trade
from src.infra.persistence.entities.trade_entity import TradeEntity


class TradeMapper:
    @staticmethod
    def to_domain(orm: TradeEntity) -> Trade:
        return Trade(
            id=orm.id,
            symbol=orm.symbol,
            action=orm.action,
            confidence=orm.confidence,
            entry_price=orm.entry_price,
            exit_price=orm.exit_price,
            qty=orm.qty,
            sl=orm.sl,
            tp=orm.tp,
            pnl=orm.pnl,
            reason=orm.reason,
            llm_log_id=orm.llm_log_id,
            exit_llm_log_id=orm.exit_llm_log_id,
            created_at=orm.created_at,
        )

    @staticmethod
    def to_persistence(
        symbol: str,
        action: str,
        confidence: float,
        entry_price: float,
        exit_price: float,
        qty: float,
        sl: float,
        tp: float,
        pnl: float,
        reason: str,
        llm_log_id: str | None = None,
        exit_llm_log_id: str | None = None,
    ) -> TradeEntity:
        return TradeEntity(
            symbol=symbol,
            action=action,
            confidence=confidence,
            entry_price=entry_price,
            exit_price=exit_price,
            qty=qty,
            sl=sl,
            tp=tp,
            pnl=pnl,
            reason=reason,
            llm_log_id=llm_log_id,
            exit_llm_log_id=exit_llm_log_id,
        )
