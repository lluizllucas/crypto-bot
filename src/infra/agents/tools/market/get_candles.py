"""
Tool de consulta: retorna candles OHLCV de um timeframe especifico.
Nao calcula indicadores — retorna apenas preco e volume brutos.
"""

import logging

import pandas as pd
from binance.client import Client

from src.infra.clients.binance.client import get_klines

log = logging.getLogger(__name__)

_VALID_TIMEFRAMES = {
    "1m":  Client.KLINE_INTERVAL_1MINUTE,
    "5m":  Client.KLINE_INTERVAL_5MINUTE,
    "15m": Client.KLINE_INTERVAL_15MINUTE,
    "30m": Client.KLINE_INTERVAL_30MINUTE,
    "1h":  Client.KLINE_INTERVAL_1HOUR,
    "4h":  Client.KLINE_INTERVAL_4HOUR,
    "1d":  Client.KLINE_INTERVAL_1DAY,
}


def _fetch_ohlcv(symbol: str, timeframe: str, limit: int) -> pd.DataFrame | None:
    interval = _VALID_TIMEFRAMES.get(timeframe)
    if not interval:
        log.warning(f"Timeframe invalido: {timeframe}")
        return None

    try:
        klines = get_klines(symbol, interval, limit=limit)

        df = pd.DataFrame(klines, columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ])

        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)

        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")

        return df.set_index("open_time").sort_index()
    except Exception as e:
        log.error(f"Erro ao buscar candles {symbol} {timeframe}: {e}")
        return None


def query_candles(symbol: str, timeframe: str, limit: int) -> dict:
    """
    Retorna candles OHLCV de um timeframe especifico.
    Util para o LLM analisar tendencia em 4h ou precisao de entrada em 15m.
    """
    limit = max(5, min(limit, 100))

    df = _fetch_ohlcv(symbol, timeframe, limit)

    if df is None:
        return {"error": f"Nao foi possivel buscar candles {timeframe}"}

    candles = []
    
    for ts, row in df.tail(limit).iterrows():
        candles.append({
            "time":   ts.strftime("%Y-%m-%dT%H:%M"),
            "open":   round(float(row["open"]),   2),
            "high":   round(float(row["high"]),   2),
            "low":    round(float(row["low"]),    2),
            "close":  round(float(row["close"]),  2),
            "volume": round(float(row["volume"]), 2),
        })

    return {
        "symbol":    symbol,
        "timeframe": timeframe,
        "candles":   candles,
    }
