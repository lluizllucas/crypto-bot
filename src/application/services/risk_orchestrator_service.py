"""
Gestao de risco: posicoes abertas em memoria, limite diario de perda
e estatisticas de sessao.
"""

import logging

from datetime import datetime, timezone

from src.config import MAX_DAILY_LOSS_USDT

from src.domain.entities.position import Position
from src.domain.value_objects.trade_signal import SessionStats

from src.infra.clients.discord.client import discord_notify

from src.infra.persistence.repository import (
    load_positions,
    get_daily_loss,
    upsert_daily_loss,
)

log = logging.getLogger("bot")


# Posicoes abertas em memoria -- carregadas do Supabase na inicializacao
# { "BTCUSDT": [Position, ...] }
open_positions: dict[str, list[Position]] = {}

# Estatisticas da sessao
session_stats = SessionStats(
    started_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
)


# ── Inicializacao ─────────────────────────────────────────────────────────────

def load_state():
    """
    Carrega posicoes abertas do Supabase para a memoria.
    Deve ser chamado uma vez ao iniciar o bot.
    """
    global open_positions

    open_positions = load_positions()
    total = sum(len(v) for v in open_positions.values())

    if total:
        log.info(f"Estado restaurado: {total} posicao(oes) em {len(open_positions)} par(es)")
    else:
        log.info("Nenhuma posicao aberta encontrada no banco.")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_loss = get_daily_loss(today)
    if daily_loss > 0:
        log.info(f"Perda diaria restaurada: ${daily_loss:.2f} / ${MAX_DAILY_LOSS_USDT:.2f}")


# ── Limite diario ─────────────────────────────────────────────────────────────

def check_daily_loss_limit() -> bool:
    """Retorna True se o limite de perda diaria foi atingido."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_loss = get_daily_loss(today)

    if daily_loss >= MAX_DAILY_LOSS_USDT:
        log.warning(
            f"Limite de perda diaria atingido "
            f"(${daily_loss:.2f} / ${MAX_DAILY_LOSS_USDT:.2f}) -- sem novas ordens hoje"
        )
        return True

    if daily_loss >= MAX_DAILY_LOSS_USDT * 0.8:
        log.warning(
            f"Atencao: perda diaria em {daily_loss / MAX_DAILY_LOSS_USDT:.0%} do limite "
            f"(${daily_loss:.2f} / ${MAX_DAILY_LOSS_USDT:.2f})"
        )
        discord_notify(
            title="Alerta de perda diaria",
            message=(
                f"Perda acumulada: **${daily_loss:.2f}** de **${MAX_DAILY_LOSS_USDT:.2f}**\n"
                f"Limite em {daily_loss / MAX_DAILY_LOSS_USDT:.0%} — proximas perdas bloqueiam novas ordens."
            ),
            color=0xFEE75C,
        )

    return False


def record_loss(amount: float):
    """Acumula perda do dia no banco."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    current = get_daily_loss(today)
    upsert_daily_loss(today, current + abs(amount))

