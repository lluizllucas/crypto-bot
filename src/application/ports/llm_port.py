"""
Port (interface) para os agentes LLM.
Define o contrato que qualquer provedor LLM deve cumprir.
"""

from typing import Protocol

from src.domain.value_objects.market_data import MarketData
from src.domain.entities.position import Position


class LLMPort(Protocol):

    def run_bot_agent(self, data: MarketData, positions: list[Position]) -> object:
        """Analise estrategica para o ciclo principal. Executa buy/sell internamente."""
        ...

    def run_tp_agent(self, data: MarketData, pos: Position) -> object:
        """Decide hold ou sell quando o TP e atingido. Executa internamente."""
        ...

    def run_early_exit_agent(self, data: MarketData, pos: Position) -> object:
        """Decide sair ou manter quando o preco se aproxima do SL. Executa internamente."""
        ...
