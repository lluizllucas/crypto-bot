"""
Execucao efemera de monitoramento de stop-loss/take-profit.
Este script roda uma unica vez e encerra, ideal para EventBridge + ECS Fargate.
"""

import sys
from datetime import datetime, timezone

from src.infra import setup_logging
from src.application.risk_manager import load_state, monitor_positions


log = setup_logging()


def main() -> int:
    log.info("-" * 55)
    log.info(
        f"Execucao SL/TP: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')}"
    )
    load_state()
    monitor_positions()
    log.info("Execucao SL/TP concluida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
