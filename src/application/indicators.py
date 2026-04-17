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
    - Bollinger Bands (20 periodos, 2 desvios) + BB Width + %B
    - MACD (12, 26, 9)
    """
    df = df.copy()

    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)

    # EMAs (identificacao de tendencia)
    df["ema20"]  = close.ewm(span=20,  adjust=False).mean()
    df["ema50"]  = close.ewm(span=50,  adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()

    # SMAs simples (usados pelo signal_generator no backtest)
    df["sma5"]  = close.rolling(5).mean()
    df["sma20"] = close.rolling(20).mean()

    # Volume medio 5h
    df["vol_avg5"] = df["volume"].rolling(5).mean()

    # Variacao percentual da ultima hora
    df["close_pct1h"] = close.pct_change() * 100

    # RSI 14 periodos
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, float("inf"))
    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR 14 periodos
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()

    # Bollinger Bands (20 periodos, 2 desvios padrao)
    bb_mean      = close.rolling(20).mean()
    bb_std       = close.rolling(20).std()
    df["bb_upper"] = bb_mean + 2 * bb_std
    df["bb_lower"] = bb_mean - 2 * bb_std
    df["bb_mid"]   = bb_mean

    # BB Width: compressao das bandas (squeeze = movimento iminente)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

    # %B: posicao do preco dentro das bandas (0=banda inferior, 1=banda superior)
    span = df["bb_upper"] - df["bb_lower"]
    df["bb_pct_b"] = (close - df["bb_lower"]) / span.replace(0, float("nan"))

    # MACD (12, 26, 9)
    ema12             = close.ewm(span=12, adjust=False).mean()
    ema26             = close.ewm(span=26, adjust=False).mean()
    df["macd_line"]   = ema12 - ema26
    df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
    df["macd_hist"]   = df["macd_line"] - df["macd_signal"]

    # ADX 14 periodos (forca da tendencia, independente da direcao)
    # +DM / -DM
    up_move   = high.diff()
    down_move = -(low.diff())
    plus_dm   = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm  = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr_adx    = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr14     = tr_adx.rolling(14).mean()
    plus_di14 = 100 * plus_dm.rolling(14).mean()  / atr14.replace(0, float("nan"))
    minus_di14= 100 * minus_dm.rolling(14).mean() / atr14.replace(0, float("nan"))
    dx        = (100 * (plus_di14 - minus_di14).abs() /
                 (plus_di14 + minus_di14).replace(0, float("nan")))
    df["adx"]       = dx.rolling(14).mean()
    df["plus_di"]   = plus_di14
    df["minus_di"]  = minus_di14

    return df.dropna()


def score_setup(df: pd.DataFrame) -> int:
    """
    Pontua o setup de entrada de 0 a 100 com base em indicadores tecnicos.
    Retorna o score da ultima vela. Abaixo de 40 o bot nao consulta a LLM para BUY.

    Criterios (cada criterio verdadeiro adiciona pontos):
    - RSI entre 35 e 60 (zona neutra receptiva):       +20
    - MACD histograma positivo:                        +20
    - Preco acima da EMA20:                            +15
    - EMA20 > EMA50 (tendencia curta alinhada):        +15
    - Volume ratio >= 1.2 (volume acima da media):     +15
    - BB %B entre 0.3 e 0.7 (preco no corpo das BB):  +10
    - ADX >= 20 (tendencia definida):                  +5
    """
    last = df.iloc[-1]

    score = 0

    rsi = float(last.get("rsi", 50))
    if 35 <= rsi <= 60:
        score += 20

    if float(last.get("macd_hist", 0)) > 0:
        score += 20

    close = float(last["close"])
    ema20 = float(last.get("ema20", close))
    if close > ema20:
        score += 15

    ema50 = float(last.get("ema50", ema20))
    if ema20 > ema50:
        score += 15

    vol_avg5 = float(last.get("vol_avg5", 1))
    vol      = float(last.get("volume",   1))
    if vol_avg5 > 0 and (vol / vol_avg5) >= 1.2:
        score += 15

    bb_pct_b = float(last.get("bb_pct_b", 0.5))
    if 0.3 <= bb_pct_b <= 0.7:
        score += 10

    adx = float(last.get("adx", 0))
    if adx >= 20:
        score += 5

    return score
