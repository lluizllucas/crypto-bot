"""
Use case: monitorar posicoes abertas para SL/TP.
Cada cenario delega para um agente especializado.
"""

import logging

from src.config import SL_EARLY_EXIT_THRESHOLD

from src.application.services.market_data_service import get_market_data
from src.application.services.notifier_service import discord_notify
from src.application.services.risk_orchestrator_service import open_positions
from src.infra.agents.tools.execution.execute_sell import close_position_at_index

from src.infra.agents.tp_agent import run_tp_agent
from src.infra.agents.early_exit_agent import run_early_exit_agent
from src.infra.clients.binance.client import get_current_price
from src.infra.persistence.repository import save_llm_log

log = logging.getLogger("bot")


def _get_price_with_retry(symbol: str, attempts: int = 3) -> float | None:
    for attempt in range(1, attempts + 1):
        price = get_current_price(symbol)
        if price is not None:
            return price
        if attempt < attempts:
            log.warning(f"[MONITOR] Falha ao buscar preco de {symbol} (tentativa {attempt}/{attempts})")

    log.error(f"[MONITOR] Nao foi possivel obter preco de {symbol} apos {attempts} tentativas")

    discord_notify(
        title=f"Erro de preco -- {symbol}",
        message=f"Nao foi possivel obter preco apos {attempts} tentativas. Posicoes nao monitoradas neste ciclo.",
        color=0xED4245,
    )
    
    return None


def _handle_tp(symbol: str, idx: int, pos, price: float):
    data = get_market_data(symbol)
    if data is None:
        log.warning(f"[MONITOR] Falha ao buscar dados de mercado — vendendo no TP")
        close_position_at_index(symbol, idx, price, "TAKE-PROFIT")
        return

    result = run_tp_agent(data=data, open_positions=open_positions, pos=pos)

    save_llm_log(
        symbol=symbol,
        context=result.context,
        response={"reasoning": result.reasoning},
        process="tp",
        tool_called=result.tool_called,
        position_id=pos.db_id or None,
    )

    if not result.executed:
        log.info(f"[MONITOR] [{symbol}] LLM nao acionou tool para TP — vendendo")
        close_position_at_index(symbol, idx, price, "TAKE-PROFIT")


def _handle_early_exit(symbol: str, pos):
    data = get_market_data(symbol)
    if data is None:
        return

    result = run_early_exit_agent(data=data, open_positions=open_positions, pos=pos)

    save_llm_log(
        symbol=symbol,
        context=result.context,
        response={"reasoning": result.reasoning},
        process="early_exit",
        tool_called=result.tool_called,
        position_id=pos.db_id or None,
    )


def run_monitor_positions() -> None:
    """
    Executa o ciclo de monitoramento SL/TP:
    - SL: executa direto, sem LLM
    - TP atingido: run_tp_agent decide hold ou sell
    - Preco proximo do SL (80%): run_early_exit_agent decide sair ou manter
    """
    total = sum(len(v) for v in open_positions.values())
    log.info(f"[MONITOR] Iniciando ciclo — {total} posicao(oes) abertas em {len(open_positions)} par(es)")

    if not open_positions:
        log.info("[MONITOR] Ciclo concluido")
        return

    try:
        for symbol in list(open_positions.keys()):
            price = _get_price_with_retry(symbol)
            if price is None:
                continue

            positions = open_positions[symbol]

            for idx in range(len(positions) - 1, -1, -1):
                pos    = positions[idx]
                entry  = pos.entry_price
                change = (price - entry) / entry * 100

                if price <= pos.sl:
                    log.warning(
                        f"[MONITOR] [{symbol}] STOP-LOSS @ ${price:.4f} "
                        f"(entrada ${entry:.4f}, {change:+.2f}%)"
                    )
                    close_position_at_index(symbol, idx, price, "STOP-LOSS")
                    continue

                if price >= pos.tp:
                    log.info(
                        f"[MONITOR] [{symbol}] TP ATINGIDO @ ${price:.4f} "
                        f"(entrada ${entry:.4f}, {change:+.2f}%) — consultando LLM"
                    )
                    _handle_tp(symbol, idx, pos, price)
                    continue

                sl_distance_total = entry - pos.sl
                sl_distance_atual = entry - price
                if sl_distance_total > 0 and sl_distance_atual / sl_distance_total >= SL_EARLY_EXIT_THRESHOLD:
                    log.warning(
                        f"[MONITOR] [{symbol}] PRECO PROXIMO DO SL ({sl_distance_atual / sl_distance_total:.0%}) "
                        f"@ ${price:.4f} — consultando LLM para early exit"
                    )
                    _handle_early_exit(symbol, pos)
                    continue

                log.info(
                    f"[MONITOR] [{symbol}] OK | entrada: ${entry:.4f} | "
                    f"atual: ${price:.4f} | {change:+.2f}%"
                )

    except Exception:
        log.exception("[MONITOR] Erro inesperado no ciclo de monitoramento")
        raise

    log.info("[MONITOR] Ciclo concluido")
