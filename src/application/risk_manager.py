"""
Gestao de risco: posicoes abertas, SL/TP dinamicos, TP progressivo,
early exit, limite diario e execucao de ordens.
"""

import logging
log = logging.getLogger("bot")
from datetime import datetime, timezone

from binance.exceptions import BinanceAPIException

from src.config import (
    MAX_DAILY_LOSS_USDT,
    MAX_POSITIONS_PER_SYMBOL,
    MIN_ENTRY_DISTANCE_PCT,
    MIN_CONFIDENCE,
    TRADE_USDT,
    TP_HOLD_MIN_CONFIDENCE,
    TP_EXTENSION_MULTIPLIER,
    SL_EARLY_EXIT_THRESHOLD,
    MIN_CONFIDENCE_EARLY_EXIT,
    AVERAGING_DOWN_BLOCK_HOURS,
    AVERAGING_DOWN_MIN_PNL_PCT,
)

from src.domain.models import Position, SessionStats


from src.application.notifier import discord_notify
from src.application.tools import process_monitor_actions

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
    update_position,
    delete_position,
    delete_all_positions,
    count_positions_in_db,
    save_trade,
    get_daily_loss,
    upsert_daily_loss,
    save_llm_log,
)


# Posicoes abertas em memoria -- carregadas do Supabase na inicializacao
# { "BTCUSDT": [Position, ...] }
open_positions: dict[str, list[Position]] = {}

# Perda acumulada no dia (restaurada do banco na inicializacao)
daily_loss_usdt: float = 0.0
daily_loss_date: str   = ""

# Estatisticas da sessao
session_stats = SessionStats(
    started_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
)


# ── Inicializacao ─────────────────────────────────────────────────────────────

def load_state():
    """
    Carrega posicoes abertas e perda diaria do Supabase para a memoria.
    Deve ser chamado uma vez ao iniciar o bot.
    """
    global open_positions, daily_loss_usdt, daily_loss_date

    open_positions = load_positions()
    total = sum(len(v) for v in open_positions.values())

    if total:
        log.info(f"Estado restaurado: {total} posicao(oes) em {len(open_positions)} par(es)")
    else:
        log.info("Nenhuma posicao aberta encontrada no banco.")

    # Restaura perda diaria do banco
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_loss_usdt = get_daily_loss(today)
    daily_loss_date = today

    if daily_loss_usdt > 0:
        log.info(f"Perda diaria restaurada: ${daily_loss_usdt:.2f} / ${MAX_DAILY_LOSS_USDT:.2f}")


# ── Limite diario ─────────────────────────────────────────────────────────────

def check_daily_loss_limit() -> bool:
    """Retorna True se o limite de perda diaria foi atingido."""
    global daily_loss_usdt, daily_loss_date

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if daily_loss_date != today:
        if daily_loss_date:
            log.info(f"Novo dia -- perda acumulada resetada (era ${daily_loss_usdt:.2f})")
        daily_loss_usdt = 0.0
        daily_loss_date = today

    if daily_loss_usdt >= MAX_DAILY_LOSS_USDT:
        log.warning(
            f"Limite de perda diaria atingido "
            f"(${daily_loss_usdt:.2f} / ${MAX_DAILY_LOSS_USDT:.2f}) -- sem novas ordens hoje"
        )
        return True

    # Alerta de 80% do limite
    if daily_loss_usdt >= MAX_DAILY_LOSS_USDT * 0.8:
        log.warning(
            f"Atencao: perda diaria em {daily_loss_usdt / MAX_DAILY_LOSS_USDT:.0%} do limite "
            f"(${daily_loss_usdt:.2f} / ${MAX_DAILY_LOSS_USDT:.2f})"
        )
        discord_notify(
            title="Alerta de perda diaria",
            message=(
                f"Perda acumulada: **${daily_loss_usdt:.2f}** de **${MAX_DAILY_LOSS_USDT:.2f}**\n"
                f"Limite em {daily_loss_usdt / MAX_DAILY_LOSS_USDT:.0%} — proximas perdas bloqueiam novas ordens."
            ),
            color=0xFEE75C,
        )

    return False


def _record_loss(amount: float):
    """Registra perda no acumulador em memoria e persiste no banco."""
    global daily_loss_usdt, daily_loss_date

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if daily_loss_date != today:
        daily_loss_usdt = 0.0
        daily_loss_date = today

    daily_loss_usdt += abs(amount)
    upsert_daily_loss(today, daily_loss_usdt)


# ── Registro de posicoes ──────────────────────────────────────────────────────

def register_position(
    symbol:     str,
    entry_price: float,
    qty:        float,
    sl_pct:     float,
    tp_pct:     float,
    llm_log_id: str = "",
) -> Position | None:
    """Abre um lote, persiste no Supabase e adiciona na memoria."""
    if symbol not in open_positions:
        open_positions[symbol] = []

    sl = entry_price * (1 - sl_pct / 100)
    tp = entry_price * (1 + tp_pct / 100)

    position = Position(
        entry_price=  entry_price,
        qty=          qty,
        sl=           sl,
        tp=           tp,
        ts=           datetime.now(timezone.utc),
        llm_log_id=   llm_log_id,
        original_sl=  sl,
        original_tp=  tp,
        tp_hold_count=0,
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
    return position


# ── Fechamento de posicoes ────────────────────────────────────────────────────

def close_position_at_index(
    symbol:          str,
    idx:             int,
    current_price:   float,
    reason:          str,
    exit_llm_log_id: str | None = None,
):
    """Fecha um lote, remove do Supabase e persiste o trade no historico."""
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
            confidence=      0.0,
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


# ── TP progressivo ────────────────────────────────────────────────────────────

def _tp_threshold(hold_count: int) -> float:
    """Retorna o threshold de confianca minimo para a N-esima tentativa de hold."""
    thresholds = TP_HOLD_MIN_CONFIDENCE
    if hold_count < len(thresholds):
        return thresholds[hold_count]
    return thresholds[-1]


def apply_tp_hold(symbol: str, pos: Position):
    """
    Aplica o hold progressivo apos o LLM decidir segurar no TP:
    - Sobe o SL para proteger o lucro acumulado
    - Estende o TP
    - Incrementa o contador de tentativas
    - Persiste no banco
    """
    pos.tp_hold_count += 1

    # SL sobe de acordo com a tentativa
    if pos.tp_hold_count == 1:
        # 1a tentativa: SL vai para break-even (entrada)
        pos.sl = pos.entry_price
    else:
        # 2a+ tentativa: SL vai para o TP anterior (lucro garantido)
        pos.sl = pos.tp

    # TP estendido
    pos.tp = pos.tp * TP_EXTENSION_MULTIPLIER

    update_position(pos)

    log.info(
        f"[{symbol}] TP hold #{pos.tp_hold_count} aplicado | "
        f"Novo SL: ${pos.sl:.4f} | Novo TP: ${pos.tp:.4f}"
    )

    discord_notify(
        title=f"TP Hold #{pos.tp_hold_count} -- {symbol}",
        message=(
            f"**LLM segurou no TP** (tentativa {pos.tp_hold_count})\n"
            f"**Novo SL:** ${pos.sl:.4f}\n"
            f"**Novo TP:** ${pos.tp:.4f}"
        ),
        color=0x5865F2,
    )


# ── Execucao de ordens (bot.py) ───────────────────────────────────────────────

def execute_buy(
    symbol:     str,
    confidence: float,
    sl_pct:     float,
    tp_pct:     float,
    reason:     str,
    last_price: float,
    llm_log_id: str | None = None,
) -> bool:
    """Valida todas as regras de risco e executa ordem de compra."""
    if confidence < MIN_CONFIDENCE:
        log.info(f"[{symbol}] Confianca {confidence:.0%} abaixo do limiar -- ignorando BUY")
        return False

    if check_daily_loss_limit():
        return False

    # Lock otimista: verifica no banco, nao apenas em memoria
    db_count = count_positions_in_db(symbol)
    if db_count >= MAX_POSITIONS_PER_SYMBOL:
        log.info(f"[{symbol}] Limite de posicoes no banco ({db_count}/{MAX_POSITIONS_PER_SYMBOL}) -- ignorando BUY")
        return False

    posicoes = open_positions.get(symbol, [])
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

        # Bloqueio de averaging down temporal
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

        pos = register_position(symbol, last_price, qty, sl_pct, tp_pct, llm_log_id or "")

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


def execute_sell_by_id(
    symbol:          str,
    position_id:     str,
    confidence:      float,
    reason:          str,
    current_price:   float,
    exit_llm_log_id: str | None = None,
) -> bool:
    """Fecha uma posicao especifica pelo db_id (decisao estrategica do LLM no bot.py)."""
    posicoes = open_positions.get(symbol, [])
    for idx, pos in enumerate(posicoes):
        if pos.db_id == position_id:
            close_position_at_index(symbol, idx, current_price, reason, exit_llm_log_id)
            return True

    log.warning(f"[{symbol}] Posicao {position_id} nao encontrada em memoria para SELL")
    return False


# ── Monitor SL/TP (check_sl_tp.py) ───────────────────────────────────────────

def get_current_price_with_retry(symbol: str, attempts: int = 3) -> float | None:
    """Busca o preco atual com retry em caso de falha."""
    for attempt in range(1, attempts + 1):
        price = get_current_price(symbol)
        if price is not None:
            return price
        if attempt < attempts:
            log.warning(f"[MONITOR] Falha ao buscar preco de {symbol} (tentativa {attempt}/{attempts})")

    log.error(f"[MONITOR] Nao foi possivel obter preco de {symbol} apos {attempts} tentativas")
    discord_notify(
        title=f"Erro de preco -- {symbol}",
        message=f"Nao foi possivel obter preco apos {attempts} tentativas. Posicoes nao monitoradas neste ciclo.",
        color=0xED4245,
    )
    return None


def monitor_positions(
    llm_analyze_fn=None,
    market_data_fn=None,
):
    """
    Ciclo rapido de monitoramento SL/TP.
    - SL: executa direto, sem LLM
    - 80% do SL: consulta LLM via early_exit
    - TP: consulta LLM via sell_position ou hold_position

    llm_analyze_fn: funcao analyze_monitor do llm_analyst (injetada para evitar import circular)
    market_data_fn: funcao get_market_data do market_data (injetada)
    """
    if not open_positions:
        return

    for symbol in list(open_positions.keys()):
        price = get_current_price_with_retry(symbol)
        if price is None:
            continue

        positions = open_positions[symbol]

        for idx in range(len(positions) - 1, -1, -1):
            pos    = positions[idx]
            entry  = pos.entry_price
            change = (price - entry) / entry * 100

            # 1. SL atingido — executa direto, sem LLM
            if price <= pos.sl:
                log.warning(
                    f"[MONITOR] [{symbol}] STOP-LOSS @ ${price:.4f} "
                    f"(entrada ${entry:.4f}, {change:+.2f}%)"
                )
                close_position_at_index(symbol, idx, price, "STOP-LOSS")
                continue

            # 2. TP atingido — consulta LLM
            if price >= pos.tp:
                log.info(
                    f"[MONITOR] [{symbol}] TP ATINGIDO @ ${price:.4f} "
                    f"(entrada ${entry:.4f}, {change:+.2f}%) — consultando LLM"
                )
                _handle_tp(symbol, idx, pos, price, llm_analyze_fn, market_data_fn)
                continue

            # 3. Early exit — preco a 80% do caminho ate o SL
            sl_distance_total = entry - pos.sl
            sl_distance_atual = entry - price
            if sl_distance_total > 0 and sl_distance_atual / sl_distance_total >= SL_EARLY_EXIT_THRESHOLD:
                log.warning(
                    f"[MONITOR] [{symbol}] PRECO PROXIMO DO SL ({sl_distance_atual / sl_distance_total:.0%}) "
                    f"@ ${price:.4f} — consultando LLM para early exit"
                )
                _handle_early_exit(symbol, idx, pos, price, llm_analyze_fn, market_data_fn)
                continue

            log.info(
                f"[MONITOR] [{symbol}] OK | entrada: ${entry:.4f} | "
                f"atual: ${price:.4f} | {change:+.2f}%"
            )


def _handle_tp(symbol, idx, pos, price, llm_analyze_fn, market_data_fn):
    """Trata TP atingido: consulta LLM e aplica decisao via process_monitor_actions."""
    if llm_analyze_fn is None or market_data_fn is None:
        log.info(f"[MONITOR] LLM nao disponivel — vendendo no TP")
        close_position_at_index(symbol, idx, price, "TAKE-PROFIT")
        return

    data = market_data_fn(symbol)
    if data is None:
        log.warning(f"[MONITOR] Falha ao buscar dados de mercado — vendendo no TP")
        close_position_at_index(symbol, idx, price, "TAKE-PROFIT")
        return

    actions, reasoning = llm_analyze_fn(
        data=data,
        open_positions=open_positions,
        triggered_positions=[pos],
        trigger_type="TP",
    )

    from src.application.llm_analyst import build_context
    context         = build_context(data, open_positions)
    exit_llm_log_id = save_llm_log(
        symbol=      symbol,
        context=     context,
        response=    {"actions": actions, "reasoning": reasoning},
        process=     "monitor",
        tool_called= actions[0]["tool"] if actions else None,
        position_id= pos.db_id or None,
    )

    acted = process_monitor_actions(
        actions=          actions,
        symbol=           symbol,
        pos=              pos,
        price=            price,
        exit_llm_log_id=  exit_llm_log_id,
        apply_tp_hold_fn= lambda: apply_tp_hold(symbol, pos),
        close_position_fn=lambda reason, log_id: close_position_at_index(symbol, idx, price, reason, log_id),
        tp_threshold=     _tp_threshold(pos.tp_hold_count),
        min_conf_early=   MIN_CONFIDENCE_EARLY_EXIT,
        trigger_type=     "TP",
    )

    if not acted:
        log.info(f"[MONITOR] [{symbol}] LLM nao acionou tool para TP — vendendo")
        close_position_at_index(symbol, idx, price, "TAKE-PROFIT", exit_llm_log_id)


def _handle_early_exit(symbol, idx, pos, price, llm_analyze_fn, market_data_fn):
    """Trata preco proximo do SL: consulta LLM para saida antecipada via process_monitor_actions."""
    if llm_analyze_fn is None or market_data_fn is None:
        return

    data = market_data_fn(symbol)
    if data is None:
        return

    actions, reasoning = llm_analyze_fn(
        data=data,
        open_positions=open_positions,
        triggered_positions=[pos],
        trigger_type="EARLY_EXIT",
    )

    from src.application.llm_analyst import build_context
    context         = build_context(data, open_positions)
    exit_llm_log_id = save_llm_log(
        symbol=      symbol,
        context=     context,
        response=    {"actions": actions, "reasoning": reasoning},
        process=     "monitor",
        tool_called= actions[0]["tool"] if actions else None,
        position_id= pos.db_id or None,
    )

    process_monitor_actions(
        actions=          actions,
        symbol=           symbol,
        pos=              pos,
        price=            price,
        exit_llm_log_id=  exit_llm_log_id,
        apply_tp_hold_fn= lambda: apply_tp_hold(symbol, pos),
        close_position_fn=lambda reason, log_id: close_position_at_index(symbol, idx, price, reason, log_id),
        tp_threshold=     _tp_threshold(pos.tp_hold_count),
        min_conf_early=   MIN_CONFIDENCE_EARLY_EXIT,
        trigger_type=     "EARLY_EXIT",
    )