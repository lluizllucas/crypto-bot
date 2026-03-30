"""
Crypto Trading Bot -- OpenRouter (estrategista) + Binance Testnet (simulacao)
Stack 100% gratuito, sem dados fiscais, funciona no Brasil
"""

import json
import math
import sys
import time
import logging
import logging.handlers
from datetime import datetime, timezone

import schedule
from openai import OpenAI
from binance.client import Client
from binance.exceptions import BinanceAPIException

from config import (
    OPENROUTER_API_KEY,
    BINANCE_API_KEY,
    BINANCE_SECRET_KEY,
    SYMBOLS,
    TRADE_USDT,
    INTERVAL_MINUTES,
    MIN_CONFIDENCE,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    MAX_DAILY_LOSS_USDT,
    MONITOR_INTERVAL_MINUTES,
    DISCORD_WEBHOOK_URL,
    MAX_POSITIONS_PER_SYMBOL,
    MIN_ENTRY_DISTANCE_PCT,
)

# ── Logging ───────────────────────────────────────────────────────────────────
# Rotacao automatica: novo arquivo a cada dia, mantem 30 dias de historico
# bot.log          -> log principal (INFO+)
# bot.error.log    -> apenas WARNING e ERROR (facil de checar problemas)

_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# Terminal com UTF-8 (corrige Windows cp1252)
_console = logging.StreamHandler(sys.stdout)
_console.setFormatter(_fmt)
if hasattr(_console.stream, "reconfigure"):
    _console.stream.reconfigure(encoding="utf-8", errors="replace")

# Arquivo principal -- rotacao diaria, retencao infinita (para analise historica)
# Gera: bot.log (hoje), bot.log.2026-03-20 (ontem), etc.
_file_main = logging.handlers.TimedRotatingFileHandler(
    "/app/logs/bot.log", when="midnight", interval=1, backupCount=0, encoding="utf-8"
)
_file_main.setFormatter(_fmt)
_file_main.setLevel(logging.INFO)

# Arquivo de erros -- apenas WARNING+ para diagnostico rapido
# Gera: bot.error.log (hoje), bot.error.log.2026-03-20 (ontem), etc.
_file_err = logging.handlers.TimedRotatingFileHandler(
    "/app/logs/bot.error.log", when="midnight", interval=1, backupCount=0, encoding="utf-8"
)
_file_err.setFormatter(_fmt)
_file_err.setLevel(logging.WARNING)

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
log.addHandler(_console)
log.addHandler(_file_main)
log.addHandler(_file_err)

# ── Clientes ──────────────────────────────────────────────────────────────────
llm = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# testnet=True --> usa https://testnet.binance.vision (sem dinheiro real)
client = Client(
    BINANCE_API_KEY,
    BINANCE_SECRET_KEY,
    testnet=True,
)

# Rastreamento de posicoes abertas (multi-lote por simbolo):
# { "BTCUSDT": [ {"entry_price", "qty", "sl", "tp", "ts"}, ... ] }
open_positions: dict = {}

# Perda acumulada no dia
daily_loss_usdt: float = 0.0
daily_loss_date: str = ""

# Estatisticas da sessao (desde que o bot foi iniciado)
session_stats = {
    "trades_total": 0,
    "trades_win":   0,
    "trades_loss":  0,
    "pnl_total":    0.0,
    "started_at":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def sanitize(text: str) -> str:
    """Substitui caracteres tipograficos que o Windows cp1252 nao suporta."""
    replacements = {
        "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2026": "...", "\u00b7": ".",
    }
    for char, rep in replacements.items():
        text = text.replace(char, rep)
    return text


def discord_notify(title: str, message: str, color: int = 0x5865F2):
    """
    Envia uma notificacao para o canal do Discord via webhook.
    color: 0x57F287 (verde), 0xED4245 (vermelho), 0xFEE75C (amarelo), 0x5865F2 (azul)
    """
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        import requests
        payload = {
            "embeds": [{
                "title": title,
                "description": message,
                "color": color,
                "footer": {"text": "Trading Bot"},
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        log.warning(f"Erro ao enviar notificacao Discord: {e}")


def get_balance(asset: str) -> float:
    """Retorna o saldo disponivel de um asset (ex: 'BTC', 'USDT')."""
    try:
        balance = client.get_asset_balance(asset=asset)
        return float(balance["free"]) if balance else 0.0
    except Exception as e:
        log.error(f"Erro ao buscar saldo de {asset}: {e}")
        return 0.0


def get_current_price(symbol: str) -> float | None:
    """Busca apenas o preco atual do par -- chamada leve, sem velas."""
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker["price"])
    except Exception as e:
        log.error(f"Erro ao buscar preco atual de {symbol}: {e}")
        return None


def get_symbol_filters(symbol: str) -> tuple[float, float, int, float]:
    """Retorna (min_qty, step_size, decimals, min_notional) para o par."""
    min_qty, step, decimals, min_notional = 0.0, 0.00001, 5, 5.0
    try:
        info = client.get_symbol_info(symbol)
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


# ── Gestao de risco ───────────────────────────────────────────────────────────

def check_daily_loss_limit() -> bool:
    """Retorna True se o limite de perda diaria foi atingido."""
    global daily_loss_usdt, daily_loss_date
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if daily_loss_date != today:
        if daily_loss_date:
            log.info(f"Novo dia -- perda acumulada resetada (era ${daily_loss_usdt:.2f})")
        daily_loss_usdt = 0.0
        daily_loss_date = today
    if daily_loss_usdt >= MAX_DAILY_LOSS_USDT:
        log.warning(
            f"Limite de perda diaria atingido "
            f"(${daily_loss_usdt:.2f} / ${MAX_DAILY_LOSS_USDT:.2f}) -- sem novas ordens hoje"
        )
        return True
    return False


def register_position(symbol: str, entry_price: float, qty: float):
    """Acrescenta um lote ao simbolo para monitoramento de SL/TP."""
    if symbol not in open_positions:
        open_positions[symbol] = []
    sl = entry_price * (1 - STOP_LOSS_PCT / 100)
    tp = entry_price * (1 + TAKE_PROFIT_PCT / 100)
    open_positions[symbol].append({
        "entry_price": entry_price,
        "qty": qty,
        "sl": sl,
        "tp": tp,
        "ts": datetime.now(timezone.utc),
    })
    n = len(open_positions[symbol])
    log.info(
        f"[{symbol}] Posicao registrada ({n}/{MAX_POSITIONS_PER_SYMBOL}) | "
        f"entrada: ${entry_price:.4f} | "
        f"SL: ${sl:.4f} (-{STOP_LOSS_PCT}%) | "
        f"TP: ${tp:.4f} (+{TAKE_PROFIT_PCT}%)"
    )


def close_position_at_index(symbol: str, idx: int, current_price: float, reason: str):
    """Fecha um lote pelo indice na lista, vende apenas essa quantidade."""
    global daily_loss_usdt

    positions = open_positions.get(symbol)
    if not positions or idx < 0 or idx >= len(positions):
        return

    pos   = positions[idx]
    entry = pos["entry_price"]
    qty   = pos["qty"]
    pnl   = (current_price - entry) * qty

    min_qty, step, decimals, min_notional = get_symbol_filters(symbol)
    sell_qty = adjust_qty(qty * 0.999, step, decimals)

    if sell_qty < min_qty or sell_qty * current_price < min_notional:
        log.warning(f"[{symbol}] Quantidade insuficiente para fechar lote ({sell_qty})")
        positions.pop(idx)
        if not positions:
            del open_positions[symbol]
        return

    try:
        order = client.order_market_sell(symbol=symbol, quantity=sell_qty)

        session_stats["trades_total"] += 1
        session_stats["pnl_total"]    += pnl
        if pnl >= 0:
            session_stats["trades_win"] += 1
        else:
            session_stats["trades_loss"] += 1
            daily_loss_usdt += abs(pnl)

        level = logging.INFO if pnl >= 0 else logging.WARNING
        log.log(level,
            f"[{symbol}] [{reason}] Lote fechado | "
            f"entrada: ${entry:.4f} -> saida: ${current_price:.4f} | "
            f"PnL: ${pnl:+.4f} | "
            f"ID: {order['orderId']} | "
            f"Sessao: {session_stats['trades_win']}W/"
            f"{session_stats['trades_loss']}L "
            f"PnL total: ${session_stats['pnl_total']:+.4f}"
        )
        positions.pop(idx)
        if not positions:
            del open_positions[symbol]
        notify_color = 0x57F287 if pnl >= 0 else 0xED4245
        discord_notify(
            title=f"{reason} -- {symbol}",
            message=(
                f"**Entrada:** ${entry:.4f}\n"
                f"**Saida:** ${current_price:.4f}\n"
                f"**PnL:** ${pnl:+.4f}\n"
                f"**Sessao:** {session_stats['trades_win']}W/{session_stats['trades_loss']}L "
                f"| PnL total: ${session_stats['pnl_total']:+.4f}"
            ),
            color=notify_color
        )
    except BinanceAPIException as e:
        log.error(f"[{symbol}] Erro ao fechar posicao: {e}")


# ── Dados de mercado ──────────────────────────────────────────────────────────

def get_market_data(symbol: str) -> dict:
    """Busca as ultimas 20 velas de 1h e o ticker 24h."""
    try:
        klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1HOUR, limit=20)
        closes  = [float(k[4]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        ticker  = client.get_ticker(symbol=symbol)
        return {
            "symbol": symbol,
            "last_price": closes[-1],
            "price_change_24h_pct": float(ticker["priceChangePercent"]),
            "high_24h": float(ticker["highPrice"]),
            "low_24h":  float(ticker["lowPrice"]),
            "volume_24h": float(ticker["volume"]),
            "avg_volume_5h": round(sum(volumes[-5:]) / 5, 2),
            "last_volume": volumes[-1],
            "closes_5h": [round(c, 4) for c in closes[-5:]],
        }
    except BinanceAPIException as e:
        log.error(f"Erro Binance ao buscar {symbol}: {e}")
        return {}
    except Exception as e:
        log.error(f"Erro inesperado ao buscar {symbol}: {e}")
        return {}


# ── Analise LLM ───────────────────────────────────────────────────────────────

def analyze_with_llm(market_data: dict) -> dict:
    """Envia dados ao OpenRouter e recebe signal, confidence, reasoning."""
    prompt = f"""Voce e um analista quantitativo de criptomoedas. Analise os dados abaixo e retorne
APENAS um JSON valido, sem texto adicional, sem markdown, sem blocos de codigo.

Dados de mercado (ultima hora):
{json.dumps(market_data, indent=2)}

Retorne exatamente neste formato:
{{
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": <numero entre 0.0 e 1.0>,
  "reasoning": "<explicacao objetiva em ate 2 frases>"
}}

Criterios sugeridos:
- BUY:  tendencia de alta nas ultimas horas, volume acima da media
- SELL: queda consistente com volume alto confirmando pressao vendedora
- HOLD: sinal ambiguo ou confianca abaixo de {MIN_CONFIDENCE}
- Em caso de duvida, prefira HOLD"""

    for attempt in range(1, 4):
        try:
            response = llm.chat.completions.create(
                model="openrouter/free",
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.choices[0].message.content.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text.strip())
            assert result.get("signal") in ("BUY", "SELL", "HOLD")
            assert 0.0 <= float(result.get("confidence", 0)) <= 1.0
            result["reasoning"] = sanitize(result.get("reasoning", ""))
            return result
        except Exception as e:
            wait = attempt * 15
            if attempt < 3:
                log.warning(
                    f"Tentativa {attempt} falhou para {market_data.get('symbol')}: "
                    f"{sanitize(str(e))} -- aguardando {wait}s"
                )
                time.sleep(wait)
            else:
                log.error(
                    f"Erro na analise LLM para {market_data.get('symbol')} "
                    f"apos 3 tentativas: {sanitize(str(e))}"
                )

    return {"signal": "HOLD", "confidence": 0.0, "reasoning": "Erro na analise."}


# ── Execucao de ordens ────────────────────────────────────────────────────────

def execute_trade(symbol: str, signal: str, confidence: float, last_price: float) -> bool:
    """Executa uma ordem de mercado respeitando todos os filtros e limites."""
    if confidence < MIN_CONFIDENCE:
        log.info(f"[{symbol}] Confianca {confidence:.0%} abaixo do limiar -- ignorando")
        return False

    base_asset   = symbol.replace("USDT", "")
    usdt_balance = get_balance("USDT")
    base_balance = get_balance(base_asset)
    min_qty, step, decimals, min_notional = get_symbol_filters(symbol)

    try:
        if signal == "BUY":
            posicoes = open_positions.get(symbol, [])
            if len(posicoes) >= MAX_POSITIONS_PER_SYMBOL:
                log.info(
                    f"[{symbol}] Limite de posicoes ({MAX_POSITIONS_PER_SYMBOL}) -- ignorando BUY"
                )
                return False
            if posicoes:
                ultima_entrada = posicoes[-1]["entry_price"]
                distancia = abs(last_price - ultima_entrada) / ultima_entrada * 100
                if distancia < MIN_ENTRY_DISTANCE_PCT:
                    log.info(
                        f"[{symbol}] Nova entrada muito perto da ultima "
                        f"({distancia:.2f}% < {MIN_ENTRY_DISTANCE_PCT}%) -- ignorando BUY"
                    )
                    return False
            if usdt_balance < 10:
                log.warning(f"[{symbol}] Saldo USDT insuficiente ({usdt_balance:.2f})")
                return False
            spend = min(TRADE_USDT, usdt_balance * 0.99)
            qty   = adjust_qty(spend / last_price, step, decimals)
            if qty < min_qty or qty * last_price < min_notional:
                log.warning(f"[{symbol}] Ordem abaixo dos filtros minimos -- ignorando")
                return False
            order = client.order_market_buy(symbol=symbol, quantity=qty)
            log.info(
                f"[{symbol}] [BUY] Ordem executada | "
                f"qty: {qty} @ ~${last_price:.4f} | "
                f"valor: ~${qty * last_price:.2f} | "
                f"ID: {order['orderId']}"
            )
            register_position(symbol, last_price, qty)
            sl_price = last_price * (1 - STOP_LOSS_PCT / 100)
            tp_price = last_price * (1 + TAKE_PROFIT_PCT / 100)
            discord_notify(
                title=f"BUY -- {symbol}",
                message=(
                    f"**Preco:** ${last_price:.4f}\n"
                    f"**Quantidade:** {qty}\n"
                    f"**Valor:** ~${qty * last_price:.2f}\n"
                    f"**Stop-loss:** ${sl_price:.4f} (-{STOP_LOSS_PCT}%)\n"
                    f"**Take-profit:** ${tp_price:.4f} (+{TAKE_PROFIT_PCT}%)"
                ),
                color=0x57F287
            )
            return True

        elif signal == "SELL":
            if base_balance < 0.001:
                log.info(f"[{symbol}] Sem {base_asset} para vender")
                return False
            qty = adjust_qty(base_balance * 0.999, step, decimals)
            if qty < min_qty or qty * last_price < min_notional:
                log.warning(f"[{symbol}] Ordem abaixo dos filtros minimos -- ignorando")
                return False
            order = client.order_market_sell(symbol=symbol, quantity=qty)
            log.info(
                f"[{symbol}] [SELL] Ordem executada | "
                f"qty: {qty} {base_asset} @ ~${last_price:.4f} | "
                f"ID: {order['orderId']}"
            )
            if symbol in open_positions:
                del open_positions[symbol]
            discord_notify(
                title=f"SELL -- {symbol}",
                message=(
                    f"**Preco:** ${last_price:.4f}\n"
                    f"**Quantidade:** {qty} {base_asset}\n"
                    f"**Motivo:** sinal do LLM"
                ),
                color=0xFEE75C
            )
            return True

    except BinanceAPIException as e:
        log.error(f"[{symbol}] [ERRO] Binance: {e}")
    except Exception as e:
        log.error(f"[{symbol}] [ERRO] Inesperado: {e}")

    return False


# ── Resumo diario ─────────────────────────────────────────────────────────────

def log_daily_summary():
    """Loga um resumo diario das operacoes -- agendado para meia-noite."""
    usdt = get_balance("USDT")
    total = session_stats["trades_total"]
    wins  = session_stats["trades_win"]
    wr    = (wins / total * 100) if total > 0 else 0
    log.info("=" * 55)
    log.info("RESUMO DIARIO")
    log.info(f"  Saldo USDT atual:   ${usdt:.2f}")
    log.info(f"  Operacoes hoje:     {total}")
    log.info(f"  Win rate:           {wr:.1f}% ({wins}W/{session_stats['trades_loss']}L)")
    log.info(f"  PnL da sessao:      ${session_stats['pnl_total']:+.4f}")
    log.info(f"  Perda acumulada:    ${daily_loss_usdt:.2f} / ${MAX_DAILY_LOSS_USDT:.2f}")
    total_lotes = sum(len(v) for v in open_positions.values())
    log.info(f"  Posicoes abertas:   {total_lotes} lote(s) em {len(open_positions)} par(es)")
    if open_positions:
        for sym, plist in open_positions.items():
            price = get_current_price(sym)
            if not price:
                continue
            for pos in plist:
                change = (price - pos["entry_price"]) / pos["entry_price"] * 100
                log.info(
                    f"    {sym}: entrada ${pos['entry_price']:.4f} | "
                    f"atual ${price:.4f} | {change:+.2f}%"
                )
    log.info("=" * 55)


# ── Monitor de posicoes (ciclo rapido) ────────────────────────────────────────

def monitor_positions():
    """
    Ciclo rapido (a cada MONITOR_INTERVAL_MINUTES).
    Verifica SL/TP em cada lote aberto sem chamar o LLM.
    """
    if not open_positions:
        return

    for symbol in list(open_positions.keys()):
        price = get_current_price(symbol)
        if price is None:
            continue

        positions = open_positions[symbol]
        for idx in range(len(positions) - 1, -1, -1):
            pos = positions[idx]
            entry = pos["entry_price"]
            change = (price - entry) / entry * 100

            if price <= pos["sl"]:
                log.warning(
                    f"[MONITOR] [{symbol}] STOP-LOSS @ ${price:.4f} "
                    f"(entrada ${entry:.4f}, {change:+.2f}%)"
                )
                close_position_at_index(symbol, idx, price, "STOP-LOSS")
            elif price >= pos["tp"]:
                log.info(
                    f"[MONITOR] [{symbol}] TAKE-PROFIT @ ${price:.4f} "
                    f"(entrada ${entry:.4f}, {change:+.2f}%)"
                )
                close_position_at_index(symbol, idx, price, "TAKE-PROFIT")
            else:
                log.info(
                    f"[MONITOR] [{symbol}] OK | entrada: ${entry:.4f} | "
                    f"atual: ${price:.4f} | {change:+.2f}%"
                )


# ── Ciclo de analise (ciclo lento) ────────────────────────────────────────────

def run_cycle():
    global daily_loss_usdt

    log.info("-" * 55)
    log.info(f"Ciclo: {datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")}")
    log.info(
        f"Saldo USDT: ${get_balance('USDT'):.2f} | "
        f"Perda hoje: ${daily_loss_usdt:.2f}/${MAX_DAILY_LOSS_USDT:.2f} | "
        f"Sessao: {session_stats['trades_win']}W/{session_stats['trades_loss']}L "
        f"PnL: ${session_stats['pnl_total']:+.4f}"
    )

    daily_limit_hit = check_daily_loss_limit()

    for symbol in SYMBOLS:
        data = get_market_data(symbol)
        if not data:
            continue

        current_price = data["last_price"]

        plist = open_positions.get(symbol, [])
        if plist:
            for pos in plist:
                entry  = pos["entry_price"]
                change = (current_price - entry) / entry * 100
                log.info(
                    f"[{symbol}] Posicao aberta | "
                    f"entrada: ${entry:.4f} | atual: ${current_price:.4f} | {change:+.2f}%"
                )

        # Analise LLM
        log.info(f"[{symbol}] Analisando...")
        analysis = analyze_with_llm(data)
        log.info(
            f"[{symbol}] Preco: ${current_price:.4f} "
            f"({data['price_change_24h_pct']:+.2f}% 24h) | "
            f"Sinal: {analysis['signal']} | "
            f"Confianca: {analysis['confidence']:.0%}"
        )
        log.info(f"[{symbol}] LLM: {analysis['reasoning']}")

        if not daily_limit_hit and analysis["signal"] != "HOLD":
            execute_trade(symbol, analysis["signal"], analysis["confidence"], current_price)

        time.sleep(10)

    log.info("Ciclo concluido.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("=" * 55)
    log.info("---Crypto Bot iniciado -- OpenRouter + Binance TESTNET by lluizllucas---")
    log.info(f"  Simbolos:        {', '.join(SYMBOLS)}")
    log.info(f"  Analise:         a cada {INTERVAL_MINUTES} min")
    log.info(f"  Monitor SL/TP:   a cada {MONITOR_INTERVAL_MINUTES} min")
    log.info(f"  USDT por trade:  ${TRADE_USDT}")
    log.info(f"  Max lotes/par:   {MAX_POSITIONS_PER_SYMBOL}")
    log.info(f"  Dist. min. entrada: {MIN_ENTRY_DISTANCE_PCT}%")
    log.info(f"  Stop-loss:       {STOP_LOSS_PCT}%")
    log.info(f"  Take-profit:     {TAKE_PROFIT_PCT}%")
    log.info(f"  Limite diario:   ${MAX_DAILY_LOSS_USDT}")
    log.info(f"  Logs:            bot.log.YYYY-MM-DD (historico completo) | bot.error.log.YYYY-MM-DD (erros)")
    log.info("=" * 55)

    # Ciclo de analise LLM
    run_cycle()
    schedule.every(INTERVAL_MINUTES).minutes.do(run_cycle)

    # Ciclo de monitoramento SL/TP
    schedule.every(MONITOR_INTERVAL_MINUTES).minutes.do(monitor_positions)

    # Resumo diario a meia-noite
    schedule.every().day.at("00:00").do(log_daily_summary)

    while True:
        schedule.run_pending()
        time.sleep(15)