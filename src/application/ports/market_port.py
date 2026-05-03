"""
Port (interface) para dados de mercado.
Define o contrato que qualquer fonte de dados de mercado deve cumprir.
"""

from typing import Protocol

from src.domain.value_objects.market_data import MarketData


class MarketPort(Protocol):
    """Interface para busca de snapshot de mercado."""

    def get_market_data(self, symbol: str) -> MarketData | None:
        """Retorna o snapshot completo de mercado para um simbolo."""
        ...
