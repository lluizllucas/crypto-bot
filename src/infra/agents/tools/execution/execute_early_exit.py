"""
Tool de execucao: early_exit — sai antecipadamente quando o preco se aproxima do SL.
Reutiliza close_position_at_index com reason="EARLY-EXIT".
"""

import logging

from src.config import MIN_CONFIDENCE_EARLY_EXIT

from src.application.services.risk_orchestrator_service import open_positions

from src.infra.agents.tools.execution.execute_sell import close_position_at_index

log = logging.getLogger("bot")


def tool_early_exit(
    symbol:          str,
    position_id:     str,
    confidence:      float,
    price:           float,
    exit_llm_log_id: str | None = None,
) -> bool:
    if confidence < MIN_CONFIDENCE_EARLY_EXIT:
        log.info(
            f"[EARLY-EXIT] Confianca insuficiente "
            f"({confidence:.2f} < {MIN_CONFIDENCE_EARLY_EXIT:.2f}) — mantendo posicao"
        )
        return True

    positions = open_positions.get(symbol, [])
    
    for idx, pos in enumerate(positions):
        if pos.db_id == position_id:
            log.warning(
                f"[EARLY-EXIT] Saida antecipada solicitada pelo LLM "
                f"(conf {confidence:.2f}) @ ${price:.4f}"
            )
            close_position_at_index(symbol, idx, price, "EARLY-EXIT", exit_llm_log_id, confidence)
            return True

    log.warning(f"[EARLY-EXIT] Posicao {position_id} nao encontrada")
    return False
