"""
Geracao de sinais tecnicos (sem LLM).
Usado pelo backtest e pode ser reaproveitado pelo bot ao vivo como pre-filtro.
"""

import pandas as pd

from src.domain.value_objects.trade_signal import TradeSignal


def generate_signal(row: pd.Series) -> TradeSignal:
    """
    Gera sinal com base em indicadores tecnicos.

    BUY:  SMA5 > SMA20, volume acima da media, RSI 40-65, close_pct1h > 0
    SELL: SMA5 < SMA20, volume acima da media, RSI > 60 ou RSI < 35
    HOLD: nenhuma condicao satisfeita
    """
    sma_bull = row["sma5"] > row["sma20"]
    vol_ratio = row["volume"] / row["vol_avg5"] if row["vol_avg5"] > 0 else 0
    rsi = row["rsi"]
    pct1h = row["close_pct1h"]

    if sma_bull and vol_ratio >= 1.0 and 40 <= rsi <= 65 and pct1h > 0:
        confidence = 0.55

        if rsi < 60:
            confidence += 0.10
        if pct1h > 0.3:
            confidence += 0.10
        if vol_ratio >= 1.5:
            confidence += 0.10

        return TradeSignal(signal="BUY", confidence=round(min(confidence, 0.95), 2))

    if not sma_bull and vol_ratio >= 1.0 and (rsi > 60 or rsi < 35):
        confidence = 0.55

        if rsi > 65 or rsi < 30:
            confidence += 0.15
        if pct1h < -0.3:
            confidence += 0.10

        return TradeSignal(signal="SELL", confidence=round(min(confidence, 0.95), 2))

    return TradeSignal(signal="HOLD", confidence=0.0)
