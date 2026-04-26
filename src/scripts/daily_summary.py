"""
Resumo diario do bot — roda 1x/dia via EventBridge + ECS Fargate.
Loga saldo, win rate, PnL da sessao e snapshot de mercado por simbolo.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import datetime, timezone

from src.config import SYMBOLS, MAX_DAILY_LOSS_USDT

from src.application.services.market_data_service import get_market_data
from src.application.services.risk_service import session_stats
from src.infra.persistence.repository import get_daily_loss, load_positions
from src.infra.clients.binance.client import get_balance
from src.infra.logging.setup import setup_logging

log = setup_logging()


def run():
    open_positions = load_positions()
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
    log.info(f"  Perda acumulada:    ${get_daily_loss(datetime.now(timezone.utc).strftime('%Y-%m-%d')):.2f} / ${MAX_DAILY_LOSS_USDT:.2f}")

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

        for pos in open_positions.get(symbol, []):
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


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log.exception("Erro no resumo diario")
        sys.exit(1)

    sys.exit(0)
