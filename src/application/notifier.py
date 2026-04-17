"""
Notificacoes via Discord webhook.
"""


import logging
log = logging.getLogger("bot")
from datetime import datetime, timezone

from src.config import DISCORD_WEBHOOK_URL


def discord_notify(title: str, message: str, color: int = 0x5865F2):
    """
    Envia uma notificacao para o canal do Discord via webhook.
    color: 0x57F287 (verde), 0xED4245 (vermelho), 0xFEE75C (amarelo), 0x5865F2 (azul)
    """
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        import requests

        payload = {
            "embeds": [{
                "title": title,
                "description": message,
                "color": color,
                "footer": {"text": "Trading Bot"},
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            }]
        }

        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)

    except Exception as e:
        log.warning(f"Erro ao enviar notificacao Discord: {e}")
