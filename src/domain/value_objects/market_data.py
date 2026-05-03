"""
Value objects de mercado: MarketData e Candle.
"""

from dataclasses import dataclass, field


@dataclass
class Candle:
    """Resumo de uma vela OHLCV."""
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float


@dataclass
class MarketData:
    """Snapshot de mercado completo enviado para a LLM."""
    symbol: str
    price:  float

    # Indicadores tecnicos
    rsi_1h:   float
    ema20:    float
    ema50:    float
    ema200:   float
    atr:      float
    bb_upper: float
    bb_lower: float
    bb_mid:   float
    bb_width: float   # (bb_upper - bb_lower) / bb_mid — compressao das bandas
    bb_pct_b: float   # (price - bb_lower) / (bb_upper - bb_lower) — posicao relativa

    # MACD
    macd_line:      float
    macd_signal:    float
    macd_histogram: float

    # Variacao percentual recente
    change_pct_1h:  float
    change_pct_4h:  float
    change_pct_24h: float

    # Volume
    volume_24h:    float
    avg_volume_5h: float
    volume_ratio:  float   # volume_24h / media historica

    # Range engine
    range_position_24h: float   # 0.0 (suporte) a 1.0 (resistencia)
    range_position_7d:  float
    range_high_24h:     float
    range_low_24h:      float
    range_high_7d:      float
    range_low_7d:       float
    range_high_30d:     float
    range_low_30d:      float

    # Sentimento
    fear_greed:       int    # 0-100
    fear_greed_label: str    # "Extreme Fear" | "Fear" | "Neutral" | "Greed" | "Extreme Greed"

    # Price action recente (ultimas 4 velas)
    recent_candles: list = field(default_factory=list)   # lista de Candle

    # Direcao do RSI (ultimas 3 velas)
    rsi_direction:  str  = "flat"    # "rising" | "falling" | "flat"
    rsi_divergence: str  = "none"    # "bullish" | "bearish" | "none"

    # ADX — forca e regime de mercado
    adx:            float = 0.0
    plus_di:        float = 0.0
    minus_di:       float = 0.0
    market_regime:  str   = "undefined"  # "trending" | "ranging" | "undefined"

    # Score do setup pre-LLM (0-100)
    setup_score:    int   = 0
