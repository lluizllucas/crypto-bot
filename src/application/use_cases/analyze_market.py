"""
Use case: analisa mercado e toma decisoes via LLM.
Delega todo o raciocinio e execucao para o trade_agent.
Responsabilidade aqui: carregar dados, chamar o agente, registrar o log.
"""

import logging

from src.config import MIN_SETUP_SCORE_FOR_LLM

from src.application.services.market_data_service import get_market_data
from src.application.services.risk_orchestrator_service import open_positions, check_daily_loss_limit

from src.infra.agents.bot_agent import run_bot_agent
from src.infra.persistence.repository import save_llm_log

log = logging.getLogger("bot")


def run_analyze_market(symbol: str) -> None:
    data = get_market_data(symbol)

    if not data:
        return

    if check_daily_loss_limit():
        log.info(f"[{symbol}] Limite diario atingido — pulando LLM")
        return

    # if data.setup_score < MIN_SETUP_SCORE_FOR_LLM and not open_positions.get(symbol):
    #     log.info(f"[{symbol}] Setup score {data.setup_score}/100 abaixo do minimo ({MIN_SETUP_SCORE_FOR_LLM}) — pulando LLM")
    #     return

    result = run_bot_agent(data, open_positions)

    save_llm_log(
        symbol=symbol,
        process="bot",
        context=result.context,
        response={"reasoning": result.reasoning},
        tool_called=result.tool_called,
    )
