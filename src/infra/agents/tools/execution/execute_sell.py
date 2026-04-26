"""
Tool de execucao: fecha uma posicao de venda pelo db_id.
Delega para risk_orchestrator_service.execute_sell_by_id.
"""

import logging

log = logging.getLogger(__name__)


def tool_execute_sell(
    symbol:          str,
    position_id:     str,
    confidence:      float,
    reason:          str,
    current_price:   float,
    exit_llm_log_id: str | None = None,
) -> bool:
    """Delega a execucao de venda para o risk_orchestrator_service."""
    from src.application.services.risk_orchestrator_service import execute_sell_by_id
    
    return execute_sell_by_id(
        symbol=symbol,
        position_id=position_id,
        confidence=confidence,
        reason=reason,
        current_price=current_price,
        exit_llm_log_id=exit_llm_log_id,
    )
