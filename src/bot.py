"""
Crypto Trading Bot -- OpenRouter (estrategista) + Binance Testnet (simulacao)
Stack 100% gratuito, sem dados fiscais, funciona no Brasil
"""

import time
import schedule

from datetime import datetime, timedelta, timezone

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
from src.infra.supabase.repository import get_trades_since, save_llm_log

log = setup_logging()


# ── Resumo diario ─────────────────────────────────────────────────────────────

def log_daily_summary():
    """Loga um resumo diario das operacoes com dados de mercado -- agendado para meia-noite."""
    usdt = get_balance("USDT")

    total = session_stats.trades_total
    wins  = session_stats.trades_win
    wr    = (wins / total * 100) if total > 0 else 0

    log.info("=" * 55)
    log.info("RESUMO DIARIO")
    log.info(f"  Data:               {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    log.info(f"  Saldo USDT atual:   ${usdt:.2f}")
    log.info(f"  Operacoes hoje:     {total}")
    log.info(f"  Win rate:           {wr:.1f}% ({wins}W/{session_stats.trades_loss}L)")
    log.info(f"  PnL da sessao:      ${session_stats.pnl_total:+.4f}")
    log.info(f"  Perda acumulada:    ${daily_loss_usdt:.2f} / ${MAX_DAILY_LOSS_USDT:.2f}")

    total_lotes = sum(len(v) for v in open_positions.values())
    log.info(f"  Posicoes abertas:   {total_lotes} lote(s) em {len(open_positions)} par(es)")

    # Dados de mercado por simbolo
    for symbol in SYMBOLS:
        data = get_market_data(symbol)
        if not data:
            continue

        if data.ema20 > data.ema50 > data.ema200:
            ema_trend = "bullish"
        elif data.ema20 < data.ema50 < data.ema200:
            ema_trend = "bearish"
        else:
            ema_trend = "neutral"

        bb_pos = (
            (data.price - data.bb_lower) / (data.bb_upper - data.bb_lower) * 100
            if data.bb_upper != data.bb_lower else 50.0
        )

        log.info(f"  [{symbol}] Mercado:")
        log.info(f"    Preco:            ${data.price:.4f}")
        log.info(f"    RSI 1h:           {data.rsi_1h:.1f}")
        log.info(f"    Fear & Greed:     {data.fear_greed}")
        log.info(f"    Tendencia EMA:    {ema_trend} (EMA20:{data.ema20:.0f} EMA50:{data.ema50:.0f} EMA200:{data.ema200:.0f})")
        log.info(f"    Bollinger:        lower ${data.bb_lower:.0f} / upper ${data.bb_upper:.0f} | pos: {bb_pos:.0f}%")
        log.info(f"    ATR:              {data.atr:.2f}")
        log.info(f"    Volume 24h:       {data.volume_24h:.2f} BTC | media 5h: {data.avg_volume_5h:.2f} BTC")
        log.info(f"    Range 24h:        ${data.range_low_24h:.0f} - ${data.range_high_24h:.0f} | pos: {data.range_position_24h * 100:.0f}%")
        log.info(f"    Range 7d:         ${data.range_low_7d:.0f} - ${data.range_high_7d:.0f} | pos: {data.range_position_7d * 100:.0f}%")
        log.info(f"    Range 30d:        ${data.range_low_30d:.0f} - ${data.range_high_30d:.0f}")

        # Posicoes abertas do simbolo
        plist = open_positions.get(symbol, [])
        if plist:
            for pos in plist:
                change = (data.price - pos.entry_price) / pos.entry_price * 100
                pnl_est = (data.price - pos.entry_price) * pos.qty
                log.info(
                    f"    Posicao: entrada ${pos.entry_price:.4f} | "
                    f"atual ${data.price:.4f} | {change:+.2f}% | "
                    f"PnL est.: ${pnl_est:+.4f} | "
                    f"SL: ${pos.sl:.4f} | TP: ${pos.tp:.4f}"
                )

    log.info("=" * 55)


def log_weekly_pnl():
    """Relatorio semanal de lucro e perda por moeda -- agendado para domingo a meia-noite."""
    now  = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    since_iso  = week_start.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    trades = get_trades_since(since_iso)

    log.info("=" * 55)
    log.info("RELATORIO SEMANAL DE P&L")
    log.info(f"  Periodo: {week_start.strftime('%Y-%m-%d')} a {now.strftime('%Y-%m-%d')}")

    if not trades:
        log.info("  Nenhuma operacao de venda na semana.")
        log.info("=" * 55)
        return

    # Agrupa por simbolo
    by_symbol: dict[str, list[dict]] = {}
    for t in trades:
        sym = t["symbol"]
        by_symbol.setdefault(sym, []).append(t)

    total_pnl_global = 0.0

    for sym, sym_trades in by_symbol.items():
        wins   = [t for t in sym_trades if t["pnl"] > 0]
        losses = [t for t in sym_trades if t["pnl"] <= 0]
        total_pnl = sum(t["pnl"] for t in sym_trades)
        total_pnl_global += total_pnl

        wr = len(wins) / len(sym_trades) * 100 if sym_trades else 0

        log.info(f"\n  [{sym}]")
        log.info(f"    Operacoes:        {len(sym_trades)} ({len(wins)} ganhos / {len(losses)} perdas)")
        log.info(f"    Win rate:         {wr:.1f}%")
        log.info(f"    PnL total:        ${total_pnl:+.4f}")

        if wins:
            best = max(wins, key=lambda t: t["pnl"])
            log.info(f"    Melhor trade:     ${best['pnl']:+.4f} ({best['action']} @ {best['created_at'][:10]})")

        if losses:
            worst = min(losses, key=lambda t: t["pnl"])
            log.info(f"    Pior trade:       ${worst['pnl']:+.4f} ({worst['action']} @ {worst['created_at'][:10]})")

        log.info(f"    Detalhe:")
        for t in sym_trades:
            log.info(
                f"      {t['created_at'][:16]} | {t['action']:<12} | "
                f"entrada: ${t['entry_price']:.4f} -> saida: ${t['exit_price']:.4f} | "
                f"qty: {t['qty']} | PnL: ${t['pnl']:+.4f}"
            )

    log.info(f"\n  PnL GLOBAL DA SEMANA: ${total_pnl_global:+.4f}")
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

        llm_response = {
            "action":        signal.action,
            "confidence":    signal.confidence,
            "sl_percentage": signal.sl_percentage,
            "tp_percentage": signal.tp_percentage,
            "reason":        signal.reason,
        }
        llm_log_id = save_llm_log(symbol, context, llm_response)

        log.info(
            f"[{symbol}] Preco: ${price:.4f} | "
            f"Acao: {signal.action} | "
            f"Confianca: {signal.confidence:.0%} | "
            f"SL: {signal.sl_percentage}% | TP: {signal.tp_percentage}%"
        )
        log.info(f"[{symbol}] LLM: {signal.reason}")

        if not daily_limit_hit:
            execute_trade(symbol, signal, price, llm_log_id=llm_log_id)

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
    schedule.every().sunday.at("00:00").do(log_weekly_pnl)

    while True:
        schedule.run_pending()
        time.sleep(15)
