"""
Auditoria de tools — chama todas as tools de consulta de mercado e portfolio
e loga os resultados. Util para verificar se todas as tools estao funcionando
corretamente antes de colocar o bot em producao.
"""

import os
import sys
import json

from src.config import SYMBOLS

from src.infra.agents.tools.market.get_candles import query_candles
from src.infra.agents.tools.portfolio.get_positions import query_positions
from src.infra.agents.tools.market.get_market_data import (
    query_rsi_history,
    query_volume_profile,
    query_ema_history,
    query_recent_highs_lows,
    query_volatility_history,
    query_range_breakdown,
    query_fear_greed_history,
)

from src.infra.logging.setup import setup_logging

log = setup_logging()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

SYMBOL = SYMBOLS[0]


def _print(tool: str, result: dict):
    has_error = "error" in result
    status = "FALHOU" if has_error else "OK"

    log.info(f"  [{status}] {tool}")

    if has_error:
        log.warning(f"    {result['error']}")
    else:
        preview = json.dumps(result, ensure_ascii=False, indent=2)
        
        for line in preview.splitlines():
            log.info(f"    {line}")


def run():
    log.info("=" * 55)
    log.info(f"AUDITORIA DE TOOLS — simbolo: {SYMBOL}")
    log.info("=" * 55)

    log.info("\n--- market/get_candles ---")
    _print("get_candles(1h, 5)", query_candles(SYMBOL, "1h", 5))
    _print("get_candles(4h, 5)", query_candles(SYMBOL, "4h", 5))
    _print("get_candles(15m, 5)", query_candles(SYMBOL, "15m", 5))

    log.info("\n--- market/get_market_data ---")
    _print("get_rsi_history(10)", query_rsi_history(SYMBOL, 10))
    _print("get_volume_profile(12)", query_volume_profile(SYMBOL, 12))
    _print("get_ema_history(ema=20, p=10)", query_ema_history(SYMBOL, 20, 10))
    _print("get_ema_history(ema=50, p=10)", query_ema_history(SYMBOL, 50, 10))
    _print("get_ema_history(ema=200, p=5)", query_ema_history(SYMBOL, 200, 5))
    _print("get_recent_highs_lows(24)", query_recent_highs_lows(SYMBOL, 24))
    _print("get_volatility_history(10)", query_volatility_history(SYMBOL, 10))
    _print("get_range_breakdown([24,168])",
           query_range_breakdown(SYMBOL, [24, 168]))
    _print("get_fear_greed_history(7)",     query_fear_greed_history(7))

    log.info("\n--- portfolio/get_positions ---")
    _print("get_positions", query_positions(SYMBOL))

    log.info("\n" + "=" * 55)
    log.info("Auditoria concluida.")
    log.info("=" * 55)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log.exception("Erro na auditoria de tools")
        sys.exit(1)

    sys.exit(0)
