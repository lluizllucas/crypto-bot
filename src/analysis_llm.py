"""
Execucao efemera da analise LLM.
Este script roda uma unica vez e encerra, ideal para EventBridge + ECS Fargate.
"""

import sys
from pathlib import Path

# Raiz do projeto (/app no Docker): necessario se rodar `python src/analysis_llm.py`
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from datetime import datetime, timezone

from src.config import SYMBOLS, MAX_DAILY_LOSS_USDT
from src.infra import setup_logging, get_balance
from src.application.market_data import get_market_data
from src.application.llm_analyst import analyze, build_context
from src.application.risk_manager import (
    load_state,
    check_daily_loss_limit,
    execute_trade,
    open_positions,
    daily_loss_usdt,
    session_stats,
)
from src.infra.supabase.repository import save_llm_log


log = setup_logging()


def main() -> int:
    log.info("-" * 55)
    log.info(
        f"Execucao LLM: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')}"
    )
    log.info(
        f"Saldo USDT: ${get_balance('USDT'):.2f} | "
        f"Perda hoje: ${daily_loss_usdt:.2f}/${MAX_DAILY_LOSS_USDT:.2f} | "
        f"Sessao: {session_stats.trades_win}W/{session_stats.trades_loss}L "
        f"PnL: ${session_stats.pnl_total:+.4f}"
    )

    load_state()
    daily_limit_hit = check_daily_loss_limit()

    for symbol in SYMBOLS:
        data = get_market_data(symbol)
        if not data:
            continue

        price = data.price
        for pos in open_positions.get(symbol, []):
            change = (price - pos.entry_price) / pos.entry_price * 100
            log.info(
                f"[{symbol}] Posicao aberta | "
                f"entrada: ${pos.entry_price:.4f} | atual: ${price:.4f} | {change:+.2f}%"
            )

        log.info(f"[{symbol}] Analisando... (RSI: {data.rsi_1h} | F&G: {data.fear_greed})")
        context = build_context(data, open_positions)
        signal = analyze(data, open_positions)

        llm_response = {
            "action": signal.action,
            "confidence": signal.confidence,
            "sl_percentage": signal.sl_percentage,
            "tp_percentage": signal.tp_percentage,
            "reason": signal.reason,
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

    log.info("Execucao LLM concluida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
