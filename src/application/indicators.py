"""
Indicadores tecnicos calculados sobre DataFrames de velas.
Usado pelo backtest e pelo bot ao vivo via market_data.
"""

import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adiciona ao DataFrame os indicadores usados para gerar sinais:
    - EMA 20 / 50 / 200
    - SMA 5 / 20 (usados pelo backtest)
    - Volume medio 5h
    - Variacao percentual da ultima hora
    - RSI 14 periodos
    - ATR 14 periodos
    - Bollinger Bands (20 periodos, 2 desvios)
    """
    df = df.copy()

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    # EMAs (identificacao de tendencia)
    df["ema20"] = close.ewm(span=20,  adjust=False).mean()
    df["ema50"] = close.ewm(span=50,  adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()

    # SMAs simples (usados pelo signal_generator no backtest)
    df["sma5"] = close.rolling(5).mean()
    df["sma20"] = close.rolling(20).mean()

    # Volume medio 5h
    df["vol_avg5"] = df["volume"].rolling(5).mean()

    # Variacao percentual da ultima hora
    df["close_pct1h"] = close.pct_change() * 100

    # RSI 14 periodos
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, float("inf"))

    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR 14 periodos
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    df["atr"] = tr.rolling(14).mean()

    # Bollinger Bands (20 periodos, 2 desvios padrao)
    bb_mean = close.rolling(20).mean()
    bb_std = close.rolling(20).std()

    df["bb_upper"] = bb_mean + 2 * bb_std
    df["bb_lower"] = bb_mean - 2 * bb_std
    df["bb_mid"] = bb_mean

    return df.dropna()
