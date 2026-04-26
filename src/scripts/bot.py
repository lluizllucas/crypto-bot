"""
Crypto Trading Bot — ciclo principal de analise (a cada 15 min).
Execucao efemera via EventBridge + ECS Fargate.

Responsabilidades:
- Carrega estado do banco
- Itera sobre simbolos e delega para o use-case
- Log de inicio de ciclo

Toda a logica de analise esta em:
  src/application/use_cases/analyze_market.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import datetime, timezone

from src.config import SYMBOLS, MAX_DAILY_LOSS_USDT, TRADE_USDT, MAX_POSITIONS_PER_SYMBOL, MIN_ENTRY_DISTANCE_PCT

from src.application.services.risk_orchestrator_service import load_state, daily_loss_usdt, session_stats
from src.application.use_cases.analyze_market import run_analyze_market
from src.infra.clients.binance.client import get_balance
from src.infra.logging.setup import setup_logging
from src.infra.persistence.database import db

log = setup_logging()


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
        run_analyze_market(symbol)

    log.info("Ciclo concluido.")


if __name__ == "__main__":
    log.info("=" * 55)
    log.info("Crypto Bot iniciado -- Bedrock + Binance TESTNET")
    log.info(f"  Simbolos:              {', '.join(SYMBOLS)}")
    log.info(f"  Analise:               a cada 15 min (bot.py)")
    log.info(f"  Monitor SL/TP:         a cada 5 min (check_sl_tp.py)")
    log.info(f"  USDT por trade:        ${TRADE_USDT}")
    log.info(f"  Max lotes/par:         {MAX_POSITIONS_PER_SYMBOL}")
    log.info(f"  Dist. min. entrada:    {MIN_ENTRY_DISTANCE_PCT}%")
    log.info(f"  SL/TP:                 dinamicos (definidos pela LLM via ATR)")
    log.info(f"  Limite diario:         ${MAX_DAILY_LOSS_USDT}")
    log.info("=" * 55)

    db.create_tables()
    
    load_state()

    try:
        run_cycle()
    except Exception:
        log.exception("Erro na execucao do bot")
        sys.exit(1)

    sys.exit(0)
