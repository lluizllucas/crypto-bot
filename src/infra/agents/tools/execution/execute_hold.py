"""
Tool de execucao: hold_position no TP.
Aplica trailing SL/TP quando o LLM decide segurar a posicao lucrativa.
"""

import logging

from src.config import TP_HOLD_MIN_CONFIDENCE, TP_EXTENSION_MULTIPLIER

from src.application.services.risk_orchestrator_service import open_positions
from src.infra.clients.discord.client import discord_notify

from src.infra.persistence.repository import update_position
from src.infra.agents.tools.execution.execute_sell import close_position_at_index

log = logging.getLogger("bot")


def _get_tp_threshold(hold_count: int) -> float:
    thresholds = TP_HOLD_MIN_CONFIDENCE

    if hold_count < len(thresholds):
        return thresholds[hold_count]
    
    return thresholds[-1]


def _apply_tp_hold(symbol: str, pos) -> None:
    pos.tp_hold_count += 1

    if pos.tp_hold_count == 1:
        pos.sl = pos.entry_price
    else:
        pos.sl = pos.tp

    pos.tp = pos.tp * TP_EXTENSION_MULTIPLIER

    update_position(pos)

    log.info(
        f"[{symbol}] TP hold #{pos.tp_hold_count} aplicado | "
        f"Novo SL: ${pos.sl:.4f} | Novo TP: ${pos.tp:.4f}"
    )

    discord_notify(
        title=f"TP Hold #{pos.tp_hold_count} -- {symbol}",
        message=(
            f"**LLM segurou no TP** (tentativa {pos.tp_hold_count})\n"
            f"**Novo SL:** ${pos.sl:.4f}\n"
            f"**Novo TP:** ${pos.tp:.4f}"
        ),
        color=0x5865F2,
    )


def tool_hold_position(symbol: str, position_id: str, confidence: float, price: float) -> bool:
    positions = open_positions.get(symbol, [])

    for idx, pos in enumerate(positions):
        if pos.db_id == position_id:
            threshold = _get_tp_threshold(pos.tp_hold_count)

            if confidence >= threshold:
                log.info(
                    f"[TP] LLM segura no TP "
                    f"(conf {confidence:.2f} >= {threshold:.2f}, tentativa #{pos.tp_hold_count + 1})"
                )
                _apply_tp_hold(symbol, pos)
            else:
                log.info(
                    f"[TP] Confianca insuficiente para hold "
                    f"({confidence:.2f} < {threshold:.2f}) — vendendo no TP"
                )
                close_position_at_index(symbol, idx, price, "TAKE-PROFIT")

            return True

    log.warning(f"[TP] Posicao {position_id} nao encontrada para HOLD")
    return False
