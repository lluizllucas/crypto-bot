"""
Fear & Greed Index via Alternative.me (gratuito, sem autenticacao).

Escala:
  0-25  -> Extreme Fear
  25-50 -> Fear
  50-75 -> Greed
  75-100 -> Extreme Greed
"""

import logging
import requests

log = logging.getLogger(__name__)

_URL = "https://api.alternative.me/fng/"


def _label(value: int) -> str:
    if value <= 25:
        return "Extreme Fear"
    if value <= 50:
        return "Fear"
    if value <= 75:
        return "Greed"
    return "Extreme Greed"


def get_fear_greed() -> tuple[int, str]:
    """
    Retorna (value, label) do Fear & Greed Index atual.
    Retorna (50, "Neutral") em caso de erro para nao bloquear o ciclo.
    """
    try:
        response = requests.get(_URL, timeout=5)
        response.raise_for_status()

        data  = response.json()["data"][0]
        value = int(data["value"])
        label = _label(value)

        log.info(f"Fear & Greed Index: {value} ({label})")

        return value, label

    except Exception as e:
        log.warning(
            f"Erro ao buscar Fear & Greed Index: {e} -- usando 50 (Neutral)")
        return 50, "Neutral"
