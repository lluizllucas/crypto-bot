"""
Crypto Trading Bot — ciclo principal de analise (a cada 15 min).
Execucao efemera via EventBridge + ECS Fargate.

Responsabilidades:
- Busca dados de mercado completos
- Consulta LLM via tools para decisoes estrategicas (BUY / SELL por posicao)
- Executa ordens e persiste no banco
- Gera resumo diario e semanal
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from datetime import datetime, timedelta, timezone

from src.infra import setup_logging, get_balance, get_current_price
from src.config import (
    SYMBOLS,
    MAX_DAILY_LOSS_USDT,
    TRADE_USDT,
    MAX_POSITIONS_PER_SYMBOL,
    MIN_ENTRY_DISTANCE_PCT,
    MIN_CONFIDENCE_SELL,
    MIN_SETUP_SCORE_FOR_LLM,
)
from src.application.market_data import get_market_data
from src.application.llm_analyst import analyze_bot, build_context
from src.application.tools import process_bot_actions
from src.application.risk_manager import (
    load_state,
    check_daily_loss_limit,
    execute_buy,
    execute_sell_by_id,
    open_positions,
    daily_loss_usdt,
    session_stats,
)
from src.infra.supabase.repository import get_trades_since, save_llm_log

log = setup_logging()


# ── Resumo diario ─────────────────────────────────────────────────────────────

def log_daily_summary():
    usdt  = get_balance("USDT")
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

        log.info(f"  [{symbol}] Mercado:")
        log.info(f"    Preco:            ${data.price:.4f}")
        log.info(f"    RSI 1h:           {data.rsi_1h:.1f} ({data.rsi_direction})")
        log.info(f"    Fear & Greed:     {data.fear_greed} ({data.fear_greed_label})")
        log.info(f"    MACD:             linha {data.macd_line:.2f} | sinal {data.macd_signal:.2f} | hist {data.macd_histogram:.2f}")
        log.info(f"    Tendencia EMA:    {ema_trend} (EMA20:{data.ema20:.0f} EMA50:{data.ema50:.0f} EMA200:{data.ema200:.0f})")
        log.info(f"    Bollinger:        lower ${data.bb_lower:.0f} / upper ${data.bb_upper:.0f} | %B: {data.bb_pct_b:.2f} | width: {data.bb_width:.4f}")
        log.info(f"    Variacao:         1h {data.change_pct_1h:+.2f}% | 4h {data.change_pct_4h:+.2f}% | 24h {data.change_pct_24h:+.2f}%")
        log.info(f"    Volume ratio:     {data.volume_ratio:.2f}x da media")
        log.info(f"    Range 24h:        ${data.range_low_24h:.0f} - ${data.range_high_24h:.0f} | pos: {data.range_position_24h * 100:.0f}%")
        log.info(f"    Range 7d:         ${data.range_low_7d:.0f} - ${data.range_high_7d:.0f} | pos: {data.range_position_7d * 100:.0f}%")

        plist = open_positions.get(symbol, [])
        for pos in plist:
            change  = (data.price - pos.entry_price) / pos.entry_price * 100
            pnl_est = (data.price - pos.entry_price) * pos.qty
            log.info(
                f"    Posicao: entrada ${pos.entry_price:.4f} | "
                f"atual ${data.price:.4f} | {change:+.2f}% | "
                f"PnL est.: ${pnl_est:+.4f} | "
                f"SL: ${pos.sl:.4f} | TP: ${pos.tp:.4f} | "
                f"holds: {pos.tp_hold_count}"
            )

    log.info("=" * 55)


def log_weekly_pnl():
    now        = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    since_iso  = week_start.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    trades     = get_trades_since(since_iso)

    log.info("=" * 55)
    log.info("RELATORIO SEMANAL DE P&L")
    log.info(f"  Periodo: {week_start.strftime('%Y-%m-%d')} a {now.strftime('%Y-%m-%d')}")

    if not trades:
        log.info("  Nenhuma operacao de venda na semana.")
        log.info("=" * 55)
        return

    by_symbol: dict[str, list[dict]] = {}
    for t in trades:
        by_symbol.setdefault(t["symbol"], []).append(t)

    total_pnl_global = 0.0

    for sym, sym_trades in by_symbol.items():
        wins      = [t for t in sym_trades if t["pnl"] > 0]
        losses    = [t for t in sym_trades if t["pnl"] <= 0]
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
    log.info(f"Ciclo: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')}")
    log.info(
        f"Saldo USDT: ${get_balance('USDT'):.2f} | "
        f"Perda hoje: ${daily_loss_usdt:.2f}/${MAX_DAILY_LOSS_USDT:.2f} | "
        f"Sessao: {session_stats.trades_win}W/{session_stats.trades_loss}L "
        f"PnL: ${session_stats.pnl_total:+.4f}"
    )

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
                f"entrada: ${pos.entry_price:.4f} | atual: ${price:.4f} | {change:+.2f}% | "
                f"holds: {pos.tp_hold_count}"
            )

        log.info(
            f"[{symbol}] Analisando... "
            f"(RSI: {data.rsi_1h} {data.rsi_direction} | "
            f"F&G: {data.fear_greed} {data.fear_greed_label} | "
            f"MACD hist: {data.macd_histogram:+.2f} | "
            f"ADX: {data.adx:.1f} [{data.market_regime}] | "
            f"setup: {data.setup_score}/100)"
        )

        # Pula consulta ao LLM se o setup tecnico estiver abaixo do limiar
        if data.setup_score < MIN_SETUP_SCORE_FOR_LLM and not open_positions.get(symbol):
            log.info(
                f"[{symbol}] Setup score {data.setup_score}/100 abaixo do minimo "
                f"({MIN_SETUP_SCORE_FOR_LLM}) e sem posicoes abertas -- pulando LLM"
            )
            continue

        # Consulta LLM via tools
        actions = analyze_bot(data, open_positions)

        # Salva log LLM (mesmo que nao haja actions)
        context = build_context(data, open_positions)

        tool_called = actions[0]["tool"] if actions else None
        
        llm_log_id = save_llm_log(
            symbol=      symbol,
            context=     context,
            response=    {"actions": actions},
            process=     "bot",
            tool_called= tool_called,
        )

        if check_daily_loss_limit():
            log.info(f"[{symbol}] Limite diario atingido — ignorando acoes do LLM")
            continue

        # Despacha acoes do LLM para as funcoes de execucao via tools.py
        process_bot_actions(
            actions=        actions,
            symbol=         symbol,
            price=          price,
            llm_log_id=     llm_log_id,
            execute_buy_fn= execute_buy,
            execute_sell_fn=execute_sell_by_id,
            min_conf_sell=  MIN_CONFIDENCE_SELL,
        )

    log.info("Ciclo concluido.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("=" * 55)
    log.info("Crypto Bot iniciado -- OpenRouter + Binance TESTNET")
    log.info(f"  Simbolos:              {', '.join(SYMBOLS)}")
    log.info(f"  Analise:               a cada 15 min (bot.py)")
    log.info(f"  Monitor SL/TP:         a cada 5 min (check_sl_tp.py)")
    log.info(f"  USDT por trade:        ${TRADE_USDT}")
    log.info(f"  Max lotes/par:         {MAX_POSITIONS_PER_SYMBOL}")
    log.info(f"  Dist. min. entrada:    {MIN_ENTRY_DISTANCE_PCT}%")
    log.info(f"  SL/TP:                 dinamicos (definidos pela LLM via ATR)")
    log.info(f"  Limite diario:         ${MAX_DAILY_LOSS_USDT}")
    log.info("=" * 55)

    load_state()

    try:
        run_cycle()
        log_daily_summary()
        log_weekly_pnl()
    except Exception:
        log.exception("Erro na execucao do bot")
        sys.exit(1)

    sys.exit(0)
