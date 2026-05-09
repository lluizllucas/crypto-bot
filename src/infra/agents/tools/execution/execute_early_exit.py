"""
Tool de execucao: early_exit — sai antecipadamente quando o preco se aproxima do SL.
Reutiliza close_position_by_id com reason="EARLY-EXIT".
"""

import logging

from src.config import MIN_CONFIDENCE_EARLY_EXIT

from src.infra.persistence.repository import get_position_by_id
from src.infra.agents.tools.execution.execute_sell import close_position_by_id

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

    pos = get_position_by_id(position_id)
    if not pos:
        log.warning(f"[EARLY-EXIT] Posicao {position_id} nao encontrada")
        return False

    pnl_realizado = (price - pos.entry_price) * pos.qty

    log.warning(
        f"[EARLY-EXIT] Saida antecipada solicitada pelo LLM "
        f"(conf {confidence:.2f}) @ ${price:.4f} | "
        f"entrada: ${pos.entry_price:.4f} | "
        f"PnL realizado: ${pnl_realizado:+.4f}"
    )
    close_position_by_id(symbol, position_id, price, "EARLY-EXIT", exit_llm_log_id, confidence)
    return True
