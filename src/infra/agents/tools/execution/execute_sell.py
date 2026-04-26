"""
Tool de execucao: fecha uma posicao de venda pelo db_id.
Contem toda a logica de fechamento, PnL, persistencia e notificacao.
"""

import logging

from binance.exceptions import BinanceAPIException

from src.config import MIN_CONFIDENCE

from src.application.services.risk_orchestrator_service import (
    open_positions,
    session_stats,
    _record_loss,
)
from src.infra.clients.discord.client import discord_notify

from src.infra.clients.binance.client import get_symbol_filters, adjust_qty, order_market_sell
from src.infra.persistence.repository import delete_position, save_trade

log = logging.getLogger("bot")


def close_position_at_index(
    symbol:          str,
    idx:             int,
    current_price:   float,
    reason:          str,
    exit_llm_log_id: str | None = None,
    confidence:      float = 0.0,
):
    """Executa a ordem de venda, atualiza estado em memoria, persiste trade e notifica."""
    positions = open_positions.get(symbol)
    if not positions or idx < 0 or idx >= len(positions):
        return

    pos   = positions[idx]
    entry = pos.entry_price
    qty   = pos.qty
    pnl   = (current_price - entry) * qty

    min_qty, step, decimals, min_notional = get_symbol_filters(symbol)
    sell_qty = adjust_qty(qty * 0.999, step, decimals)

    if sell_qty < min_qty or sell_qty * current_price < min_notional:
        log.warning(f"[{symbol}] Quantidade insuficiente para fechar lote ({sell_qty})")
        if pos.db_id:
            delete_position(pos.db_id)
        positions.pop(idx)
        if not positions:
            del open_positions[symbol]
        return

    try:
        order = order_market_sell(symbol=symbol, quantity=sell_qty)

        session_stats.trades_total += 1
        session_stats.pnl_total    += pnl

        if pnl >= 0:
            session_stats.trades_win += 1
        else:
            session_stats.trades_loss += 1
            _record_loss(abs(pnl))

        level = logging.INFO if pnl >= 0 else logging.WARNING
        log.log(level,
            f"[{symbol}] [{reason}] Lote fechado | "
            f"entrada: ${entry:.4f} -> saida: ${current_price:.4f} | "
            f"PnL: ${pnl:+.4f} | ID: {order['orderId']} | "
            f"Sessao: {session_stats.trades_win}W/{session_stats.trades_loss}L "
            f"PnL total: ${session_stats.pnl_total:+.4f}"
        )

        if pos.db_id:
            delete_position(pos.db_id)

        save_trade(
            symbol=          symbol,
            action=          reason,
            confidence=      confidence,
            entry_price=     entry,
            exit_price=      current_price,
            qty=             qty,
            sl=              pos.sl,
            tp=              pos.tp,
            pnl=             round(pnl, 4),
            reason=          reason,
            llm_log_id=      pos.llm_log_id or None,
            exit_llm_log_id= exit_llm_log_id,
        )

        positions.pop(idx)
        if not positions:
            del open_positions[symbol]

        discord_notify(
            title=f"{reason} -- {symbol}",
            message=(
                f"**Entrada:** ${entry:.4f}\n"
                f"**Saida:** ${current_price:.4f}\n"
                f"**PnL:** ${pnl:+.4f}\n"
                f"**Sessao:** {session_stats.trades_win}W/{session_stats.trades_loss}L "
                f"| PnL total: ${session_stats.pnl_total:+.4f}"
            ),
            color=0x57F287 if pnl >= 0 else 0xED4245,
        )

    except BinanceAPIException as e:
        log.error(f"[{symbol}] Erro ao fechar posicao: {e}")


def tool_execute_sell(
    symbol:          str,
    position_id:     str,
    confidence:      float,
    reason:          str,
    current_price:   float,
    exit_llm_log_id: str | None = None,
) -> bool:
    if confidence < MIN_CONFIDENCE:
        log.info(f"[{symbol}] Confianca {confidence:.0%} abaixo do limiar -- ignorando SELL")
        return False

    posicoes = open_positions.get(symbol, [])
    for idx, pos in enumerate(posicoes):
        if pos.db_id == position_id:
            close_position_at_index(symbol, idx, current_price, reason, exit_llm_log_id, confidence)
            return True

    log.warning(f"[{symbol}] Posicao {position_id} nao encontrada em memoria para SELL")
    return False
