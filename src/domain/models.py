"""
Tipos e estruturas de dados compartilhados entre camadas.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Position:
    """Representa um lote aberto de compra em um par."""
    entry_price: float
    qty: float
    sl: float
    tp: float
    ts: datetime
    db_id: str = ""   # id da linha no Supabase (open_positions)


@dataclass
class MarketData:
    """Snapshot de mercado completo enviado para a LLM."""
    symbol: str
    price: float

    # Indicadores tecnicos
    rsi_1h: float
    ema20: float
    ema50: float
    ema200: float
    atr: float
    bb_upper: float
    bb_lower: float

    # Range engine
    range_position_24h: float   # 0.0 (suporte) a 1.0 (resistencia)
    range_position_7d: float
    range_high_24h: float
    range_low_24h: float
    range_high_7d: float
    range_low_7d: float
    range_high_30d: float
    range_low_30d: float

    # Sentimento
    fear_greed: int             # 0-100

    # Volume
    volume_24h: float
    avg_volume_5h: float


@dataclass
class TradeSignal:
    """Resultado da analise retornado pela LLM."""
    action: str             # "BUY" | "SELL" | "HOLD" | "RANGE_MODE" | "TREND_MODE"
    confidence: float       # 0.0 a 1.0
    sl_percentage: float    # stop-loss sugerido pela LLM (%)
    tp_percentage: float    # take-profit sugerido pela LLM (%)
    reason: str = ""


@dataclass
class SessionStats:
    """Estatisticas acumuladas desde o inicio da sessao."""
    trades_total: int = 0
    trades_win: int = 0
    trades_loss: int = 0
    pnl_total: float = 0.0
    started_at: str = ""
