"""
Analise de mercado via LLM (AWS Bedrock — Claude Haiku 4.5).
Recebe MarketData completo e posicoes abertas.
O LLM age via tool use — nao retorna JSON generico.

Schemas das tools e processamento das respostas estao em application/tools.py.
"""

import json
import logging
from datetime import datetime, timezone

import boto3

log = logging.getLogger("bot")

from src.config import BEDROCK_MODEL_ID, BEDROCK_REGION, MIN_CONFIDENCE, TP_HOLD_MIN_CONFIDENCE
from src.domain.models import MarketData, Position
from src.application.tools import TOOLS_MONITOR, TOOLS_BOT, TOOLS_QUERY, parse_tool_calls, dispatch_query_tool
from src.infra.supabase.repository import get_recent_llm_decisions, get_recent_performance


_bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)

_MAX_QUERY_ROUNDS = 3


# ---------------------------------------------------------------------------
# Conversao de schemas OpenAI → Bedrock
# ---------------------------------------------------------------------------

def _to_bedrock_tools(openai_tools: list) -> list:
    result = []
    for t in openai_tools:
        fn = t["function"]
        result.append({
            "toolSpec": {
                "name":        fn["name"],
                "description": fn.get("description", ""),
                "inputSchema": {"json": fn["parameters"]},
            }
        })
    return result


# ---------------------------------------------------------------------------
# Sanitizacao de texto
# ---------------------------------------------------------------------------

def _sanitize(text: str) -> str:
    replacements = {
        "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2026": "...", "\u00b7": ".",
    }
    for char, rep in replacements.items():
        text = text.replace(char, rep)
    return text


# ---------------------------------------------------------------------------
# Montagem de contexto
# ---------------------------------------------------------------------------

def build_context(data: MarketData, open_positions: dict | None = None) -> dict:
    if data.ema20 > data.ema50 > data.ema200:
        ema_trend = "bullish"
    elif data.ema20 < data.ema50 < data.ema200:
        ema_trend = "bearish"
    else:
        ema_trend = "neutral"

    positions_ctx = []
    if open_positions:
        for pos in open_positions.get(data.symbol, []):
            pnl_pct     = (data.price - pos.entry_price) / pos.entry_price * 100
            dist_sl_pct = (pos.entry_price - pos.sl) / pos.entry_price * 100
            dist_tp_pct = (pos.tp - pos.entry_price) / pos.entry_price * 100
            hours_open  = (
                datetime.now(timezone.utc) - pos.ts.replace(tzinfo=timezone.utc)
                if pos.ts.tzinfo is None else
                datetime.now(timezone.utc) - pos.ts
            ).total_seconds() / 3600

            positions_ctx.append({
                "position_id":   pos.db_id,
                "entry_price":   pos.entry_price,
                "qty":           pos.qty,
                "sl":            pos.sl,
                "tp":            pos.tp,
                "original_sl":   pos.original_sl,
                "original_tp":   pos.original_tp,
                "pnl_pct":       round(pnl_pct, 2),
                "dist_sl_pct":   round(dist_sl_pct, 2),
                "dist_tp_pct":   round(dist_tp_pct, 2),
                "hours_open":    round(hours_open, 1),
                "tp_hold_count": pos.tp_hold_count,
            })

    return {
        "symbol": data.symbol,
        "price":  data.price,
        "indicators": {
            "rsi_1h":         data.rsi_1h,
            "rsi_direction":  data.rsi_direction,
            "rsi_divergence": data.rsi_divergence,
            "ema20":          data.ema20,
            "ema50":          data.ema50,
            "ema200":         data.ema200,
            "ema_trend":      ema_trend,
            "atr":            data.atr,
            "bb_upper":       data.bb_upper,
            "bb_lower":       data.bb_lower,
            "bb_mid":         data.bb_mid,
            "bb_width":       data.bb_width,
            "bb_pct_b":       data.bb_pct_b,
            "macd_line":      data.macd_line,
            "macd_signal":    data.macd_signal,
            "macd_histogram": data.macd_histogram,
        },
        "price_action": {
            "change_pct_1h":  data.change_pct_1h,
            "change_pct_4h":  data.change_pct_4h,
            "change_pct_24h": data.change_pct_24h,
            "recent_candles": [
                {"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                for c in data.recent_candles
            ],
        },
        "volume": {
            "volume_24h":    data.volume_24h,
            "avg_volume_5h": data.avg_volume_5h,
            "volume_ratio":  data.volume_ratio,
        },
        "ranges": {
            "range_position_24h": data.range_position_24h,
            "range_high_24h":     data.range_high_24h,
            "range_low_24h":      data.range_low_24h,
            "range_position_7d":  data.range_position_7d,
            "range_high_7d":      data.range_high_7d,
            "range_low_7d":       data.range_low_7d,
            "range_high_30d":     data.range_high_30d,
            "range_low_30d":      data.range_low_30d,
        },
        "sentiment": {
            "fear_greed":       data.fear_greed,
            "fear_greed_label": data.fear_greed_label,
        },
        "market_regime": {
            "adx":         data.adx,
            "plus_di":     data.plus_di,
            "minus_di":    data.minus_di,
            "regime":      data.market_regime,
            "setup_score": data.setup_score,
        },
        "open_positions":     positions_ctx,
        "llm_memory":         get_recent_llm_decisions(data.symbol, limit=5),
        "recent_performance": get_recent_performance(data.symbol, limit=10),
    }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_MONITOR = """\
Voce e um analista quantitativo especializado em Bitcoin atuando como gestor de risco.
Seu papel e gerenciar posicoes abertas que atingiram um nivel critico (TP ou proximo do SL).

Contexto disponivel:
- "llm_memory": suas ultimas 5 decisoes para este par (tool_called + reason + timestamp)
- "recent_performance": resumo das ultimas 10 operacoes fechadas (win_rate, pnl_avg, best, worst)
- "market_regime": regime atual (trending/ranging) via ADX + DI+ / DI- + setup_score

Use llm_memory para evitar repeticao de erros recentes e calibrar sua decisao.
Use recent_performance como contexto historico para entender o ambiente recente.
Use market_regime: em ranging (ADX < 20) prefira realizar lucro; em trending (ADX >= 25) hold e justificavel.

Regras de decisao:
- TP atingido: chame sell_position ou hold_position
- Preco proximo do SL (80%): chame early_exit se acreditar em queda iminente

Regras de confianca para hold_position:
- 1a tentativa: confianca minima {conf_1}
- 2a tentativa: confianca minima {conf_2}
- 3a tentativa em diante: confianca minima {conf_3}

Se confianca insuficiente para hold, prefira sell_position.

IMPORTANTE: Voce DEVE sempre escrever um paragrafo explicando sua analise e decisao, independentemente de acionar ou nao uma tool. Sem texto de analise a resposta e invalida.
"""

_SYSTEM_BOT = """\
Voce e um analista quantitativo especializado em Bitcoin com foco em preservacao de capital.
Analise o contexto completo de mercado e decida as acoes estrategicas.

Contexto disponivel:
- "llm_memory": suas ultimas 5 decisoes para este par (tool_called + reason + timestamp)
- "recent_performance": resumo das ultimas 10 operacoes fechadas (win_rate, pnl_avg, best, worst)
- "market_regime": regime atual via ADX (trending/ranging) + setup_score pre-calculado (0-100)

Use llm_memory para evitar sequencias de erros ou entradas muito proximas de decisoes recentes.
Use recent_performance como contexto historico, mas nao altere o limiar de confianca com base nele.
Use market_regime: setup_score < 40 indica sem setup claro — evite abrir posicoes.
Em ranging (ADX < 20), conservador com novas entradas; em trending (ADX >= 25), setups tem maior probabilidade.

Acoes disponiveis:
- open_position: apenas se houver setup claro (RSI, EMA, volume e momentum alinhados)
- sell_position: se posicao aberta deve ser encerrada por deterioracao do cenario
- Nao chame nenhuma tool se mercado ambiguo ou sem setup definido

Regras para open_position:
- sl_percentage: ATR / preco * 100. Minimo 1.0%, maximo 5.0%
- tp_percentage: risco/retorno minimo 1:2 em relacao ao sl_percentage
- confianca minima: {min_confidence}

Em caso de duvida, nao abra posicao.

IMPORTANTE: Voce DEVE sempre escrever um paragrafo explicando sua analise e decisao, independentemente de acionar ou nao uma tool. Sem texto de analise a resposta e invalida.
"""


# ---------------------------------------------------------------------------
# Chamada ao Bedrock com agentic reasoning loop
# ---------------------------------------------------------------------------

def _call_llm(system: str, context: dict, action_tools: list, process: str) -> tuple[list, str]:
    """
    Chama o Bedrock com contexto e tools.
    Retorna tupla (tool_calls, reasoning):
    - tool_calls: acoes duck-typed para parse_tool_calls (vazia se HOLD)
    - reasoning:  texto explicativo do LLM (sempre presente, especialmente no HOLD)
    """
    all_openai_tools = action_tools + TOOLS_QUERY
    bedrock_tools    = _to_bedrock_tools(all_openai_tools)
    query_names      = {t["function"]["name"] for t in TOOLS_QUERY}

    user_content = f"Contexto de mercado atual:\n{json.dumps(context, indent=2, ensure_ascii=False)}"
    messages     = [{"role": "user", "content": [{"text": user_content}]}]

    for attempt in range(1, 4):
        query_rounds = 0
        msgs         = list(messages)

        try:
            while True:
                response = _bedrock.converse(
                    modelId=BEDROCK_MODEL_ID,
                    system=[{"text": system}],
                    messages=msgs,
                    toolConfig={"tools": bedrock_tools},
                    inferenceConfig={"maxTokens": 2048, "temperature": 0.3},
                )

                output_msg  = response["output"]["message"]
                stop_reason = response["stopReason"]

                # Extrai texto de reasoning presente em qualquer stopReason
                text_blocks = [b["text"] for b in output_msg["content"] if "text" in b]
                reasoning   = " ".join(text_blocks).strip()

                # Sem tool use → loga reasoning e encerra
                if stop_reason != "tool_use":
                    if reasoning:
                        log.info(f"[{process}] LLM HOLD — {reasoning[:400]}")
                    return [], reasoning

                # Separa consulta de acao
                tool_uses   = [b["toolUse"] for b in output_msg["content"] if "toolUse" in b]
                query_uses  = [u for u in tool_uses if u["name"] in query_names]
                action_uses = [u for u in tool_uses if u["name"] not in query_names]

                # Tem acao → retorna imediatamente
                if action_uses:
                    return [_BedrockToolCall(u) for u in action_uses], reasoning

                # Só consultas mas atingiu limite
                if query_rounds >= _MAX_QUERY_ROUNDS:
                    log.warning(
                        f"[{process}] Limite de {_MAX_QUERY_ROUNDS} rodadas de consulta atingido "
                        f"— encerrando sem acao"
                    )
                    return [], reasoning

                # Executa tools de consulta
                msgs.append({"role": "assistant", "content": output_msg["content"]})

                tool_results = []
                for u in query_uses:
                    result = dispatch_query_tool(u["name"], u["input"])
                    log.info(
                        f"[{process}] Tool de consulta: {u['name']} | "
                        f"args: {u['input']} | result keys: {list(result.keys())}"
                    )
                    tool_results.append({
                        "type":      "toolResult",
                        "toolUseId": u["toolUseId"],
                        "content":   json.dumps(result, ensure_ascii=False),
                    })

                msgs.append({"role": "user", "content": tool_results})
                query_rounds += 1

        except Exception as e:
            if attempt < 3:
                log.warning(f"[{process}] Tentativa {attempt} falhou: {_sanitize(str(e))} -- retentando")
            else:
                log.error(f"[{process}] Erro apos 3 tentativas: {_sanitize(str(e))}")

    return [], ""


# ---------------------------------------------------------------------------
# Duck-type para compatibilidade com parse_tool_calls
# ---------------------------------------------------------------------------

class _BedrockToolCall:
    """Adapta tool use do Bedrock para a interface esperada por parse_tool_calls."""

    class _Function:
        def __init__(self, name: str, arguments: str):
            self.name      = name
            self.arguments = arguments

    def __init__(self, tool_use: dict):
        self.function = self._Function(
            name=      tool_use["name"],
            arguments= json.dumps(tool_use["input"]),
        )


# ---------------------------------------------------------------------------
# Funcoes publicas — retornam tupla (actions, reasoning)
# ---------------------------------------------------------------------------

def analyze_monitor(
    data:                MarketData,
    open_positions:      dict,
    triggered_positions: list[Position],
    trigger_type:        str,
) -> tuple[list[dict], str]:
    """
    Chamado pelo monitor (check_sl_tp) quando TP e atingido ou preco esta proximo do SL.
    Retorna (actions, reasoning).
    """
    conf   = TP_HOLD_MIN_CONFIDENCE
    system = _SYSTEM_MONITOR.format(
        conf_1=conf[0],
        conf_2=conf[1] if len(conf) > 1 else conf[0],
        conf_3=conf[2] if len(conf) > 2 else conf[-1],
    )

    context = build_context(data, open_positions)
    context["trigger_type"]        = trigger_type
    context["triggered_positions"] = [p.db_id for p in triggered_positions]

    tool_calls, reasoning = _call_llm(system, context, TOOLS_MONITOR, "monitor")
    return parse_tool_calls(tool_calls, "monitor"), reasoning


def analyze_bot(
    data:           MarketData,
    open_positions: dict,
) -> tuple[list[dict], str]:
    """
    Chamado pelo ciclo principal (analysis_llm.py) para decisoes estrategicas.
    Retorna (actions, reasoning).
    """
    system                = _SYSTEM_BOT.format(min_confidence=MIN_CONFIDENCE)
    context               = build_context(data, open_positions)
    tool_calls, reasoning = _call_llm(system, context, TOOLS_BOT, "bot")
    return parse_tool_calls(tool_calls, "bot"), reasoning