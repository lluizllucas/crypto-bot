"""
Tool de consulta: retorna posicoes abertas no banco.
"""

import logging

from src.infra.persistence.repository import get_positions_by_symbol

log = logging.getLogger(__name__)


def query_positions(symbol: str) -> dict:
    """Retorna as posicoes abertas no banco para um simbolo."""
    positions = get_positions_by_symbol(symbol)
    result = [
        {
            "db_id":         pos.db_id,
            "entry_price":   pos.entry_price,
            "qty":           pos.qty,
            "sl":            pos.sl,
            "tp":            pos.tp,
            "tp_hold_count": pos.tp_hold_count,
        }
        for pos in positions
    ]

    return {
        "symbol":    symbol,
        "count":     len(result),
        "positions": result,
    }
