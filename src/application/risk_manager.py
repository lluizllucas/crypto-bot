"""
Gestao de risco: posicoes abertas (persistidas no Supabase), SL/TP dinamicos,
limite diario e execucao de ordens.
"""

import logging
from datetime import datetime, timezone

from binance.exceptions import BinanceAPIException

from src.config import (
    MAX_DAILY_LOSS_USDT,
    MAX_POSITIONS_PER_SYMBOL,
    MIN_ENTRY_DISTANCE_PCT,
    MIN_CONFIDENCE,
    TRADE_USDT,
)

from src.domain.models import Position, SessionStats, TradeSignal

from src.application.notifier import discord_notify

from src.infra.binance.client import (
    get_balance,
    get_current_price,
    get_symbol_filters,
    adjust_qty,
    order_market_buy,
    order_market_sell,
)
from src.infra.supabase.repository import (
    load_positions,
    save_position,
    delete_position,
    delete_all_positions,
    save_trade,
)


log = logging.getLogger(__name__)

# Posicoes abertas em memoria -- carregadas do Supabase na inicializacao
# { "BTCUSDT": [Position, ...] }
open_positions: dict[str, list[Position]] = {}

# Perda acumulada no dia
daily_loss_usdt: float = 0.0
daily_loss_date: str = ""

# Estatisticas da sessao
session_stats = SessionStats(
    started_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
)


def load_state():
    """
    Carrega posicoes abertas do Supabase para a memoria.
    Deve ser chamado uma vez ao iniciar o bot.
    """
    global open_positions

    open_positions = load_positions()

    total = sum(len(v) for v in open_positions.values())

    if total:
        log.info(
            f"Estado restaurado: {total} posicao(oes) abertas em {len(open_positions)} par(es)")
    else:
        log.info("Nenhuma posicao aberta encontrada no banco.")


def check_daily_loss_limit() -> bool:
    """Retorna True se o limite de perda diaria foi atingido."""
    global daily_loss_usdt, daily_loss_date

    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    if daily_loss_date != today:
        if daily_loss_date:
            log.info(
                f"Novo dia -- perda acumulada resetada (era ${daily_loss_usdt:.2f})")

        daily_loss_usdt = 0.0
        daily_loss_date = today

    if daily_loss_usdt >= MAX_DAILY_LOSS_USDT:
        log.warning(
            f"Limite de perda diaria atingido "
            f"(${daily_loss_usdt:.2f} / ${MAX_DAILY_LOSS_USDT:.2f}) -- sem novas ordens hoje"
        )
        return True

    return False


def register_position(symbol: str, entry_price: float, qty: float, sl_pct: float, tp_pct: float):
    """Abre um lote, persiste no Supabase e adiciona na memoria."""
    if symbol not in open_positions:
        open_positions[symbol] = []

    sl = entry_price * (1 - sl_pct / 100)
    tp = entry_price * (1 + tp_pct / 100)

    position = Position(
        entry_price=entry_price,
        qty=qty,
        sl=sl,
        tp=tp,
        ts=datetime.now(timezone.utc),
    )

    db_id = save_position(symbol, position)

    if db_id:
        position.db_id = db_id

    open_positions[symbol].append(position)
    n = len(open_positions[symbol])

    log.info(
        f"[{symbol}] Posicao registrada ({n}/{MAX_POSITIONS_PER_SYMBOL}) | "
        f"entrada: ${entry_price:.4f} | "
        f"SL: ${sl:.4f} (-{sl_pct}%) | "
        f"TP: ${tp:.4f} (+{tp_pct}%)"
    )


def close_position_at_index(
    symbol: str,
    idx: int,
    current_price: float,
    reason: str,
    llm_context: dict | None = None,
    llm_response: dict | None = None,
):
    """Fecha um lote, remove do Supabase e persiste o trade no historico."""
    global daily_loss_usdt

    positions = open_positions.get(symbol)

    if not positions or idx < 0 or idx >= len(positions):
        return

    pos = positions[idx]
    entry = pos.entry_price
    qty = pos.qty
    pnl = (current_price - entry) * qty

    min_qty, step, decimals, min_notional = get_symbol_filters(symbol)
    sell_qty = adjust_qty(qty * 0.999, step, decimals)

    if sell_qty < min_qty or sell_qty * current_price < min_notional:
        log.warning(
            f"[{symbol}] Quantidade insuficiente para fechar lote ({sell_qty})")

        if pos.db_id:
            delete_position(pos.db_id)

        positions.pop(idx)

        if not positions:
            del open_positions[symbol]

        return

    try:
        order = order_market_sell(symbol=symbol, quantity=sell_qty)

        session_stats.trades_total += 1
        session_stats.pnl_total += pnl

        if pnl >= 0:
            session_stats.trades_win += 1
        else:
            session_stats.trades_loss += 1
            daily_loss_usdt += abs(pnl)

        level = logging.INFO if pnl >= 0 else logging.WARNING
        log.log(level,
                f"[{symbol}] [{reason}] Lote fechado | "
                f"entrada: ${entry:.4f} -> saida: ${current_price:.4f} | "
                f"PnL: ${pnl:+.4f} | "
                f"ID: {order['orderId']} | "
                f"Sessao: {session_stats.trades_win}W/{session_stats.trades_loss}L "
                f"PnL total: ${session_stats.pnl_total:+.4f}"
                )

        # Remove posicao do banco e salva trade no historico
        if pos.db_id:
            delete_position(pos.db_id)

        save_trade(
            symbol=symbol,
            action=reason,
            confidence=0.0,
            entry_price=entry,
            exit_price=current_price,
            qty=qty,
            sl=pos.sl,
            tp=pos.tp,
            pnl=round(pnl, 4),
            reason=reason,
            llm_context=llm_context or {},
            llm_response=llm_response or {},
        )

        positions.pop(idx)

        if not positions:
            del open_positions[symbol]

        notify_color = 0x57F287 if pnl >= 0 else 0xED4245

        discord_notify(
            title=f"{reason} -- {symbol}",
            message=(
                f"**Entrada:** ${entry:.4f}\n"
                f"**Saida:** ${current_price:.4f}\n"
                f"**PnL:** ${pnl:+.4f}\n"
                f"**Sessao:** {session_stats.trades_win}W/{session_stats.trades_loss}L "
                f"| PnL total: ${session_stats.pnl_total:+.4f}"
            ),
            color=notify_color
        )
    except BinanceAPIException as e:
        log.error(f"[{symbol}] Erro ao fechar posicao: {e}")


def execute_trade(
    symbol: str,
    signal: TradeSignal,
    last_price: float,
    llm_context: dict | None = None,
) -> bool:
    """Executa uma ordem de mercado usando os SL/TP dinamicos retornados pela LLM."""
    if signal.confidence < MIN_CONFIDENCE:
        log.info(
            f"[{symbol}] Confianca {signal.confidence:.0%} abaixo do limiar -- ignorando")
        return False

    if signal.action in ("RANGE_MODE", "TREND_MODE", "HOLD"):
        log.info(f"[{symbol}] Modo: {signal.action} -- sem execucao de ordem")
        return False

    base_asset = symbol.replace("USDT", "")
    usdt_balance = get_balance("USDT")
    base_balance = get_balance(base_asset)
    min_qty, step, decimals, min_notional = get_symbol_filters(symbol)

    llm_response = {
        "action":         signal.action,
        "confidence":     signal.confidence,
        "sl_percentage":  signal.sl_percentage,
        "tp_percentage":  signal.tp_percentage,
        "reason":         signal.reason,
    }

    try:
        if signal.action == "BUY":
            posicoes = open_positions.get(symbol, [])

            if len(posicoes) >= MAX_POSITIONS_PER_SYMBOL:
                log.info(
                    f"[{symbol}] Limite de posicoes ({MAX_POSITIONS_PER_SYMBOL}) -- ignorando BUY")
                return False

            if posicoes:
                ultima_entrada = posicoes[-1].entry_price
                distancia = abs(last_price - ultima_entrada) / \
                    ultima_entrada * 100
                if distancia < MIN_ENTRY_DISTANCE_PCT:
                    log.info(
                        f"[{symbol}] Nova entrada muito perto da ultima "
                        f"({distancia:.2f}% < {MIN_ENTRY_DISTANCE_PCT}%) -- ignorando BUY"
                    )
                    return False

            if usdt_balance < 10:
                log.warning(
                    f"[{symbol}] Saldo USDT insuficiente ({usdt_balance:.2f})")
                return False

            spend = min(TRADE_USDT, usdt_balance * 0.99)
            qty = adjust_qty(spend / last_price, step, decimals)

            if qty < min_qty or qty * last_price < min_notional:
                log.warning(
                    f"[{symbol}] Ordem abaixo dos filtros minimos -- ignorando")
                return False

            order = order_market_buy(symbol=symbol, quantity=qty)
            sl_price = last_price * (1 - signal.sl_percentage / 100)
            tp_price = last_price * (1 + signal.tp_percentage / 100)

            log.info(
                f"[{symbol}] [BUY] Ordem executada | "
                f"qty: {qty} @ ~${last_price:.4f} | "
                f"valor: ~${qty * last_price:.2f} | "
                f"SL: ${sl_price:.4f} (-{signal.sl_percentage}%) | "
                f"TP: ${tp_price:.4f} (+{signal.tp_percentage}%) | "
                f"ID: {order['orderId']}"
            )

            register_position(symbol, last_price, qty,
                              signal.sl_percentage, signal.tp_percentage)

            # Salva o trade de abertura no historico
            save_trade(
                symbol=symbol,
                action="BUY",
                confidence=signal.confidence,
                entry_price=last_price,
                exit_price=0.0,
                qty=qty,
                sl=sl_price,
                tp=tp_price,
                pnl=0.0,
                reason=signal.reason,
                llm_context=llm_context or {},
                llm_response=llm_response,
            )

            discord_notify(
                title=f"BUY -- {symbol}",
                message=(
                    f"**Preco:** ${last_price:.4f}\n"
                    f"**Quantidade:** {qty}\n"
                    f"**Valor:** ~${qty * last_price:.2f}\n"
                    f"**Stop-loss:** ${sl_price:.4f} (-{signal.sl_percentage}%)\n"
                    f"**Take-profit:** ${tp_price:.4f} (+{signal.tp_percentage}%)\n"
                    f"**Motivo:** {signal.reason}"
                ),
                color=0x57F287
            )
            return True

        elif signal.action == "SELL":
            if base_balance < 0.001:
                log.info(f"[{symbol}] Sem {base_asset} para vender")
                return False

            qty = adjust_qty(base_balance * 0.999, step, decimals)

            if qty < min_qty or qty * last_price < min_notional:
                log.warning(
                    f"[{symbol}] Ordem abaixo dos filtros minimos -- ignorando")
                return False

            order = order_market_sell(symbol=symbol, quantity=qty)

            log.info(
                f"[{symbol}] [SELL] Ordem executada | "
                f"qty: {qty} {base_asset} @ ~${last_price:.4f} | "
                f"ID: {order['orderId']}"
            )

            # Fecha todas as posicoes do simbolo no banco
            delete_all_positions(symbol)
            if symbol in open_positions:
                del open_positions[symbol]

            save_trade(
                symbol=symbol,
                action="SELL",
                confidence=signal.confidence,
                entry_price=0.0,
                exit_price=last_price,
                qty=qty,
                sl=0.0,
                tp=0.0,
                pnl=0.0,
                reason=signal.reason,
                llm_context=llm_context or {},
                llm_response=llm_response,
            )

            discord_notify(
                title=f"SELL -- {symbol}",
                message=(
                    f"**Preco:** ${last_price:.4f}\n"
                    f"**Quantidade:** {qty} {base_asset}\n"
                    f"**Motivo:** {signal.reason}"
                ),
                color=0xFEE75C
            )
            return True

    except BinanceAPIException as e:
        log.error(f"[{symbol}] [ERRO] Binance: {e}")
    except Exception as e:
        log.error(f"[{symbol}] [ERRO] Inesperado: {e}")

    return False


def monitor_positions():
    """Ciclo rapido -- verifica SL/TP em cada lote aberto sem chamar o LLM."""
    if not open_positions:
        return

    for symbol in list(open_positions.keys()):
        price = get_current_price(symbol)
        if price is None:
            continue

        positions = open_positions[symbol]
        for idx in range(len(positions) - 1, -1, -1):
            pos = positions[idx]
            entry = pos.entry_price
            change = (price - entry) / entry * 100

            if price <= pos.sl:
                log.warning(
                    f"[MONITOR] [{symbol}] STOP-LOSS @ ${price:.4f} "
                    f"(entrada ${entry:.4f}, {change:+.2f}%)"
                )
                close_position_at_index(symbol, idx, price, "STOP-LOSS")

            elif price >= pos.tp:
                log.info(
                    f"[MONITOR] [{symbol}] TAKE-PROFIT @ ${price:.4f} "
                    f"(entrada ${entry:.4f}, {change:+.2f}%)"
                )
                close_position_at_index(symbol, idx, price, "TAKE-PROFIT")

            else:
                log.info(
                    f"[MONITOR] [{symbol}] OK | entrada: ${entry:.4f} | "
                    f"atual: ${price:.4f} | {change:+.2f}%"
                )
