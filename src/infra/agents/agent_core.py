"""
Core do agente LLM: loop de raciocinio, dispatch de queries e resultado.
Compartilhado por todos os agentes especializados.
"""

import json
import logging

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.domain.entities.position import Position
from src.domain.value_objects.market_data import MarketData

from src.infra.agents.schemas.tool_schemas import TOOLS_QUERY
from src.infra.agents.providers.bedrock_provider import BedrockProvider, to_bedrock_tools, sanitize
from src.infra.persistence.repository import get_recent_llm_decisions, get_recent_performance

log = logging.getLogger("bot")

_provider = BedrockProvider()

_MAX_QUERY_ROUNDS = 10
_QUERY_NAMES = {t["function"]["name"] for t in TOOLS_QUERY}


@dataclass
class AgentResult:
    reasoning:   str
    tool_called: str | None
    executed:    bool = False
    context:     dict = field(default_factory=dict)


def build_context(data: MarketData, positions: list[Position] | None = None) -> dict:
    if data.ema20 > data.ema50 > data.ema200:
        ema_trend = "bullish"
    elif data.ema20 < data.ema50 < data.ema200:
        ema_trend = "bearish"
    else:
        ema_trend = "neutral"

    positions_ctx = []
    if positions:
        for pos in positions:
            pnl_pct     = (data.price - pos.entry_price) / pos.entry_price * 100
            dist_sl_pct = (pos.entry_price - pos.sl) / pos.entry_price * 100
            dist_tp_pct = (pos.tp - pos.entry_price) / pos.entry_price * 100
            hours_open  = (
                datetime.now(timezone.utc) -
                (pos.ts.replace(tzinfo=timezone.utc) if pos.ts.tzinfo is None else pos.ts)
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


def _dispatch_query(name: str, args: dict) -> dict:
    from src.infra.agents.tools.market.get_candles import query_candles
    from src.infra.agents.tools.market.get_market_data import (
        query_rsi_history, query_volume_profile, query_ema_history,
        query_recent_highs_lows, query_volatility_history,
        query_range_breakdown, query_fear_greed_history,
    )

    symbol = args.get("symbol", "BTCUSDT")

    dispatch = {
        "get_candles":            lambda: query_candles(symbol, args.get("timeframe", "1h"), int(args.get("limit", 20))),
        "get_rsi_history":        lambda: query_rsi_history(symbol, int(args.get("periods", 20))),
        "get_volume_profile":     lambda: query_volume_profile(symbol, int(args.get("periods", 24))),
        "get_ema_history":        lambda: query_ema_history(symbol, int(args.get("ema", 20)), int(args.get("periods", 20))),
        "get_recent_highs_lows":  lambda: query_recent_highs_lows(symbol, int(args.get("periods", 48))),
        "get_volatility_history": lambda: query_volatility_history(symbol, int(args.get("periods", 20))),
        "get_range_breakdown":    lambda: query_range_breakdown(symbol, list(args.get("periods", [24, 48, 168]))),
        "get_fear_greed_history": lambda: query_fear_greed_history(int(args.get("days", 7))),
    }

    fn = dispatch.get(name)
    if fn is None:
        return {"error": f"Tool desconhecida: {name}"}

    try:
        result = fn()
        log.info(f"[QUERY] {name} | args: {args} | keys: {list(result.keys())}")
        return result
    except Exception as e:
        log.error(f"[QUERY] Erro em {name}: {e}")
        return {"error": str(e)}


def run_agent(
    system:       str,
    context:      dict,
    action_tools: list,
    action_names: set,
    process:      str,
    on_action,
) -> AgentResult:
    bedrock_tools = to_bedrock_tools(action_tools + TOOLS_QUERY)
    user_content  = f"Contexto de mercado atual:\n{json.dumps(context, indent=2, ensure_ascii=False)}"
    messages      = [{"role": "user", "content": [{"text": user_content}]}]

    for attempt in range(1, 4):
        query_rounds = 0
        msgs = list(messages)

        try:
            while True:
                response    = _provider.converse(system=system, messages=msgs, tools=bedrock_tools)
                output_msg  = response["output"]["message"]
                stop_reason = response["stopReason"]

                text_blocks = [b["text"] for b in output_msg["content"] if "text" in b]
                reasoning   = " ".join(text_blocks).strip()

                if stop_reason != "tool_use":
                    if reasoning:
                        log.info(f"[{process}] LLM HOLD — {reasoning[:400]}")
                    return AgentResult(reasoning=reasoning, tool_called=None)

                tool_uses   = [b["toolUse"] for b in output_msg["content"] if "toolUse" in b]
                query_uses  = [u for u in tool_uses if u["name"] in _QUERY_NAMES]
                action_uses = [u for u in tool_uses if u["name"] in action_names]

                if action_uses:
                    u        = action_uses[0]
                    executed = on_action(u["name"], u["input"])
                    return AgentResult(
                        reasoning=reasoning,
                        tool_called=u["name"],
                        executed=executed,
                        context=context,
                    )

                if query_rounds >= _MAX_QUERY_ROUNDS:
                    log.warning(f"[{process}] Limite de {_MAX_QUERY_ROUNDS} rodadas de consulta atingido — encerrando sem acao")
                    return AgentResult(reasoning=reasoning, tool_called=None)

                msgs.append({"role": "assistant", "content": output_msg["content"]})

                tool_results = []
                for u in query_uses:
                    result = _dispatch_query(u["name"], u["input"])
                    tool_results.append({
                        "type":      "toolResult",
                        "toolUseId": u["toolUseId"],
                        "content":   json.dumps(result, ensure_ascii=False),
                    })

                msgs.append({"role": "user", "content": tool_results})
                query_rounds += 1

        except Exception as e:
            if attempt < 3:
                log.warning(f"[{process}] Tentativa {attempt} falhou: {sanitize(str(e))} — retentando")
            else:
                log.error(f"[{process}] Erro apos 3 tentativas: {sanitize(str(e))}")

    return AgentResult(reasoning="", tool_called=None)
