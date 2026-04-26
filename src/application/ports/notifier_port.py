"""
Port (interface) para envio de notificacoes.
Define o contrato que qualquer canal de notificacao deve cumprir.
"""

from typing import Protocol


class NotifierPort(Protocol):
    """Interface para envio de notificacoes."""

    def notify(self, title: str, message: str, color: int = 0x5865F2) -> None:
        """Envia uma notificacao com titulo, mensagem e cor."""
        ...
