"""
Backtesting -- simula a estrategia do bot em dados historicos da Binance Testnet.

Como funciona:
- Baixa velas de 1h para cada simbolo
- Para cada vela, calcula os mesmos indicadores que o LLM recebe
- Gera sinais usando regras tecnicas (sem chamar LLM -- seria lento e custoso)
- Simula entradas, stop-loss, take-profit e limite diario
- Exibe relatorio final com PnL, win rate e drawdown maximo
"""

import sys
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from binance.client import Client

from config import (
    BINANCE_API_KEY,
    BINANCE_SECRET_KEY,
    SYMBOLS,
    TRADE_USDT,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    MAX_DAILY_LOSS_USDT,
)

# Parametros do backtest
BACKTEST_DAYS   = 365   # quantos dias para tras simular (1 ano -- captura bull de 2025)
MIN_CONFIDENCE  = 0.65  # mesmo limiar do bot ao vivo

# Se True: ignora SELL-SIGNAL quando ha posicao aberta (deixa SL/TP trabalhar)
# Se False: comportamento original (vende no sinal do LLM)
# Compare os dois para decidir qual estrategia e melhor
HOLD_ON_OPEN_POSITION = False

# Stop-loss por simbolo -- ETH e mais volatil, precisa de margem maior
SYMBOL_SL = {
    "BTCUSDT": 2.5,
    "ETHUSDT": 4.0,
}

# Filtro de mercado extremo: se BTC subiu mais que X% nos ultimos 30 dias,
# considera mercado em euforia e bloqueia novas entradas (evita bull extremo)
BULL_FILTER_PCT = 30.0  # 30% de alta em 30 dias = euforia

# Logging simples para o backtest
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# Backtest usa API publica (sem autenticacao) para ter acesso ao historico completo
client = Client("", "")


# ── Dados historicos ──────────────────────────────────────────────────────────

def fetch_historical(symbol: str, days: int) -> pd.DataFrame:
    """Baixa velas de 1h dos ultimos N dias da Binance."""
    log.info(f"[{symbol}] Baixando {days} dias de dados historicos...")
    start = datetime.now(timezone.utc) - timedelta(days=days)
    start_str = start.strftime("%d %b %Y %H:%M:%S")

    klines = client.get_historical_klines(
        symbol, Client.KLINE_INTERVAL_1HOUR, start_str
    )

    df = pd.DataFrame(klines, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["close"]  = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    df["high"]   = df["high"].astype(float)
    df["low"]    = df["low"].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df = df.set_index("open_time").sort_index()
    log.info(f"[{symbol}] {len(df)} velas carregadas ({df.index[0].date()} -> {df.index[-1].date()})")
    return df


# ── Indicadores tecnicos ──────────────────────────────────────────────────────

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona indicadores usados para gerar sinais."""
    df = df.copy()

    # Medias moveis
    df["sma5"]  = df["close"].rolling(5).mean()
    df["sma20"] = df["close"].rolling(20).mean()

    # Volume medio 5h
    df["vol_avg5"] = df["volume"].rolling(5).mean()

    # Variacao percentual da ultima hora
    df["close_pct1h"] = df["close"].pct_change() * 100

    # RSI 14 periodos
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, float("inf"))
    df["rsi"] = 100 - (100 / (1 + rs))

    return df.dropna()


# ── Gerador de sinais ─────────────────────────────────────────────────────────

def generate_signal(row: pd.Series, in_position: bool = False) -> tuple[str, float]:
    """
    Versao original -- melhor resultado no backtest ($18.45 PnL em 90 dias).

    BUY:  SMA5 > SMA20, volume acima da media, RSI 40-65, close_pct1h > 0
    SELL: SMA5 < SMA20, volume acima da media, RSI > 60 ou RSI < 35
    """
    sma_bull  = row["sma5"] > row["sma20"]
    vol_ratio = row["volume"] / row["vol_avg5"] if row["vol_avg5"] > 0 else 0
    rsi       = row["rsi"]
    pct1h     = row["close_pct1h"]

    if sma_bull and vol_ratio >= 1.0 and 40 <= rsi <= 65 and pct1h > 0:
        confidence = 0.55
        if rsi < 60:
            confidence += 0.10
        if pct1h > 0.3:
            confidence += 0.10
        if vol_ratio >= 1.5:
            confidence += 0.10
        return "BUY", round(min(confidence, 0.95), 2)

    if not sma_bull and vol_ratio >= 1.0 and (rsi > 60 or rsi < 35):
        confidence = 0.55
        if rsi > 65 or rsi < 30:
            confidence += 0.15
        if pct1h < -0.3:
            confidence += 0.10
        return "SELL", round(min(confidence, 0.95), 2)

    return "HOLD", 0.0


# ── Motor de simulacao ────────────────────────────────────────────────────────

def is_extreme_bull(df_btc: pd.DataFrame, current_ts) -> bool:
    """
    Retorna True se BTC subiu mais que BULL_FILTER_PCT nos ultimos 30 dias.
    Usado para evitar entradas durante euforia de mercado.
    """
    try:
        past = current_ts - pd.Timedelta(days=30)
        slice_df = df_btc[df_btc.index <= current_ts]
        slice_df = slice_df[slice_df.index >= past]
        if len(slice_df) < 2:
            return False
        pct = (slice_df["close"].iloc[-1] - slice_df["close"].iloc[0]) / slice_df["close"].iloc[0] * 100
        return pct >= BULL_FILTER_PCT
    except Exception:
        return False


def check_intracandle_sl_tp(position: dict, low: float, high: float, sl_pct: float = STOP_LOSS_PCT) -> tuple[str | None, float]:
    """
    Simula o ciclo rapido de 5 min usando high/low da vela de 1h.

    Logica de precedencia dentro da vela:
    - Se tanto SL quanto TP foram tocados na mesma vela, assume que o SL
      ocorreu primeiro (comportamento conservador -- pior caso).
    - Retorna (motivo, preco_de_saida) ou (None, 0).
    """
    entry = position["entry"]
    sl_price = entry * (1 - sl_pct / 100)
    tp_price = entry * (1 + TAKE_PROFIT_PCT / 100)

    sl_hit = low  <= sl_price
    tp_hit = high >= tp_price

    if sl_hit and tp_hit:
        return "STOP-LOSS", sl_price   # conservador: assume SL primeiro
    if sl_hit:
        return "STOP-LOSS", sl_price
    if tp_hit:
        return "TAKE-PROFIT", tp_price
    return None, 0.0


def run_backtest(symbol: str, df: pd.DataFrame, btc_df: pd.DataFrame | None = None) -> dict:
    """
    Simula o bot no historico com ciclo rapido de SL/TP.

    Dentro de cada vela de 1h, usa high/low para verificar se SL ou TP
    teriam sido atingidos -- equivalente ao monitor de 5 minutos do bot ao vivo.
    """
    capital      = TRADE_USDT * 10
    usdt         = capital
    position     = None
    trades       = []
    daily_loss   = {}
    equity_curve = []

    for ts, row in df.iterrows():
        price = row["close"]
        today = ts.date()
        daily_loss.setdefault(today, 0.0)

        # Verifica SL/TP intra-vela usando high/low (simula monitor de 5 min)
        if position:
            sl = SYMBOL_SL.get(symbol, STOP_LOSS_PCT)
            reason, exit_price = check_intracandle_sl_tp(position, row["low"], row["high"], sl_pct=sl)
            if reason:
                pnl = (exit_price - position["entry"]) * position["qty"]
                usdt += exit_price * position["qty"]
                if pnl < 0:
                    daily_loss[today] = daily_loss.get(today, 0) + abs(pnl)
                trades.append({
                    "symbol":   symbol,
                    "entry":    position["entry"],
                    "exit":     exit_price,
                    "qty":      position["qty"],
                    "pnl":      round(pnl, 4),
                    "reason":   reason,
                    "entry_dt": position["date"],
                    "exit_dt":  ts,
                })
                position = None

        # Filtro de mercado extremo (so aplica para nao-BTC)
        if symbol != "BTCUSDT" and btc_df is not None and is_extreme_bull(btc_df, ts):
            equity_curve.append({"ts": ts, "equity": usdt + (price * position["qty"] if position else 0)})
            continue

        # Gera sinal
        signal, confidence = generate_signal(row)

        # Limite diario
        if daily_loss.get(today, 0) >= MAX_DAILY_LOSS_USDT:
            equity_curve.append({"ts": ts, "equity": usdt + (price * position["qty"] if position else 0)})
            continue

        # Executa sinal
        if signal == "BUY" and confidence >= MIN_CONFIDENCE and position is None and usdt >= 10:
            spend = min(TRADE_USDT, usdt * 0.99)
            qty   = round(spend / price, 6)
            usdt -= spend
            position = {"entry": price, "qty": qty, "date": ts}

        elif signal == "SELL" and confidence >= MIN_CONFIDENCE and position and not HOLD_ON_OPEN_POSITION:
            pnl = (price - position["entry"]) * position["qty"]
            usdt += price * position["qty"]
            if pnl < 0:
                daily_loss[today] = daily_loss.get(today, 0) + abs(pnl)
            trades.append({
                "symbol":   symbol,
                "entry":    position["entry"],
                "exit":     price,
                "qty":      position["qty"],
                "pnl":      round(pnl, 4),
                "reason":   "SELL-SIGNAL",
                "entry_dt": position["date"],
                "exit_dt":  ts,
            })
            position = None

        equity = usdt + (price * position["qty"] if position else 0)
        equity_curve.append({"ts": ts, "equity": equity})

    # Fecha posicao aberta ao final (mark-to-market)
    if position:
        last_price = df["close"].iloc[-1]
        pnl = (last_price - position["entry"]) * position["qty"]
        usdt += last_price * position["qty"]
        trades.append({
            "symbol":   symbol,
            "entry":    position["entry"],
            "exit":     last_price,
            "qty":      position["qty"],
            "pnl":      round(pnl, 4),
            "reason":   "FIM-DO-PERIODO",
            "entry_dt": position["date"],
            "exit_dt":  df.index[-1],
        })

    return {
        "symbol":       symbol,
        "capital":      capital,
        "final_usdt":   round(usdt, 2),
        "trades":       trades,
        "equity_curve": equity_curve,
    }


# ── Relatorio ─────────────────────────────────────────────────────────────────

def print_report(result: dict):
    trades  = result["trades"]
    capital = result["capital"]
    final   = result["final_usdt"]
    symbol  = result["symbol"]

    if not trades:
        print(f"\n[{symbol}] Nenhuma operacao realizada no periodo.")
        return

    df_t   = pd.DataFrame(trades)
    wins   = df_t[df_t["pnl"] > 0]
    losses = df_t[df_t["pnl"] <= 0]

    total_pnl    = df_t["pnl"].sum()
    win_rate     = len(wins) / len(df_t) * 100 if trades else 0
    avg_win      = wins["pnl"].mean() if len(wins) else 0
    avg_loss     = losses["pnl"].mean() if len(losses) else 0
    best_trade   = df_t["pnl"].max()
    worst_trade  = df_t["pnl"].min()
    total_return = (final - capital) / capital * 100

    # Drawdown maximo
    eq = pd.Series([e["equity"] for e in result["equity_curve"]])
    rolling_max = eq.cummax()
    drawdown = ((eq - rolling_max) / rolling_max * 100)
    max_dd = drawdown.min()

    sep = "-" * 50
    print(f"\n{sep}")
    print(f"  Backtest: {symbol} | ultimos {BACKTEST_DAYS} dias")
    print(sep)
    print(f"  Capital inicial:   ${capital:.2f}")
    print(f"  Capital final:     ${final:.2f}  ({total_return:+.2f}%)")
    print(f"  PnL total:         ${total_pnl:.2f}")
    print(f"  Operacoes:         {len(df_t)}")
    print(f"  Win rate:          {win_rate:.1f}%  ({len(wins)}W / {len(losses)}L)")
    print(f"  Ganho medio:       ${avg_win:.2f}")
    print(f"  Perda media:       ${avg_loss:.2f}")
    print(f"  Melhor operacao:   ${best_trade:.2f}")
    print(f"  Pior operacao:     ${worst_trade:.2f}")
    print(f"  Drawdown maximo:   {max_dd:.2f}%")
    print(sep)

    # Detalhamento por motivo de saida
    print("  Saidas por motivo:")
    for reason, count in df_t["reason"].value_counts().items():
        pnl_r = df_t[df_t["reason"] == reason]["pnl"].sum()
        print(f"    {reason:<20} {count:>3}x   PnL: ${pnl_r:.2f}")
    print(sep)

    # Breakdown mensal
    df_t["month"] = pd.to_datetime(df_t["exit_dt"]).dt.to_period("M")
    monthly = df_t.groupby("month").agg(
        ops=("pnl", "count"),
        pnl=("pnl", "sum"),
        wins=("pnl", lambda x: (x > 0).sum())
    )
    print("  Resultado por mes:")
    for month, row in monthly.iterrows():
        wr = row["wins"] / row["ops"] * 100 if row["ops"] > 0 else 0
        bar = "+" * int(max(row["pnl"], 0)) + "-" * int(max(-row["pnl"], 0))
        bar = bar[:20]
        print(f"    {str(month)}   {row['ops']:>2}ops   WR:{wr:4.0f}%   PnL:${row['pnl']:>6.2f}  {bar}")
    print(sep)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\nBacktest -- {BACKTEST_DAYS} dias | SL: {STOP_LOSS_PCT}% | TP: {TAKE_PROFIT_PCT}%")
    print(f"Simbolos: {', '.join(SYMBOLS)}\n")

    all_trades = []
    btc_df = None  # sera carregado no primeiro par e repassado para os demais

    for symbol in SYMBOLS:
        try:
            df = fetch_historical(symbol, BACKTEST_DAYS)
            df = add_indicators(df)
            if symbol == "BTCUSDT":
                btc_df = df  # guarda para uso como filtro macro
            result = run_backtest(symbol, df, btc_df=btc_df)
            print_report(result)
            all_trades.extend(result["trades"])
        except Exception as e:
            log.error(f"[{symbol}] Erro no backtest: {e}")

    # Resumo consolidado
    if all_trades:
        df_all = pd.DataFrame(all_trades)
        total  = df_all["pnl"].sum()
        wins   = len(df_all[df_all["pnl"] > 0])
        total_ops = len(df_all)
        print(f"\n{'=' * 50}")
        print(f"  CONSOLIDADO -- todos os pares")
        print(f"  Total de operacoes: {total_ops}")
        print(f"  Win rate global:    {wins/total_ops*100:.1f}%")
        print(f"  PnL total:          ${total:.2f}")
        print(f"{'=' * 50}\n")