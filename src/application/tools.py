"""
Definicao e processamento das tools disponibilizadas ao LLM.

Responsabilidades:
- Schemas JSON enviados ao LLM (o que ele pode "chamar")
- Processamento das tool_calls retornadas pelo LLM
- Mapeamento de cada tool para a funcao real de execucao
- Tools de consulta: o LLM pode buscar mais contexto antes de decidir

O LLM nunca executa nada diretamente — ele expressa intencao via tool_call,
e este modulo valida e despacha para a funcao correta.

Tools de acao (risk_manager):   open_position, sell_position, hold_position, early_exit
Tools de consulta (market_queries): get_candles, get_rsi_history, get_volume_profile,
                                    get_ema_history, get_recent_highs_lows,
                                    get_volatility_history, get_range_breakdown,
                                    get_fear_greed_history
"""

import json
import logging

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas das tools — enviados ao LLM como descricao do que ele pode chamar
# ---------------------------------------------------------------------------

TOOLS_MONITOR = [
    {
        "type": "function",
        "function": {
            "name": "sell_position",
            "description": "Vende uma posicao especifica realizando o lucro no TP.",
            "parameters": {
                "type": "object",
                "properties": {
                    "position_id": {"type": "string", "description": "db_id da posicao a ser vendida"},
                    "confidence":  {"type": "number", "description": "Confianca na decisao (0.0 a 1.0)"},
                    "reason":      {"type": "string", "description": "Justificativa objetiva em ate 2 frases"},
                },
                "required": ["position_id", "confidence", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hold_position",
            "description": "Mantem uma posicao aberta apos o TP ser atingido, apostando em continuacao da alta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "position_id": {"type": "string", "description": "db_id da posicao a ser mantida"},
                    "confidence":  {"type": "number", "description": "Confianca na decisao (0.0 a 1.0)"},
                    "reason":      {"type": "string", "description": "Justificativa objetiva em ate 2 frases"},
                },
                "required": ["position_id", "confidence", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "early_exit",
            "description": "Sai antecipadamente de uma posicao antes do SL ser atingido.",
            "parameters": {
                "type": "object",
                "properties": {
                    "position_id": {"type": "string", "description": "db_id da posicao a sair"},
                    "confidence":  {"type": "number", "description": "Confianca na decisao (0.0 a 1.0)"},
                    "reason":      {"type": "string", "description": "Justificativa objetiva em ate 2 frases"},
                },
                "required": ["position_id", "confidence", "reason"],
            },
        },
    },
]

TOOLS_BOT = [
    {
        "type": "function",
        "function": {
            "name": "open_position",
            "description": "Solicita abertura de nova posicao de compra.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":        {"type": "string", "description": "Par a comprar, ex: BTCUSDT"},
                    "confidence":    {"type": "number", "description": "Confianca na decisao (0.0 a 1.0)"},
                    "sl_percentage": {"type": "number", "description": "Stop-loss recomendado em % (1.0 a 5.0)"},
                    "tp_percentage": {"type": "number", "description": "Take-profit recomendado em % (minimo 2x o sl_percentage)"},
                    "reason":        {"type": "string", "description": "Justificativa objetiva em ate 2 frases"},
                },
                "required": ["symbol", "confidence", "sl_percentage", "tp_percentage", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sell_position",
            "description": "Vende uma posicao especifica por decisao estrategica (nao por SL/TP).",
            "parameters": {
                "type": "object",
                "properties": {
                    "position_id": {"type": "string", "description": "db_id da posicao a ser vendida"},
                    "confidence":  {"type": "number", "description": "Confianca na decisao (0.0 a 1.0)"},
                    "reason":      {"type": "string", "description": "Justificativa objetiva em ate 2 frases"},
                },
                "required": ["position_id", "confidence", "reason"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Parser de tool_calls — converte resposta bruta do LLM em lista de acoes
# ---------------------------------------------------------------------------

def parse_tool_calls(tool_calls: list, process: str) -> list[dict]:
    """
    Converte a lista de tool_calls retornada pelo LLM em lista de acoes normalizadas.
    Retorna: [{"tool": str, "args": dict}, ...]
    """
    actions = []

    for tc in tool_calls:
        try:
            args = json.loads(tc.function.arguments)

            actions.append({
                "tool": tc.function.name,
                "args": args,
            })
            
            log.info(
                f"[{process.upper()}] LLM chamou {tc.function.name} | "
                f"position_id: {args.get('position_id', args.get('symbol', '-'))} | "
                f"confidence: {args.get('confidence', '-')} | "
                f"reason: {args.get('reason', '')}"
            )
        except Exception as e:
            log.warning(f"[{process.upper()}] Erro ao parsear tool_call: {e}")

    return actions


# ---------------------------------------------------------------------------
# Processadores por processo
# ---------------------------------------------------------------------------

def process_monitor_actions(
    actions:         list[dict],
    symbol:          str,
    pos,
    price:           float,
    exit_llm_log_id: str | None,
    apply_tp_hold_fn,
    close_position_fn,
    tp_threshold:    float,
    min_conf_early:  float,
    trigger_type:    str,
):
    """
    Processa as acoes do LLM para o monitor (check_sl_tp).

    Parametros injetados para evitar import circular com risk_manager:
    - apply_tp_hold_fn:  risk_manager.apply_tp_hold
    - close_position_fn: risk_manager.close_position_at_index (parcialmente aplicada com idx)
    """
    acted = False

    for action in actions:
        args = action["args"]

        if args.get("position_id") != pos.db_id:
            continue

        tool       = action["tool"]
        confidence = float(args.get("confidence", 0))
        reason     = args.get("reason", "")

        if trigger_type == "TP":
            if tool == "sell_position":
                close_position_fn("TAKE-PROFIT", exit_llm_log_id)
                acted = True
                break

            if tool == "hold_position":
                if confidence >= tp_threshold:
                    log.info(
                        f"[MONITOR] [{symbol}] LLM segura no TP "
                        f"(conf {confidence:.2f} >= {tp_threshold:.2f}, "
                        f"tentativa #{pos.tp_hold_count + 1})"
                    )
                    apply_tp_hold_fn()
                else:
                    log.info(
                        f"[MONITOR] [{symbol}] LLM quer segurar mas confianca insuficiente "
                        f"({confidence:.2f} < {tp_threshold:.2f}) — vendendo"
                    )
                    close_position_fn("TAKE-PROFIT", exit_llm_log_id)
                acted = True
                break

        if trigger_type == "EARLY_EXIT":
            if tool == "early_exit":
                if confidence >= min_conf_early:
                    log.warning(
                        f"[MONITOR] [{symbol}] EARLY EXIT solicitado pelo LLM "
                        f"(conf {confidence:.2f}) @ ${price:.4f}"
                    )
                    close_position_fn("EARLY-EXIT", exit_llm_log_id)
                else:
                    log.info(
                        f"[MONITOR] [{symbol}] LLM quer early exit mas confianca insuficiente "
                        f"({confidence:.2f} < {min_conf_early:.2f}) — mantendo posicao"
                    )
                acted = True
                break

    return acted


def process_bot_actions(
    actions:          list[dict],
    symbol:           str,
    price:            float,
    llm_log_id:       str | None,
    execute_buy_fn,
    execute_sell_fn,
    min_conf_sell:    float = 0.70,
):
    """
    Processa as acoes do LLM para o ciclo principal (bot.py).

    Parametros injetados:
    - execute_buy_fn:  risk_manager.execute_buy
    - execute_sell_fn: risk_manager.execute_sell_by_id

    Validacoes de confianca:
    - open_position: delegada ao execute_buy (usa MIN_CONFIDENCE do config)
    - sell_position: validada aqui com min_conf_sell antes de executar
    """
    for action in actions:
        tool       = action["tool"]
        args       = action["args"]
        confidence = float(args.get("confidence", 0))

        if tool == "open_position":
            execute_buy_fn(
                symbol=     symbol,
                confidence= confidence,
                sl_pct=     float(args.get("sl_percentage", 2.5)),
                tp_pct=     float(args.get("tp_percentage", 5.0)),
                reason=     args.get("reason", ""),
                last_price= price,
                llm_log_id= llm_log_id,
            )

        elif tool == "sell_position":
            if confidence < min_conf_sell:
                log.info(
                    f"[BOT] [{symbol}] sell_position ignorado — confianca insuficiente "
                    f"({confidence:.2f} < {min_conf_sell:.2f})"
                )
                continue

            execute_sell_fn(
                symbol=          symbol,
                position_id=     args.get("position_id", ""),
                confidence=      confidence,
                reason=          args.get("reason", "SELL estrategico"),
                current_price=   price,
                exit_llm_log_id= llm_log_id,
            )


# ---------------------------------------------------------------------------
# Schemas das tools de consulta — o LLM usa quando precisa de mais contexto
# ---------------------------------------------------------------------------

TOOLS_QUERY = [
    {
        "type": "function",
        "function": {
            "name": "get_candles",
            "description": (
                "Busca candles OHLCV de um timeframe especifico. "
                "Use para analisar tendencia em 4h ou precisao de entrada em 15m."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":    {"type": "string", "description": "Par, ex: BTCUSDT"},
                    "timeframe": {
                        "type": "string",
                        "enum": ["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
                        "description": "Timeframe dos candles",
                    },
                    "limit": {"type": "integer", "description": "Numero de candles (5 a 100)", "default": 20},
                },
                "required": ["symbol", "timeframe"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rsi_history",
            "description": (
                "Retorna o historico de RSI das ultimas N velas (1h). "
                "Use para identificar divergencias de longo prazo e tendencia do momentum."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":  {"type": "string", "description": "Par, ex: BTCUSDT"},
                    "periods": {"type": "integer", "description": "Numero de velas (5 a 50)", "default": 20},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_volume_profile",
            "description": (
                "Retorna volume por candle das ultimas N horas com classificacao relativa a media. "
                "Use para confirmar se o volume atual e realmente anomalo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":  {"type": "string", "description": "Par, ex: BTCUSDT"},
                    "periods": {"type": "integer", "description": "Numero de horas (5 a 48)", "default": 24},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ema_history",
            "description": (
                "Retorna a distancia percentual do preco em relacao a uma EMA ao longo do tempo. "
                "Use para identificar preco muito esticado (candidato a mean reversion) ou recuo saudavel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":  {"type": "string", "description": "Par, ex: BTCUSDT"},
                    "ema":     {"type": "integer", "enum": [20, 50, 200], "description": "Periodo da EMA"},
                    "periods": {"type": "integer", "description": "Numero de velas historicas (5 a 50)", "default": 20},
                },
                "required": ["symbol", "ema"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_highs_lows",
            "description": (
                "Retorna as maximas e minimas locais das ultimas N velas (1h), "
                "identificando suportes e resistencias recentes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":  {"type": "string", "description": "Par, ex: BTCUSDT"},
                    "periods": {"type": "integer", "description": "Numero de velas (10 a 100)", "default": 48},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_volatility_history",
            "description": (
                "Retorna o ATR das ultimas N velas (1h). "
                "Use para ver se a volatilidade esta aumentando ou diminuindo e ajustar SL/TP."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":  {"type": "string", "description": "Par, ex: BTCUSDT"},
                    "periods": {"type": "integer", "description": "Numero de velas (5 a 50)", "default": 20},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_range_breakdown",
            "description": (
                "Retorna o range (high-low) de diferentes janelas de tempo e a posicao atual do preco. "
                "Use para comparar ranges e identificar contracao ou expansao de volatilidade."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":  {"type": "string", "description": "Par, ex: BTCUSDT"},
                    "periods": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Lista de janelas em horas, ex: [24, 48, 168]. Maximo 6 valores.",
                        "default": [24, 48, 168],
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fear_greed_history",
            "description": (
                "Retorna o Fear & Greed Index dos ultimos N dias. "
                "Use para ver se o sentimento esta mudando rapidamente ou se mantem estavel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Numero de dias (1 a 30)", "default": 7},
                },
                "required": [],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatcher das tools de consulta
# ---------------------------------------------------------------------------

def dispatch_query_tool(tool_name: str, args: dict) -> dict:
    """
    Executa a tool de consulta solicitada pelo LLM e retorna o resultado.
    Chamado durante o loop de agentic reasoning em llm_analyst.py.
    """
    from src.application.market_queries import (
        query_candles,
        query_rsi_history,
        query_volume_profile,
        query_ema_history,
        query_recent_highs_lows,
        query_volatility_history,
        query_range_breakdown,
        query_fear_greed_history,
    )

    symbol = args.get("symbol", "BTCUSDT")

    dispatch = {
        "get_candles":            lambda: query_candles(
                                      symbol,
                                      args.get("timeframe", "1h"),
                                      int(args.get("limit", 20)),
                                  ),
        "get_rsi_history":        lambda: query_rsi_history(
                                      symbol,
                                      int(args.get("periods", 20)),
                                  ),
        "get_volume_profile":     lambda: query_volume_profile(
                                      symbol,
                                      int(args.get("periods", 24)),
                                  ),
        "get_ema_history":        lambda: query_ema_history(
                                      symbol,
                                      int(args.get("ema", 20)),
                                      int(args.get("periods", 20)),
                                  ),
        "get_recent_highs_lows":  lambda: query_recent_highs_lows(
                                      symbol,
                                      int(args.get("periods", 48)),
                                  ),
        "get_volatility_history": lambda: query_volatility_history(
                                      symbol,
                                      int(args.get("periods", 20)),
                                  ),
        "get_range_breakdown":    lambda: query_range_breakdown(
                                      symbol,
                                      list(args.get("periods", [24, 48, 168])),
                                  ),
        "get_fear_greed_history": lambda: query_fear_greed_history(
                                      int(args.get("days", 7)),
                                  ),
    }

    fn = dispatch.get(tool_name)
    
    if fn is None:
        return {"error": f"Tool desconhecida: {tool_name}"}

    try:
        result = fn()
        log.info(f"[QUERY] Tool {tool_name} executada com sucesso")
        return result
    except Exception as e:
        log.error(f"[QUERY] Erro ao executar {tool_name}: {e}")
        return {"error": str(e)}
