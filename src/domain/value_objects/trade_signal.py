"""
Value objects de sinais de trade e estatisticas de sessao.
"""

from dataclasses import dataclass


@dataclass
class TradeSignal:
    """Resultado da analise retornado pela LLM (usado apenas internamente como fallback)."""
    action:         str    # "BUY" | "SELL" | "HOLD"
    confidence:     float  # 0.0 a 1.0
    sl_percentage:  float
    tp_percentage:  float
    reason:         str = ""


@dataclass
class SessionStats:
    """Estatisticas acumuladas desde o inicio da sessao."""
    trades_total: int = 0
    trades_win:   int = 0
    trades_loss:  int = 0
    pnl_total:    float = 0.0
    started_at:   str = ""
