"""
Execucao efemera da analise LLM.
Este script roda uma unica vez e encerra, ideal para EventBridge + ECS Fargate.

Mesma logica do ciclo LLM em bot.py: analyze_bot + process_bot_actions (tools).
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from datetime import datetime, timezone

from src.config import SYMBOLS, MAX_DAILY_LOSS_USDT, MIN_CONFIDENCE_SELL, MIN_SETUP_SCORE_FOR_LLM
from src.infra import setup_logging, get_balance
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

        if data.setup_score < MIN_SETUP_SCORE_FOR_LLM and not open_positions.get(symbol):
            log.info(
                f"[{symbol}] Setup score {data.setup_score}/100 abaixo do minimo "
                f"({MIN_SETUP_SCORE_FOR_LLM}) e sem posicoes abertas -- pulando LLM"
            )
            continue

        log.info(
            f"[{symbol}] Analisando... "
            f"(RSI: {data.rsi_1h} | F&G: {data.fear_greed} | setup: {data.setup_score}/100)"
        )

        actions = analyze_bot(data, open_positions)

        context = build_context(data, open_positions)

        tool_called = actions[0]["tool"] if actions else None

        llm_log_id = save_llm_log(
            symbol=symbol,
            context=context,
            response={"actions": actions},
            process="analysis_llm",
            tool_called=tool_called,
        )

        if check_daily_loss_limit():
            log.info(f"[{symbol}] Limite diario atingido — ignorando acoes do LLM")
            continue

        process_bot_actions(
            actions=actions,
            symbol=symbol,
            price=price,
            llm_log_id=llm_log_id,
            execute_buy_fn=execute_buy,
            execute_sell_fn=execute_sell_by_id,
            min_conf_sell=MIN_CONFIDENCE_SELL,
        )

    log.info("Execucao LLM concluida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
