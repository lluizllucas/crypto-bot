"""
Fear & Greed Index via Alternative.me (gratuito, sem autenticacao).

Escala:
  0-25  -> Medo extremo
  25-50 -> Medo
  50-75 -> Ganancia
  75-100 -> Ganancia extrema
"""

import logging
import requests

log = logging.getLogger(__name__)

_URL = "https://api.alternative.me/fng/"


def get_fear_greed() -> int:
    """
    Retorna o valor atual do Fear & Greed Index (0-100).
    Retorna 50 (neutro) em caso de erro para nao bloquear o ciclo.
    """
    try:
        response = requests.get(_URL, timeout=5)
        response.raise_for_status()

        value = int(response.json()["data"][0]["value"])

        log.info(f"Fear & Greed Index: {value}")

        return value

    except Exception as e:
        log.warning(
            f"Erro ao buscar Fear & Greed Index: {e} -- usando 50 (neutro)")
        return 50
