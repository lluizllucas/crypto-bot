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
# Bedrock usa {"name", "description", "input_schema"} em vez de
# {"type": "function", "function": {"name", "description", "parameters"}}
# ---------------------------------------------------------------------------

def _to_bedrock_tools(openai_tools: list) -> list:
    """Converte lista de tools no formato OpenAI para o formato Bedrock."""
    result = []
    for t in openai_tools:
        fn = t["function"]
        result.append({
            "toolSpec": {
                "name":         fn["name"],
                "description":  fn.get("description", ""),
                "inputSchema":  {"json": fn["parameters"]},
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
    """Monta o contexto JSON estruturado para envio a LLM."""

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

        "open_positions": positions_ctx,

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
Use recent_performance para ajustar conservadorismo: se win_rate < 40% ou pnl_avg negativo, seja mais cauteloso.
Use market_regime: em mercado ranging (ADX < 20) prefira realizar o lucro; em trending (ADX >= 25) hold e mais justificavel.

Regras de decisao:
- Se o TP foi atingido: chame sell_position (realizar lucro) ou hold_position (segurar se alta continua)
- Se o preco esta proximo do SL (80% do caminho): chame early_exit se acreditar em queda iminente

Regras de confianca para hold_position:
- 1a tentativa de hold: confianca minima {conf_1}
- 2a tentativa: confianca minima {conf_2}
- 3a tentativa em diante: confianca minima {conf_3}

Se a confianca nao atingir o minimo exigido para hold, prefira sell_position.
Se nao houver sinal claro, nao chame nenhuma tool.\
"""

_SYSTEM_BOT = """\
Voce e um analista quantitativo especializado em Bitcoin com foco em preservacao de capital.
Analise o contexto completo de mercado e decida as acoes estrategicas.

Contexto disponivel:
- "llm_memory": suas ultimas 5 decisoes para este par (tool_called + reason + timestamp)
- "recent_performance": resumo das ultimas 10 operacoes fechadas (win_rate, pnl_avg, best, worst)
- "market_regime": regime atual via ADX (trending/ranging) + setup_score pre-calculado (0-100)

Use llm_memory para evitar entrar em sequencias de erros ou abrir posicoes muito proximas de decisoes recentes.
Use recent_performance para calibrar confianca: se win_rate < 40%, eleve o limiar de confianca exigido.
Use market_regime: setup_score < 40 indica mercado sem setup claro — evite abrir posicoes.
Em mercado ranging (ADX < 20), seja conservador com novas entradas; em trending (ADX >= 25), setups tecnicos tem maior probabilidade.

Acoes disponiveis:
- open_position: apenas se houver setup claro de entrada (RSI, EMA, volume e momentum alinhados)
- sell_position: se uma posicao aberta deve ser encerrada por deterioracao do cenario
- Nao chame nenhuma tool se o mercado estiver ambiguo ou sem setup definido

Regras de risco para open_position:
- sl_percentage: use o ATR como referencia (ATR / preco * 100). Minimo 1.0%, maximo 5.0%
- tp_percentage: relacao risco/retorno minima de 1:2 em relacao ao sl_percentage
- confianca minima para executar: {min_confidence}

Em caso de duvida, nao abra posicao.\
"""


# ---------------------------------------------------------------------------
# Chamada ao Bedrock com agentic reasoning loop
# ---------------------------------------------------------------------------

def _call_llm(system: str, context: dict, action_tools: list, process: str) -> list:
    """
    Chama o Bedrock (Claude Haiku) com contexto, tools de consulta e tools de acao.

    Loop de agentic reasoning:
    1. LLM recebe contexto + todas as tools (consulta + acao)
    2. Se chamar uma tool de consulta → executa, adiciona resultado, repete
    3. Se chamar uma tool de acao → retorna as tool_calls de acao
    4. Se nao chamar nenhuma tool → retorna lista vazia
    5. Maximo de _MAX_QUERY_ROUNDS rodadas de consulta

    Retorna lista de tool_calls de acao normalizados como objetos duck-typed
    compatíveis com parse_tool_calls (que espera tc.function.name e tc.function.arguments).
    """
    all_openai_tools = action_tools + TOOLS_QUERY
    bedrock_tools    = _to_bedrock_tools(all_openai_tools)
    query_names      = {t["function"]["name"] for t in TOOLS_QUERY}

    user_content = f"Contexto de mercado atual:\n{json.dumps(context, indent=2, ensure_ascii=False)}"
    messages = [{"role": "user", "content": [{"text": user_content}]}]

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
                    inferenceConfig={"maxTokens": 1024, "temperature": 0.3},
                )

                output_msg  = response["output"]["message"]
                stop_reason = response["stopReason"]

                # Sem tool use → sem acao
                if stop_reason != "tool_use":
                    return []

                # Separa tool uses de consulta e de acao
                tool_uses    = [b for b in output_msg["content"] if b.get("type") == "toolUse"]
                query_uses   = [u for u in tool_uses if u["name"] in query_names]
                action_uses  = [u for u in tool_uses if u["name"] not in query_names]

                # Tem acao → converte para duck-type compatível com parse_tool_calls e retorna
                if action_uses:
                    return [_BedrockToolCall(u) for u in action_uses]

                # Só consultas mas atingiu limite → encerra sem acao
                if query_rounds >= _MAX_QUERY_ROUNDS:
                    log.warning(
                        f"[{process}] Limite de {_MAX_QUERY_ROUNDS} rodadas de consulta atingido "
                        f"— encerrando sem acao"
                    )
                    return []

                # Executa tools de consulta e adiciona resultado ao historico
                msgs.append({"role": "assistant", "content": output_msg["content"]})

                tool_results = []
                for u in query_uses:
                    result = dispatch_query_tool(u["name"], u["input"])
                    log.info(
                        f"[{process}] Tool de consulta: {u['name']} | "
                        f"args: {u['input']} | "
                        f"result keys: {list(result.keys())}"
                    )
                    tool_results.append({
                        "type":        "toolResult",
                        "toolUseId":   u["toolUseId"],
                        "content":     json.dumps(result, ensure_ascii=False),
                    })

                msgs.append({"role": "user", "content": tool_results})
                query_rounds += 1

        except Exception as e:
            if attempt < 3:
                log.warning(f"[{process}] Tentativa {attempt} falhou: {_sanitize(str(e))} -- retentando")
            else:
                log.error(f"[{process}] Erro apos 3 tentativas: {_sanitize(str(e))}")

    return []


# ---------------------------------------------------------------------------
# Duck-type para compatibilidade com parse_tool_calls (espera tc.function.name/arguments)
# ---------------------------------------------------------------------------

class _BedrockToolCall:
    """Adapta o formato de tool use do Bedrock para a interface esperada por parse_tool_calls."""

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
# Funcoes publicas
# ---------------------------------------------------------------------------

def analyze_monitor(
    data:                MarketData,
    open_positions:      dict,
    triggered_positions: list[Position],
    trigger_type:        str,
) -> list[dict]:
    """
    Chamado pelo monitor (check_sl_tp) quando TP e atingido ou preco esta proximo do SL.
    Retorna lista de acoes normalizadas via parse_tool_calls.
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

    tool_calls = _call_llm(system, context, TOOLS_MONITOR, "monitor")
    return parse_tool_calls(tool_calls, "monitor")


def analyze_bot(
    data:           MarketData,
    open_positions: dict,
) -> list[dict]:
    """
    Chamado pelo ciclo principal (analysis_llm.py) para decisoes estrategicas.
    Retorna lista de acoes normalizadas via parse_tool_calls.
    """
    system     = _SYSTEM_BOT.format(min_confidence=MIN_CONFIDENCE)
    context    = build_context(data, open_positions)
    tool_calls = _call_llm(system, context, TOOLS_BOT, "bot")
    return parse_tool_calls(tool_calls, "bot")