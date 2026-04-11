"""
Busca e montagem do snapshot de mercado completo para um par.
Baixa 200 candles de 1h, calcula indicadores, range engine e Fear & Greed.
"""

import logging

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException
from src.infra import setup_logging

from src.domain.models import MarketData

from src.application.indicators import add_indicators
from src.application.fear_greed import get_fear_greed

from src.infra.binance.client import get_klines, get_ticker

log = setup_logging()


def _range_position(price: float, low: float, high: float) -> float:
    """Retorna onde o preco esta dentro do range: 0.0 (suporte) a 1.0 (resistencia)."""
    span = high - low

    if span == 0:
        return 0.5

    return round((price - low) / span, 4)


def get_market_data(symbol: str) -> MarketData | None:
    """
    Monta o snapshot completo de mercado para envio a LLM:
    - 200 candles de 1h
    - EMA 20/50/200, RSI, ATR, Bollinger Bands
    - Range engine 24h / 7d / 30d
    - Fear & Greed Index
    """
    try:
        klines = get_klines(symbol, Client.KLINE_INTERVAL_1HOUR, limit=200)
        ticker = get_ticker(symbol)

        df = pd.DataFrame(klines, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])

        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)

        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df = df.set_index("open_time").sort_index()

        df = add_indicators(df)

        last = df.iloc[-1]
        price = float(last["close"])

        # Range engine
        high_24h = df["high"].tail(24).max()
        low_24h = df["low"].tail(24).min()
        high_7d = df["high"].tail(24 * 7).max()
        low_7d = df["low"].tail(24 * 7).min()
        high_30d = df["high"].tail(24 * 30).max()
        low_30d = df["low"].tail(24 * 30).min()

        return MarketData(
            symbol=symbol,
            price=price,
            rsi_1h=round(float(last["rsi"]), 2),
            ema20=round(float(last["ema20"]), 2),
            ema50=round(float(last["ema50"]), 2),
            ema200=round(float(last["ema200"]), 2),
            atr=round(float(last["atr"]), 2),
            bb_upper=round(float(last["bb_upper"]), 2),
            bb_lower=round(float(last["bb_lower"]), 2),
            range_position_24h=_range_position(price, low_24h, high_24h),
            range_position_7d=_range_position(price, low_7d, high_7d),
            range_high_24h=round(high_24h, 2),
            range_low_24h=round(low_24h, 2),
            range_high_7d=round(high_7d, 2),
            range_low_7d=round(low_7d, 2),
            range_high_30d=round(high_30d, 2),
            range_low_30d=round(low_30d, 2),
            fear_greed=get_fear_greed(),
            volume_24h=float(ticker["volume"]),
            avg_volume_5h=round(df["volume"].tail(5).mean(), 2),
        )

    except BinanceAPIException as e:
        log.error(f"Erro Binance ao buscar {symbol}: {e}")
        return None
    except Exception as e:
        log.error(f"Erro inesperado ao buscar {symbol}: {e}")
        return None
