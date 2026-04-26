"""
Monitor de stop-loss/take-profit — roda a cada 5 min via EventBridge + ECS Fargate.
Delega toda a logica ao use-case run_monitor_positions.
"""

import os
import sys

from datetime import datetime, timezone

from src.infra.logging.setup import setup_logging
from src.application.services.risk_orchestrator_service import load_state
from src.application.use_cases.monitor_positions import run_monitor_positions

log = setup_logging()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


if __name__ == "__main__":
    log.info("=" * 55)
    log.info(
        f"Monitor SL/TP iniciado: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')}")
    log.info("=" * 55)

    load_state()

    try:
        run_monitor_positions()
    except Exception:
        log.exception("Erro na execucao do monitor SL/TP")
        sys.exit(1)

    sys.exit(0)
