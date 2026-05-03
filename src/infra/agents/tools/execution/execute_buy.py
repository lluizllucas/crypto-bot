"""
Tool de execucao: abre uma nova posicao de compra.
Contem toda a logica de validacao de risco, registro e execucao da ordem.
"""

import logging

from datetime import datetime, timezone

from binance.exceptions import BinanceAPIException

from src.config import (
    MIN_CONFIDENCE,
    MAX_POSITIONS_PER_SYMBOL,
    MIN_ENTRY_DISTANCE_PCT,
    TRADE_USDT,
    AVERAGING_DOWN_BLOCK_HOURS,
    AVERAGING_DOWN_MIN_PNL_PCT,
)

from src.domain.entities.position import Position

from src.application.services.risk_service import check_daily_loss_limit
from src.infra.clients.discord.client import discord_notify

from src.infra.clients.binance.client import get_balance, get_symbol_filters, adjust_qty, order_market_buy
from src.infra.persistence.repository import save_position, save_trade, count_positions_in_db, get_positions_by_symbol

log = logging.getLogger("bot")


def tool_execute_buy(
    symbol:     str,
    confidence: float,
    sl_pct:     float,
    tp_pct:     float,
    reason:     str,
    last_price: float,
    llm_log_id: str | None = None,
) -> bool:
    if confidence < MIN_CONFIDENCE:
        log.info(f"[{symbol}] Confianca {confidence:.0%} abaixo do limiar -- ignorando BUY")
        return False

    if check_daily_loss_limit():
        return False

    db_count = count_positions_in_db(symbol)
    if db_count >= MAX_POSITIONS_PER_SYMBOL:
        log.info(f"[{symbol}] Limite de posicoes no banco ({db_count}/{MAX_POSITIONS_PER_SYMBOL}) -- ignorando BUY")
        return False

    posicoes = get_positions_by_symbol(symbol)
    if posicoes:
        ultima = posicoes[-1]
        ultima_entrada = ultima.entry_price

        distancia = abs(last_price - ultima_entrada) / ultima_entrada * 100
        if distancia < MIN_ENTRY_DISTANCE_PCT:
            log.info(
                f"[{symbol}] Nova entrada muito perto da ultima "
                f"({distancia:.2f}% < {MIN_ENTRY_DISTANCE_PCT}%) -- ignorando BUY"
            )
            return False

        pnl_pct = (last_price - ultima_entrada) / ultima_entrada * 100
        horas_abertas = (
            datetime.now(timezone.utc) - ultima.ts.replace(tzinfo=timezone.utc)
            if ultima.ts.tzinfo is None else
            datetime.now(timezone.utc) - ultima.ts
        ).total_seconds() / 3600

        if pnl_pct <= AVERAGING_DOWN_MIN_PNL_PCT and horas_abertas < AVERAGING_DOWN_BLOCK_HOURS:
            log.info(
                f"[{symbol}] Averaging down bloqueado: posicao em {pnl_pct:.2f}% "
                f"aberta ha {horas_abertas:.1f}h (minimo {AVERAGING_DOWN_BLOCK_HOURS}h) -- ignorando BUY"
            )
            return False

    usdt_balance = get_balance("USDT")
    if usdt_balance < 10:
        log.warning(f"[{symbol}] Saldo USDT insuficiente ({usdt_balance:.2f})")
        return False

    min_qty, step, decimals, min_notional = get_symbol_filters(symbol)
    spend = min(TRADE_USDT, usdt_balance * 0.99)
    qty   = adjust_qty(spend / last_price, step, decimals)

    if qty < min_qty or qty * last_price < min_notional:
        log.warning(f"[{symbol}] Ordem abaixo dos filtros minimos -- ignorando")
        return False

    try:
        order    = order_market_buy(symbol=symbol, quantity=qty)
        sl_price = last_price * (1 - sl_pct / 100)
        tp_price = last_price * (1 + tp_pct / 100)

        log.info(
            f"[{symbol}] [BUY] Ordem executada | "
            f"qty: {qty} @ ~${last_price:.4f} | "
            f"SL: ${sl_price:.4f} (-{sl_pct}%) | "
            f"TP: ${tp_price:.4f} (+{tp_pct}%) | "
            f"ID: {order['orderId']}"
        )

        position = Position(
            entry_price=  last_price,
            qty=          qty,
            sl=           sl_price,
            tp=           tp_price,
            ts=           datetime.now(timezone.utc),
            llm_log_id=   llm_log_id or "",
            original_sl=  sl_price,
            original_tp=  tp_price,
            tp_hold_count=0,
        )

        db_id = save_position(symbol, position)
        n = count_positions_in_db(symbol)

        log.info(
            f"[{symbol}] Posicao registrada ({n}/{MAX_POSITIONS_PER_SYMBOL}) | "
            f"entrada: ${last_price:.4f} | "
            f"SL: ${sl_price:.4f} (-{sl_pct}%) | "
            f"TP: ${tp_price:.4f} (+{tp_pct}%)"
        )

        save_trade(
            symbol=      symbol,
            action=      "BUY",
            confidence=  confidence,
            entry_price= last_price,
            exit_price=  0.0,
            qty=         qty,
            sl=          sl_price,
            tp=          tp_price,
            pnl=         0.0,
            reason=      reason,
            llm_log_id=  llm_log_id,
        )

        discord_notify(
            title=f"BUY -- {symbol}",
            message=(
                f"**Preco:** ${last_price:.4f}\n"
                f"**Quantidade:** {qty}\n"
                f"**Valor:** ~${qty * last_price:.2f}\n"
                f"**Stop-loss:** ${sl_price:.4f} (-{sl_pct}%)\n"
                f"**Take-profit:** ${tp_price:.4f} (+{tp_pct}%)\n"
                f"**Motivo:** {reason}"
            ),
            color=0x57F287,
        )
        return True

    except BinanceAPIException as e:
        log.error(f"[{symbol}] [ERRO] Binance: {e}")
    except Exception as e:
        log.error(f"[{symbol}] [ERRO] Inesperado: {e}")

    return False
