"""
Logica pura de gestao de risco — sem dependencias externas (sem I/O, sem DB, sem Binance).
Calculos de thresholds, limites e ajustes de posicao.
"""

from src.config import TP_HOLD_MIN_CONFIDENCE


def tp_threshold(hold_count: int) -> float:
    """Retorna o threshold de confianca minimo para a N-esima tentativa de hold."""
    thresholds = TP_HOLD_MIN_CONFIDENCE
    if hold_count < len(thresholds):
        return thresholds[hold_count]
    return thresholds[-1]


def is_daily_limit_reached(daily_loss_usdt: float, max_daily_loss: float) -> bool:
    """Retorna True se o limite de perda diaria foi atingido."""
    return daily_loss_usdt >= max_daily_loss


def is_near_daily_limit(daily_loss_usdt: float, max_daily_loss: float, threshold: float = 0.8) -> bool:
    """Retorna True se a perda diaria esta acima de threshold do limite."""
    return daily_loss_usdt >= max_daily_loss * threshold


def calc_sl_price(entry_price: float, sl_pct: float) -> float:
    """Calcula o preco de stop-loss a partir do percentual."""
    return entry_price * (1 - sl_pct / 100)


def calc_tp_price(entry_price: float, tp_pct: float) -> float:
    """Calcula o preco de take-profit a partir do percentual."""
    return entry_price * (1 + tp_pct / 100)


def is_near_sl(entry_price: float, sl_price: float, current_price: float,
               threshold: float = 0.8) -> bool:
    """Retorna True se o preco atual esta a `threshold` do caminho ate o SL."""
    sl_distance_total = entry_price - sl_price
    sl_distance_atual = entry_price - current_price
    if sl_distance_total <= 0:
        return False
    return sl_distance_atual / sl_distance_total >= threshold


def calc_pnl(entry_price: float, current_price: float, qty: float) -> float:
    """Calcula o PnL de uma posicao."""
    return (current_price - entry_price) * qty
