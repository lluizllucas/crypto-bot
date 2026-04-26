"""
Tool de consulta: retorna posicoes abertas em memoria.
"""

import logging

log = logging.getLogger(__name__)


def query_positions(symbol: str) -> dict:
    """
    Retorna as posicoes abertas em memoria para um simbolo.
    Importacao lazy para evitar import circular com risk_orchestrator_service.
    """
    from src.application.services.risk_orchestrator_service import open_positions

    positions = open_positions.get(symbol, [])
    result = []
    for pos in positions:
        result.append({
            "db_id":        pos.db_id,
            "entry_price":  pos.entry_price,
            "qty":          pos.qty,
            "sl":           pos.sl,
            "tp":           pos.tp,
            "tp_hold_count": pos.tp_hold_count,
        })

    return {
        "symbol":    symbol,
        "count":     len(result),
        "positions": result,
    }
