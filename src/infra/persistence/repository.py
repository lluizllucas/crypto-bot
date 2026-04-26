"""
Fachada de persistência — mantém as assinaturas originais e delega
para os repositories SQLAlchemy. Todo o código existente continua
funcionando sem alterações.
"""

import logging

from src.domain.entities.position import Position
from src.domain.entities.trade import Trade
from src.infra.persistence.database import db
from src.infra.persistence.repositories.daily_loss_repository import DailyLossRepository
from src.infra.persistence.repositories.llm_logs_repository import LlmLogsRepository
from src.infra.persistence.repositories.open_positions_repository import OpenPositionsRepository
from src.infra.persistence.repositories.trades_repository import TradesRepository

log = logging.getLogger(__name__)


# ── Posicoes abertas ──────────────────────────────────────────────────────────

def load_positions() -> dict[str, list[Position]]:
    with db.session() as session:
        return OpenPositionsRepository(session).load_all()


def save_position(symbol: str, position: Position) -> str | None:
    with db.session() as session:
        return OpenPositionsRepository(session).save(symbol, position)


def update_position(position: Position) -> None:
    with db.session() as session:
        OpenPositionsRepository(session).update(position)


def delete_position(position_id: str) -> None:
    with db.session() as session:
        OpenPositionsRepository(session).delete(position_id)


def delete_all_positions(symbol: str) -> None:
    with db.session() as session:
        OpenPositionsRepository(session).delete_all_by_symbol(symbol)


def count_positions_in_db(symbol: str) -> int:
    with db.session() as session:
        return OpenPositionsRepository(session).count_by_symbol(symbol)


# ── Historico de trades ───────────────────────────────────────────────────────

def get_trades_since(since_iso: str) -> list[Trade]:
    with db.session() as session:
        return TradesRepository(session).get_since(since_iso)


def save_trade(
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
    with db.session() as session:
        TradesRepository(session).save(
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


# ── LLM Logs ─────────────────────────────────────────────────────────────────

def save_llm_log(
    symbol: str,
    context: dict,
    response: dict,
    process: str = "",
    tool_called: str | None = None,
    position_id: str | None = None,
) -> str | None:
    with db.session() as session:
        return LlmLogsRepository(session).save(
            symbol=symbol,
            context=context,
            response=response,
            process=process,
            tool_called=tool_called,
            position_id=position_id,
        )


def get_recent_llm_decisions(symbol: str, limit: int = 5) -> list[dict]:
    with db.session() as session:
        return LlmLogsRepository(session).get_recent_decisions(symbol, limit)


def get_recent_performance(symbol: str, limit: int = 10) -> dict:
    with db.session() as session:
        return TradesRepository(session).get_recent_performance(symbol, limit)


# ── Perda diaria ──────────────────────────────────────────────────────────────

def get_daily_loss(date_str: str) -> float:
    with db.session() as session:
        return DailyLossRepository(session).get(date_str)


def upsert_daily_loss(date_str: str, loss: float) -> None:
    with db.session() as session:
        DailyLossRepository(session).upsert(date_str, loss)
