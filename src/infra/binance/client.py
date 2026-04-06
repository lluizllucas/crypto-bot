"""
Cliente Binance.

Dois clientes separados:
- market_client: mainnet publica (sem keys) -- usado para leitura de dados reais
- trade_client:  testnet autenticada       -- usado para execucao de ordens simuladas
"""

import math
import logging

from binance.client import Client

from src.config import BINANCE_TESTNET_API_KEY, BINANCE_TESTNET_SECRET_KEY, BINANCE_API_KEY, BINANCE_SECRET_KEY

log = logging.getLogger(__name__)

# Mainnet -- dados de mercado reais (candles, ticker, preco)
# Nao requer autenticacao pois endpoints de mercado sao publicos
market_client = Client(
    BINANCE_API_KEY, 
    BINANCE_SECRET_KEY, 
    testnet=False
)

# Testnet -- execucao de ordens simuladas (sem dinheiro real)
trade_client = Client(
    BINANCE_TESTNET_API_KEY,
    BINANCE_TESTNET_SECRET_KEY,
    testnet=True,
)


def get_balance(asset: str) -> float:
    """Retorna o saldo disponivel de um asset na testnet."""
    try:
        balance = trade_client.get_asset_balance(asset=asset)
        return float(balance["free"]) if balance else 0.0
    except Exception as e:
        log.error(f"Erro ao buscar saldo de {asset}: {e}")
        return 0.0


def get_current_price(symbol: str) -> float | None:
    """Busca o preco atual do par na mainnet."""
    try:
        ticker = market_client.get_symbol_ticker(symbol=symbol)
        return float(ticker["price"])
    except Exception as e:
        log.error(f"Erro ao buscar preco atual de {symbol}: {e}")
        return None


def get_symbol_filters(symbol: str) -> tuple[float, float, int, float]:
    """Retorna (min_qty, step_size, decimals, min_notional) para o par na mainnet."""
    min_qty, step, decimals, min_notional = 0.0, 0.00001, 5, 5.0
    try:
        info = market_client.get_symbol_info(symbol)
        for f in info["filters"]:
            if f["filterType"] == "LOT_SIZE":
                step = float(f["stepSize"])
                min_qty = float(f["minQty"])
                decimals = len(f["stepSize"].rstrip("0").split(".")[-1]) if "." in f["stepSize"] else 0
            elif f["filterType"] in ("MIN_NOTIONAL", "NOTIONAL"):
                min_notional = float(f.get("minNotional") or f.get("notional") or 5.0)
    except Exception as e:
        log.warning(f"Nao foi possivel obter filtros de {symbol}: {e}")
    return min_qty, step, decimals, min_notional


def adjust_qty(qty: float, step: float, decimals: int) -> float:
    """Arredonda qty para baixo no multiplo correto de step."""
    return round(math.floor(qty / step) * step, decimals)


def order_market_buy(symbol: str, quantity: float) -> dict:
    """Envia uma ordem de compra a mercado na testnet."""
    return trade_client.order_market_buy(symbol=symbol, quantity=quantity)


def order_market_sell(symbol: str, quantity: float) -> dict:
    """Envia uma ordem de venda a mercado na testnet."""
    return trade_client.order_market_sell(symbol=symbol, quantity=quantity)


def get_klines(symbol: str, interval: str, limit: int) -> list:
    """Retorna as ultimas N velas de um par na mainnet."""
    return market_client.get_klines(symbol=symbol, interval=interval, limit=limit)


def get_ticker(symbol: str) -> dict:
    """Retorna o ticker 24h de um par na mainnet."""
    return market_client.get_ticker(symbol=symbol)
