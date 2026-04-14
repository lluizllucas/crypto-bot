"""
Busca e montagem do snapshot de mercado completo para um par.
Baixa 200 candles de 1h, calcula indicadores, range engine e Fear & Greed.
"""

import logging

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException

from src.domain.models import Candle, MarketData

from src.application.indicators import add_indicators, score_setup
from src.application.fear_greed import get_fear_greed

from src.infra.binance.client import get_klines, get_ticker

log = logging.getLogger(__name__)


def _range_position(price: float, low: float, high: float) -> float:
    """Retorna onde o preco esta dentro do range: 0.0 (suporte) a 1.0 (resistencia)."""
    span = high - low
    if span == 0:
        return 0.5
    return round((price - low) / span, 4)


def _rsi_direction(rsi_series: pd.Series) -> str:
    """Retorna a direcao do RSI nas ultimas 3 velas: rising, falling ou flat."""
    if len(rsi_series) < 3:
        return "flat"
    vals = rsi_series.iloc[-3:].tolist()
    if vals[-1] > vals[-2] > vals[-3]:
        return "rising"
    if vals[-1] < vals[-2] < vals[-3]:
        return "falling"
    return "flat"


def _rsi_divergence(price_series: pd.Series, rsi_series: pd.Series) -> str:
    """
    Divergencia simples entre preco e RSI nas ultimas 3 velas:
    - bearish: preco subindo + RSI caindo
    - bullish: preco caindo + RSI subindo
    - none: sem divergencia clara
    """
    if len(price_series) < 3 or len(rsi_series) < 3:
        return "none"

    price_up = price_series.iloc[-1] > price_series.iloc[-3]
    rsi_up   = rsi_series.iloc[-1]   > rsi_series.iloc[-3]

    if price_up and not rsi_up:
        return "bearish"
    if not price_up and rsi_up:
        return "bullish"
    return "none"


def get_market_data(symbol: str) -> MarketData | None:
    """
    Monta o snapshot completo de mercado para envio a LLM:
    - 200 candles de 1h
    - EMA 20/50/200, RSI, ATR, Bollinger Bands + BB Width + %B
    - MACD (linha, sinal, histograma)
    - Variacao % 1h / 4h / 24h
    - Volume ratio (atual vs media historica)
    - Range engine 24h / 7d / 30d
    - Fear & Greed Index com label
    - Ultimas 4 velas (price action)
    - Direcao e divergencia do RSI
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

        last  = df.iloc[-1]
        price = float(last["close"])

        # Range engine
        high_24h  = df["high"].tail(24).max()
        low_24h   = df["low"].tail(24).min()
        high_7d   = df["high"].tail(24 * 7).max()
        low_7d    = df["low"].tail(24 * 7).min()
        high_30d  = df["high"].tail(24 * 30).max()
        low_30d   = df["low"].tail(24 * 30).min()

        # Variacao percentual recente
        def _pct(n: int) -> float:
            if len(df) <= n:
                return 0.0
            past = float(df["close"].iloc[-(n + 1)])
            return round((price - past) / past * 100, 2) if past else 0.0

        change_1h  = _pct(1)
        change_4h  = _pct(4)
        change_24h = _pct(24)

        # Volume ratio: volume atual vs media das ultimas 30 velas
        avg_vol_30 = df["volume"].tail(30).mean()
        vol_ratio  = round(float(last["volume"]) / avg_vol_30, 2) if avg_vol_30 else 1.0

        # Fear & Greed
        fg_value, fg_label = get_fear_greed()

        # Ultimas 4 velas para price action
        recent_candles = [
            Candle(
                open=round(float(row["open"]),   2),
                high=round(float(row["high"]),   2),
                low= round(float(row["low"]),    2),
                close=round(float(row["close"]), 2),
                volume=round(float(row["volume"]), 2),
            )
            for _, row in df.tail(4).iterrows()
        ]

        # Direcao e divergencia do RSI
        rsi_dir = _rsi_direction(df["rsi"])
        rsi_div = _rsi_divergence(df["close"], df["rsi"])

        # ADX e regime de mercado
        adx_val   = round(float(last.get("adx",      0.0)), 2)
        plus_di   = round(float(last.get("plus_di",  0.0)), 2)
        minus_di  = round(float(last.get("minus_di", 0.0)), 2)
        if adx_val >= 25:
            market_regime = "trending"
        elif adx_val <= 20:
            market_regime = "ranging"
        else:
            market_regime = "undefined"

        # Score de setup tecnico pre-LLM
        setup = score_setup(df)

        return MarketData(
            symbol=symbol,
            price=price,

            rsi_1h=round(float(last["rsi"]),      2),
            ema20= round(float(last["ema20"]),     2),
            ema50= round(float(last["ema50"]),     2),
            ema200=round(float(last["ema200"]),    2),
            atr=   round(float(last["atr"]),       2),

            bb_upper= round(float(last["bb_upper"]),  2),
            bb_lower= round(float(last["bb_lower"]),  2),
            bb_mid=   round(float(last["bb_mid"]),    2),
            bb_width= round(float(last["bb_width"]),  4),
            bb_pct_b= round(float(last["bb_pct_b"]),  4),

            macd_line=     round(float(last["macd_line"]),   2),
            macd_signal=   round(float(last["macd_signal"]), 2),
            macd_histogram=round(float(last["macd_hist"]),   2),

            change_pct_1h= change_1h,
            change_pct_4h= change_4h,
            change_pct_24h=change_24h,

            volume_24h=   float(ticker["volume"]),
            avg_volume_5h=round(df["volume"].tail(5).mean(), 2),
            volume_ratio= vol_ratio,

            range_position_24h=_range_position(price, low_24h, high_24h),
            range_position_7d= _range_position(price, low_7d,  high_7d),
            range_high_24h=round(high_24h, 2),
            range_low_24h= round(low_24h,  2),
            range_high_7d= round(high_7d,  2),
            range_low_7d=  round(low_7d,   2),
            range_high_30d=round(high_30d, 2),
            range_low_30d= round(low_30d,  2),

            fear_greed=      fg_value,
            fear_greed_label=fg_label,

            recent_candles=recent_candles,
            rsi_direction= rsi_dir,
            rsi_divergence=rsi_div,

            adx=           adx_val,
            plus_di=       plus_di,
            minus_di=      minus_di,
            market_regime= market_regime,

            setup_score=   setup,
        )

    except BinanceAPIException as e:
        log.error(f"Erro Binance ao buscar {symbol}: {e}")
        return None
    except Exception as e:
        log.error(f"Erro inesperado ao buscar {symbol}: {e}")
        return None
