"""
Tool de execucao: abre uma nova posicao de compra.
Delega para risk_orchestrator_service.execute_buy.
"""

import logging

log = logging.getLogger(__name__)


def tool_execute_buy(
    symbol:     str,
    confidence: float,
    sl_pct:     float,
    tp_pct:     float,
    reason:     str,
    last_price: float,
    llm_log_id: str | None = None,
) -> bool:
    """Delega a execucao de compra para o risk_orchestrator_service."""
    from src.application.services.risk_orchestrator_service import execute_buy
    
    return execute_buy(
        symbol=symbol,
        confidence=confidence,
        sl_pct=sl_pct,
        tp_pct=tp_pct,
        reason=reason,
        last_price=last_price,
        llm_log_id=llm_log_id,
    )
