"""
Execucao efemera de monitoramento de stop-loss/take-profit.
Roda uma unica vez e encerra — ideal para EventBridge + ECS Fargate (a cada 5 min).

Responsabilidades:
- SL: executa direto, sem LLM
- TP atingido: consulta LLM via tools (sell_position / hold_position)
- Preco proximo do SL (80%): consulta LLM via tool (early_exit)
"""

import sys
from datetime import datetime, timezone

from src.infra import setup_logging
from src.application.risk_manager import load_state, monitor_positions
from src.application.llm_analyst import analyze_monitor
from src.application.market_data import get_market_data

log = setup_logging()


def main() -> int:
    log.info("-" * 55)
    log.info(
        f"Execucao Monitor SL/TP: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')}"
    )

    load_state()

    monitor_positions(
        llm_analyze_fn=analyze_monitor,
        market_data_fn=get_market_data,
    )

    log.info("Execucao Monitor SL/TP concluida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
