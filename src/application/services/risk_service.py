"""
Verificacao de limite diario de perda.
"""

import logging

from datetime import datetime, timezone

from src.config import MAX_DAILY_LOSS_USDT

from src.domain.value_objects.trade_signal import SessionStats

from src.infra.clients.discord.client import discord_notify
from src.infra.persistence.repository import get_daily_loss

log = logging.getLogger("bot")


session_stats = SessionStats(
    started_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
)


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


