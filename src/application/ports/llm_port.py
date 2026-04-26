"""
Port (interface) para o agente LLM.
Define o contrato que qualquer provedor LLM deve cumprir.
"""

from typing import Protocol

from src.domain.value_objects.market_data import MarketData
from src.domain.entities.position import Position


class LLMPort(Protocol):
    """Interface para analise de mercado via LLM."""

    def run_bot_agent(
        self,
        data: MarketData,
        open_positions: dict,
    ) -> object:
        """Analise estrategica para o ciclo principal. Executa buy/sell internamente."""
        ...

    def run_monitor_agent(
        self,
        data: MarketData,
        open_positions: dict,
        triggered_positions: list[Position],
        trigger_type: str,
        apply_tp_hold_fn,
        close_position_fn,
        tp_threshold: float,
        min_conf_early: float,
    ) -> object:
        """Analise para o monitor SL/TP. Executa hold/sell/early_exit internamente."""
        ...
