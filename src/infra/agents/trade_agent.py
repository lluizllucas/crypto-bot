"""
Agente de trading via LLM (AWS Bedrock — Claude Haiku 4.5).

O agente e responsavel pelo ciclo completo:
  1. Monta contexto de mercado
  2. Chama o LLM em loop (agentic reasoning)
  3. Executa tools de consulta conforme o LLM pede
  4. Executa tools de acao (buy/sell/hold) quando o LLM decide
  5. Retorna AgentResult para o use-case apenas registrar o log

O use-case nao conhece nem actions nem tool dispatching.
"""

import json
import logging

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.domain.entities.position import Position
from src.domain.value_objects.market_data import MarketData

from src.infra.agents.schemas.tool_schemas import TOOLS_MONITOR, TOOLS_BOT, TOOLS_QUERY
from src.infra.agents.prompts.trade_prompt import get_monitor_system_prompt, get_bot_system_prompt
from src.infra.agents.providers.bedrock_provider import BedrockProvider, to_bedrock_tools, sanitize

from src.infra.persistence.repository import get_recent_llm_decisions, get_recent_performance

log = logging.getLogger("bot")

_provider = BedrockProvider()

_MAX_QUERY_ROUNDS = 10

_QUERY_NAMES = {t["function"]["name"] for t in TOOLS_QUERY}
_BOT_ACTION_NAMES   = {t["function"]["name"] for t in TOOLS_BOT}
_MONITOR_ACTION_NAMES = {t["function"]["name"] for t in TOOLS_MONITOR}


# ---------------------------------------------------------------------------
# Resultado do agente — unica coisa que sai do agent para o use-case
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    reasoning:   str
    tool_called: str | None
    executed:    bool = False
    context:     dict = field(default_factory=dict)


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
            pnl_pct      = (data.price - pos.entry_price) / pos.entry_price * 100
            dist_sl_pct  = (pos.entry_price - pos.sl) / pos.entry_price * 100
            dist_tp_pct  = (pos.tp - pos.entry_price) / pos.entry_price * 100
            hours_open   = (
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


# ---------------------------------------------------------------------------
# Dispatcher de tools de consulta
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Dispatcher de tools de acao do bot (open/sell)
# ---------------------------------------------------------------------------

def _dispatch_bot_action(name: str, args: dict, price: float, llm_log_id: str | None) -> bool:
    from src.infra.agents.tools.execution import tool_execute_buy, tool_execute_sell

    symbol     = args.get("symbol", "")
    confidence = float(args.get("confidence", 0))

    if name == "open_position":
        return tool_execute_buy(
            symbol=symbol,
            confidence=confidence,
            sl_pct=float(args.get("sl_percentage", 2.5)),
            tp_pct=float(args.get("tp_percentage", 5.0)),
            reason=args.get("reason", ""),
            last_price=price,
            llm_log_id=llm_log_id,
        )

    if name == "sell_position":
        return tool_execute_sell(
            symbol=symbol,
            position_id=args.get("position_id", ""),
            confidence=confidence,
            reason=args.get("reason", "SELL estrategico"),
            current_price=price,
            exit_llm_log_id=llm_log_id,
        )

    return False


# ---------------------------------------------------------------------------
# Dispatcher de tools de acao do monitor (sell/hold/early_exit)
# ---------------------------------------------------------------------------

def _dispatch_monitor_action(
    name: str,
    args: dict,
    pos: Position,
    price: float,
    llm_log_id: str | None,
    apply_tp_hold_fn,
    close_position_fn,
    tp_threshold: float,
    min_conf_early: float,
    trigger_type: str,
    process: str,
) -> bool:
    confidence = float(args.get("confidence", 0))

    if args.get("position_id") != pos.db_id:
        return False

    if trigger_type == "TP":
        if name == "sell_position":
            close_position_fn("TAKE-PROFIT", llm_log_id)
            return True
        
        if name == "hold_position":
            if confidence >= tp_threshold:
                log.info(f"[{process}] LLM segura no TP (conf {confidence:.2f} >= {tp_threshold:.2f}, tentativa #{pos.tp_hold_count + 1})")
                apply_tp_hold_fn()
            else:
                log.info(f"[{process}] LLM quer segurar mas confianca insuficiente ({confidence:.2f} < {tp_threshold:.2f}) — vendendo")
                close_position_fn("TAKE-PROFIT", llm_log_id)
            return True

    if trigger_type == "EARLY_EXIT" and name == "early_exit":
        if confidence >= min_conf_early:
            log.warning(f"[{process}] EARLY EXIT solicitado pelo LLM (conf {confidence:.2f}) @ ${price:.4f}")
            close_position_fn("EARLY-EXIT", llm_log_id)
        else:
            log.info(f"[{process}] LLM quer early exit mas confianca insuficiente ({confidence:.2f} < {min_conf_early:.2f}) — mantendo")
        return True

    return False


# ---------------------------------------------------------------------------
# Loop principal do agente
# ---------------------------------------------------------------------------

def _run_agent(
    system:       str,
    context:      dict,
    action_tools: list,
    action_names: set,
    process:      str,
    on_action,          # callable(name, args) -> bool
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

                tool_uses    = [b["toolUse"] for b in output_msg["content"] if "toolUse" in b]
                query_uses   = [u for u in tool_uses if u["name"] in _QUERY_NAMES]
                action_uses  = [u for u in tool_uses if u["name"] in action_names]

                # LLM decidiu uma acao — executa e encerra
                if action_uses:
                    u        = action_uses[0]
                    executed = on_action(u["name"], u["input"])
                    return AgentResult(
                        reasoning=reasoning,
                        tool_called=u["name"],
                        executed=executed,
                        context=context,
                    )

                # Apenas consultas
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


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

def run_bot_agent(data: MarketData, open_positions: dict) -> AgentResult:
    """
    Ciclo principal: analisa mercado e executa buy/sell se o LLM decidir.
    Retorna AgentResult para o use-case registrar o log.
    """
    context = build_context(data, open_positions)

    price   = data.price

    def on_action(name: str, args: dict) -> bool:
        return _dispatch_bot_action(name, args, price, llm_log_id=None)

    return _run_agent(
        system=get_bot_system_prompt(),
        context=context,
        action_tools=TOOLS_BOT,
        action_names=_BOT_ACTION_NAMES,
        process="bot",
        on_action=on_action,
    )


def run_monitor_agent(
    data:                MarketData,
    open_positions:      dict,
    triggered_positions: list[Position],
    trigger_type:        str,
    apply_tp_hold_fn,
    close_position_fn,
    tp_threshold:        float,
    min_conf_early:      float,
) -> AgentResult:
    """
    Monitor de SL/TP: decide hold/sell/early_exit e executa diretamente.
    Retorna AgentResult para o use-case registrar o log.
    """
    from src.config import MIN_CONFIDENCE_EARLY_EXIT

    context = build_context(data, open_positions)

    context["trigger_type"]        = trigger_type
    context["triggered_positions"] = [p.db_id for p in triggered_positions]

    pos = triggered_positions[0] if triggered_positions else None

    def on_action(name: str, args: dict) -> bool:
        if pos is None:
            return False
        
        return _dispatch_monitor_action(
            name=name,
            args=args,
            pos=pos,
            price=data.price,
            llm_log_id=None,
            apply_tp_hold_fn=apply_tp_hold_fn,
            close_position_fn=close_position_fn,
            tp_threshold=tp_threshold,
            min_conf_early=min_conf_early,
            trigger_type=trigger_type,
            process="monitor",
        )

    return _run_agent(
        system=get_monitor_system_prompt(),
        context=context,
        action_tools=TOOLS_MONITOR,
        action_names=_MONITOR_ACTION_NAMES,
        process="monitor",
        on_action=on_action,
    )
