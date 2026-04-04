"""
Crypto Trading Bot -- OpenRouter (estrategista) + Binance Testnet (simulacao)
Stack 100% gratuito, sem dados fiscais, funciona no Brasil
"""

import time
import schedule

from datetime import datetime, timezone

from src.infra import setup_logging, get_balance, get_current_price
from src.config import (
    SYMBOLS,
    INTERVAL_MINUTES,
    MONITOR_INTERVAL_MINUTES,
    MAX_DAILY_LOSS_USDT,
    TRADE_USDT,
    MAX_POSITIONS_PER_SYMBOL,
    MIN_ENTRY_DISTANCE_PCT,
)
from src.application.market_data import get_market_data
from src.application.llm_analyst import analyze
from src.application.risk_manager import (
    load_state,
    check_daily_loss_limit,
    execute_trade,
    monitor_positions,
    open_positions,
    daily_loss_usdt,
    session_stats,
)
from src.application.llm_analyst import build_context

log = setup_logging()


# ── Resumo diario ─────────────────────────────────────────────────────────────

def log_daily_summary():
    """Loga um resumo diario das operacoes -- agendado para meia-noite."""
    usdt = get_balance("USDT")

    total = session_stats.trades_total
    wins = session_stats.trades_win
    wr = (wins / total * 100) if total > 0 else 0

    log.info("=" * 55)
    log.info("RESUMO DIARIO")
    log.info(f"  Saldo USDT atual:   ${usdt:.2f}")
    log.info(f"  Operacoes hoje:     {total}")
    log.info(
        f"  Win rate:           {wr:.1f}% ({wins}W/{session_stats.trades_loss}L)")
    log.info(f"  PnL da sessao:      ${session_stats.pnl_total:+.4f}")
    log.info(
        f"  Perda acumulada:    ${daily_loss_usdt:.2f} / ${MAX_DAILY_LOSS_USDT:.2f}")
    total_lotes = sum(len(v) for v in open_positions.values())
    log.info(
        f"  Posicoes abertas:   {total_lotes} lote(s) em {len(open_positions)} par(es)")

    if open_positions:
        for sym, plist in open_positions.items():
            price = get_current_price(sym)

            if not price:
                continue

            for pos in plist:
                change = (price - pos.entry_price) / pos.entry_price * 100

                log.info(
                    f"    {sym}: entrada ${pos.entry_price:.4f} | "
                    f"atual ${price:.4f} | {change:+.2f}%"
                )

    log.info("=" * 55)


# ── Ciclo de analise ──────────────────────────────────────────────────────────

def run_cycle():
    log.info("-" * 55)
    log.info(
        f"Ciclo: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')}")
    log.info(
        f"Saldo USDT: ${get_balance('USDT'):.2f} | "
        f"Perda hoje: ${daily_loss_usdt:.2f}/${MAX_DAILY_LOSS_USDT:.2f} | "
        f"Sessao: {session_stats.trades_win}W/{session_stats.trades_loss}L "
        f"PnL: ${session_stats.pnl_total:+.4f}"
    )

    daily_limit_hit = check_daily_loss_limit()

    for symbol in SYMBOLS:
        data = get_market_data(symbol)

        if not data:
            continue

        price = data.price

        plist = open_positions.get(symbol, [])

        for pos in plist:
            change = (price - pos.entry_price) / pos.entry_price * 100

            log.info(
                f"[{symbol}] Posicao aberta | "
                f"entrada: ${pos.entry_price:.4f} | atual: ${price:.4f} | {change:+.2f}%"
            )

        log.info(
            f"[{symbol}] Analisando... (RSI: {data.rsi_1h} | F&G: {data.fear_greed})")

        context = build_context(data, open_positions)
        signal  = analyze(data, open_positions)

        log.info(
            f"[{symbol}] Preco: ${price:.4f} | "
            f"Acao: {signal.action} | "
            f"Confianca: {signal.confidence:.0%} | "
            f"SL: {signal.sl_percentage}% | TP: {signal.tp_percentage}%"
        )
        log.info(f"[{symbol}] LLM: {signal.reason}")

        if not daily_limit_hit:
            execute_trade(symbol, signal, price, llm_context=context)

        time.sleep(10)

    log.info("Ciclo concluido.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("=" * 55)
    log.info(
        "---Crypto Bot iniciado -- OpenRouter + Binance TESTNET by lluizllucas---")
    log.info(f"  Simbolos:              {', '.join(SYMBOLS)}")
    log.info(f"  Analise:               a cada {INTERVAL_MINUTES} min")
    log.info(f"  Monitor SL/TP:         a cada {MONITOR_INTERVAL_MINUTES} min")
    log.info(f"  USDT por trade:        ${TRADE_USDT}")
    log.info(f"  Max lotes/par:         {MAX_POSITIONS_PER_SYMBOL}")
    log.info(f"  Dist. min. entrada:    {MIN_ENTRY_DISTANCE_PCT}%")
    log.info(f"  SL/TP:                 dinamicos (definidos pela LLM via ATR)")
    log.info(f"  Limite diario:         ${MAX_DAILY_LOSS_USDT}")
    log.info("=" * 55)

    load_state()
    run_cycle()

    schedule.every(INTERVAL_MINUTES).minutes.do(run_cycle)
    schedule.every(MONITOR_INTERVAL_MINUTES).minutes.do(monitor_positions)
    schedule.every().day.at("00:00").do(log_daily_summary)

    while True:
        schedule.run_pending()
        time.sleep(15)
