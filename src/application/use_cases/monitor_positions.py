"""
Use case: monitorar posicoes abertas para SL/TP.
Delega raciocinio e execucao ao trade_agent via run_monitor_agent.
"""

from src.application.services.risk_orchestrator_service import monitor_positions
from src.application.services.market_data_service import get_market_data
from src.infra.agents.trade_agent import run_monitor_agent


def run_monitor_positions() -> None:
    """
    Executa o ciclo de monitoramento SL/TP:
    - SL: executa direto, sem LLM
    - TP atingido: agente decide hold/sell e executa
    - Preco proximo do SL (80%): agente decide early_exit e executa
    """
    monitor_positions(
        llm_analyze_fn=run_monitor_agent,
        market_data_fn=get_market_data,
    )
