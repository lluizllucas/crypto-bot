import logging

from sqlalchemy.orm import Session

from src.domain.entities.trade import Trade
from src.infra.persistence.entities.trade_entity import TradeEntity
from src.infra.persistence.mappers.trade_mapper import TradeMapper

log = logging.getLogger(__name__)

_CLOSED_ACTIONS = ["STOP-LOSS", "TAKE-PROFIT", "SELL", "EARLY-EXIT"]


class TradesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_since(self, since_iso: str) -> list[Trade]:
        try:
            rows = (
                self._session.query(TradeEntity)
                .filter(
                    TradeEntity.action.in_(_CLOSED_ACTIONS),
                    TradeEntity.created_at >= since_iso,
                )
                .order_by(TradeEntity.created_at)
                .all()
            )
            return [TradeMapper.to_domain(r) for r in rows]
        except Exception as e:
            log.error(f"Erro ao buscar trades desde {since_iso}: {e}")
            return []

    def save(
        self,
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
    ) -> None:
        try:
            entity = TradeMapper.to_persistence(
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
            self._session.add(entity)
            self._session.commit()
        except Exception as e:
            self._session.rollback()
            log.error(f"Erro ao salvar trade no banco ({symbol}): {e}")

    def get_recent_performance(self, symbol: str, limit: int = 10) -> dict:
        try:
            rows = (
                self._session.query(TradeEntity)
                .filter(
                    TradeEntity.symbol == symbol,
                    TradeEntity.action.in_(_CLOSED_ACTIONS),
                )
                .order_by(TradeEntity.created_at.desc())
                .limit(limit)
                .all()
            )
            if not rows:
                return {"trades": 0}

            pnls   = [r.pnl for r in rows]
            wins   = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p <= 0]

            return {
                "trades":    len(rows),
                "wins":      len(wins),
                "losses":    len(losses),
                "win_rate":  round(len(wins) / len(rows) * 100, 1),
                "pnl_total": round(sum(pnls), 4),
                "pnl_avg":   round(sum(pnls) / len(pnls), 4),
                "best":      round(max(pnls), 4),
                "worst":     round(min(pnls), 4),
            }
        except Exception as e:
            log.error(f"Erro ao buscar performance recente ({symbol}): {e}")
            return {"trades": 0}
