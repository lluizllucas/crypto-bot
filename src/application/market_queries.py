"""
Funcoes de consulta de mercado chamadas pelas tools do LLM.

Quando o LLM julgar que precisa de mais contexto para tomar uma decisao,
ele chama uma tool de consulta. Este modulo executa a busca real e retorna
os dados formatados para serem repassados ao LLM como resultado da tool.
"""

import logging

import pandas as pd
from binance.client import Client

from src.application.indicators import add_indicators
from src.application.fear_greed import get_fear_greed
from src.infra.binance.client import get_klines

log = logging.getLogger(__name__)

# Timeframes validos aceitos pelo LLM
_VALID_TIMEFRAMES = {
    "1m":  Client.KLINE_INTERVAL_1MINUTE,
    "5m":  Client.KLINE_INTERVAL_5MINUTE,
    "15m": Client.KLINE_INTERVAL_15MINUTE,
    "30m": Client.KLINE_INTERVAL_30MINUTE,
    "1h":  Client.KLINE_INTERVAL_1HOUR,
    "4h":  Client.KLINE_INTERVAL_4HOUR,
    "1d":  Client.KLINE_INTERVAL_1DAY,
}


def _fetch_df(symbol: str, timeframe: str, limit: int) -> pd.DataFrame | None:
    """Busca candles e retorna DataFrame com indicadores calculados."""
    interval = _VALID_TIMEFRAMES.get(timeframe)
    if not interval:
        log.warning(f"Timeframe invalido: {timeframe}")
        return None

    try:
        klines = get_klines(symbol, interval, limit=limit)
        df = pd.DataFrame(klines, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df = df.set_index("open_time").sort_index()
        return add_indicators(df)
    except Exception as e:
        log.error(f"Erro ao buscar candles {symbol} {timeframe}: {e}")
        return None


# ---------------------------------------------------------------------------
# Funcoes de consulta — uma por tool
# ---------------------------------------------------------------------------

def query_candles(symbol: str, timeframe: str, limit: int) -> dict:
    """
    Retorna candles OHLCV de um timeframe especifico.
    Util para o LLM analisar tendencia em 4h ou precisao de entrada em 15m.
    """
    limit  = max(5, min(limit, 100))
    df     = _fetch_df(symbol, timeframe, limit + 10)

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


def query_rsi_history(symbol: str, periods: int) -> dict:
    """
    Retorna o historico de RSI das ultimas N velas (1h).
    Util para identificar divergencias de longo prazo e tendencia do momentum.
    """
    periods = max(5, min(periods, 50))
    df      = _fetch_df(symbol, "1h", periods + 20)

    if df is None:
        return {"error": "Nao foi possivel buscar RSI historico"}

    tail   = df.tail(periods)
    values = []
    for ts, row in tail.iterrows():
        values.append({
            "time":  ts.strftime("%Y-%m-%dT%H:%M"),
            "rsi":   round(float(row["rsi"]), 2),
            "close": round(float(row["close"]), 2),
        })

    last_rsi  = values[-1]["rsi"]  if values else 0
    first_rsi = values[0]["rsi"]   if values else 0
    trend     = "rising" if last_rsi > first_rsi else "falling" if last_rsi < first_rsi else "flat"

    return {
        "symbol":       symbol,
        "periods":      periods,
        "rsi_trend":    trend,
        "rsi_current":  last_rsi,
        "rsi_start":    first_rsi,
        "rsi_min":      round(min(v["rsi"] for v in values), 2),
        "rsi_max":      round(max(v["rsi"] for v in values), 2),
        "history":      values,
    }


def query_volume_profile(symbol: str, periods: int) -> dict:
    """
    Retorna volume por candle das ultimas N horas com classificacao relativa a media.
    Util para confirmar se o volume atual e realmente anomalo.
    """
    periods = max(5, min(periods, 48))
    df      = _fetch_df(symbol, "1h", periods + 10)

    if df is None:
        return {"error": "Nao foi possivel buscar volume profile"}

    tail     = df.tail(periods)
    avg_vol  = float(tail["volume"].mean())
    entries  = []

    for ts, row in tail.iterrows():
        vol   = float(row["volume"])
        ratio = round(vol / avg_vol, 2) if avg_vol else 1.0
        entries.append({
            "time":   ts.strftime("%Y-%m-%dT%H:%M"),
            "volume": round(vol, 2),
            "ratio":  ratio,
            "class":  "high" if ratio >= 1.5 else "low" if ratio <= 0.5 else "normal",
        })

    return {
        "symbol":      symbol,
        "periods":     periods,
        "avg_volume":  round(avg_vol, 2),
        "max_volume":  round(float(tail["volume"].max()), 2),
        "min_volume":  round(float(tail["volume"].min()), 2),
        "high_count":  sum(1 for e in entries if e["class"] == "high"),
        "low_count":   sum(1 for e in entries if e["class"] == "low"),
        "profile":     entries,
    }


def query_ema_history(symbol: str, ema: int, periods: int) -> dict:
    """
    Retorna a distancia percentual do preco em relacao a uma EMA ao longo do tempo.
    Util para identificar preco muito esticado (mean reversion) ou recuo saudavel.
    """
    valid_emas = {20: "ema20", 50: "ema50", 200: "ema200"}
    if ema not in valid_emas:
        return {"error": f"EMA invalida: {ema}. Use 20, 50 ou 200."}

    periods  = max(5, min(periods, 50))
    col      = valid_emas[ema]
    df       = _fetch_df(symbol, "1h", periods + 210)

    if df is None:
        return {"error": "Nao foi possivel buscar EMA historico"}

    tail    = df.tail(periods)
    entries = []

    for ts, row in tail.iterrows():
        price    = float(row["close"])
        ema_val  = float(row[col])
        dist_pct = round((price - ema_val) / ema_val * 100, 3)
        entries.append({
            "time":     ts.strftime("%Y-%m-%dT%H:%M"),
            "price":    round(price, 2),
            "ema":      round(ema_val, 2),
            "dist_pct": dist_pct,
        })

    current_dist = entries[-1]["dist_pct"] if entries else 0
    avg_dist     = round(sum(e["dist_pct"] for e in entries) / len(entries), 3) if entries else 0

    return {
        "symbol":       symbol,
        "ema":          ema,
        "periods":      periods,
        "current_dist": current_dist,
        "avg_dist":     avg_dist,
        "max_dist":     round(max(e["dist_pct"] for e in entries), 3) if entries else 0,
        "min_dist":     round(min(e["dist_pct"] for e in entries), 3) if entries else 0,
        "history":      entries,
    }


def query_recent_highs_lows(symbol: str, periods: int) -> dict:
    """
    Retorna as maximas e minimas locais das ultimas N velas (1h).
    Util para identificar suportes e resistencias recentes.
    """
    periods = max(10, min(periods, 100))
    df      = _fetch_df(symbol, "1h", periods + 10)

    if df is None:
        return {"error": "Nao foi possivel buscar highs/lows"}

    tail        = df.tail(periods)
    closes      = tail["close"].tolist()
    highs       = tail["high"].tolist()
    lows        = tail["low"].tolist()
    price       = closes[-1]

    # Identifica maximas e minimas locais (pico entre vizinhos)
    local_highs = []
    local_lows  = []

    for i in range(1, len(highs) - 1):
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            local_highs.append(round(highs[i], 2))
        if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            local_lows.append(round(lows[i], 2))

    # Resistencias acima do preco atual, suportes abaixo
    resistances = sorted([h for h in local_highs if h > price])[:5]
    supports    = sorted([l for l in local_lows  if l < price], reverse=True)[:5]

    period_high = round(max(highs), 2)
    period_low  = round(min(lows),  2)

    return {
        "symbol":          symbol,
        "periods":         periods,
        "current_price":   round(price, 2),
        "period_high":     period_high,
        "period_low":      period_low,
        "resistances":     resistances,
        "supports":        supports,
        "nearest_resist":  resistances[0]  if resistances else None,
        "nearest_support": supports[0]     if supports    else None,
    }


def query_volatility_history(symbol: str, periods: int) -> dict:
    """
    Retorna o ATR das ultimas N velas (1h).
    Util para ver se a volatilidade esta aumentando ou diminuindo e ajustar SL/TP.
    """
    periods = max(5, min(periods, 50))
    df      = _fetch_df(symbol, "1h", periods + 20)

    if df is None:
        return {"error": "Nao foi possivel buscar volatilidade historica"}

    tail    = df.tail(periods)
    price   = float(tail["close"].iloc[-1])
    entries = []

    for ts, row in tail.iterrows():
        atr     = float(row["atr"])
        atr_pct = round(atr / price * 100, 3)
        entries.append({
            "time":    ts.strftime("%Y-%m-%dT%H:%M"),
            "atr":     round(atr, 2),
            "atr_pct": atr_pct,
        })

    current_atr = entries[-1]["atr"]     if entries else 0
    avg_atr     = round(sum(e["atr"] for e in entries) / len(entries), 2) if entries else 0
    trend       = "increasing" if current_atr > avg_atr else "decreasing"

    return {
        "symbol":       symbol,
        "periods":      periods,
        "current_atr":  current_atr,
        "current_atr_pct": entries[-1]["atr_pct"] if entries else 0,
        "avg_atr":      avg_atr,
        "max_atr":      round(max(e["atr"] for e in entries), 2) if entries else 0,
        "min_atr":      round(min(e["atr"] for e in entries), 2) if entries else 0,
        "trend":        trend,
        "history":      entries,
    }


def query_range_breakdown(symbol: str, periods: list[int]) -> dict:
    """
    Retorna o range (high-low) de diferentes janelas de tempo e a posicao atual do preco.
    Util para comparar ranges e identificar contracao ou expansao de volatilidade.
    """
    periods  = [p for p in periods if 1 <= p <= 720][:6]
    df       = _fetch_df(symbol, "1h", max(periods) + 10 if periods else 50)

    if df is None:
        return {"error": "Nao foi possivel buscar range breakdown"}

    price    = float(df["close"].iloc[-1])
    ranges   = []

    for p in sorted(periods):
        tail     = df.tail(p)
        high     = round(float(tail["high"].max()), 2)
        low      = round(float(tail["low"].min()),  2)
        span     = high - low
        position = round((price - low) / span, 4) if span > 0 else 0.5

        ranges.append({
            "hours":    p,
            "high":     high,
            "low":      low,
            "span":     round(span, 2),
            "position": position,
            "label":    "near_resistance" if position > 0.8 else
                        "near_support"    if position < 0.2 else "mid_range",
        })

    return {
        "symbol":        symbol,
        "current_price": round(price, 2),
        "ranges":        ranges,
    }


def query_fear_greed_history(days: int) -> dict:
    """
    Retorna o Fear & Greed Index dos ultimos N dias.
    Util para ver se o sentimento esta mudando rapidamente ou estavel.
    """
    import requests

    days  = max(1, min(days, 30))

    try:
        response = requests.get(
            f"https://api.alternative.me/fng/?limit={days}",
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()["data"]

        def _label(v: int) -> str:
            if v <= 25: return "Extreme Fear"
            if v <= 50: return "Fear"
            if v <= 75: return "Greed"
            return "Extreme Greed"

        history = []
        for item in reversed(data):
            val = int(item["value"])
            history.append({
                "date":  item["timestamp"][:10] if len(item.get("timestamp", "")) >= 10
                         else item.get("value_classification", ""),
                "value": val,
                "label": _label(val),
            })

        values   = [h["value"] for h in history]
        current  = values[-1] if values else 50
        avg      = round(sum(values) / len(values), 1) if values else 50
        trend    = "improving" if current > avg else "worsening" if current < avg else "stable"

        return {
            "days":    days,
            "current": current,
            "avg":     avg,
            "max":     max(values) if values else 50,
            "min":     min(values) if values else 50,
            "trend":   trend,
            "history": history,
        }

    except Exception as e:
        log.error(f"Erro ao buscar Fear & Greed historico: {e}")
        return {"error": "Nao foi possivel buscar Fear & Greed historico"}
