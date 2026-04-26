"""
Monitor de stop-loss/take-profit — roda a cada 5 min via EventBridge + ECS Fargate.
Delega toda a logica ao use-case run_monitor_positions.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import datetime, timezone

from src.application.services.risk_orchestrator_service import load_state
from src.application.use_cases.monitor_positions import run_monitor_positions
from src.infra.logging.setup import setup_logging

log = setup_logging()


def main() -> int:
    log.info("-" * 55)
    log.info(f"Monitor SL/TP: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')}")

    load_state()
    run_monitor_positions()

    log.info("Monitor SL/TP concluido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
