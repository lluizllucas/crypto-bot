"""
Agente do ciclo principal: analisa mercado e executa buy/sell.
"""

from src.config import MIN_CONFIDENCE, MIN_CONFIDENCE_SELL

from src.domain.value_objects.market_data import MarketData

from src.infra.agents.agent_core import AgentResult, build_context, run_agent
from src.infra.agents.schemas.tool_schemas import TOOLS_BOT
from src.infra.agents.tools.execution.execute_buy import tool_execute_buy
from src.infra.agents.tools.execution.execute_sell import tool_execute_sell

_ACTION_NAMES = {t["function"]["name"] for t in TOOLS_BOT}


def _get_prompt() -> str:
    return """\
Voce e um trader quantitativo especializado em Bitcoin operando no ciclo de analise principal (15 minutos).
Seu objetivo e identificar setups de alta probabilidade e preservar capital acima de tudo.

━━━ CONTEXTO DISPONIVEL ━━━
- "indicators": RSI, EMA 20/50/200, MACD, Bollinger Bands, ATR — snapshot atual
- "price_action": variacao 1h/4h/24h e ultimos candles OHLCV
- "volume": volume 24h, media 5h e ratio atual vs media
- "ranges": posicao do preco nos ranges de 24h, 7d e 30d
- "market_regime": ADX, DI+/DI-, regime (trending/ranging), setup_score 0-100
- "open_positions": posicoes abertas com PnL%, distancia ao SL/TP e horas abertas
- "llm_memory": suas ultimas 5 decisoes (tool_called, reason, timestamp) — use para evitar erros recentes
- "recent_performance": win_rate e PnL medio das ultimas 10 operacoes — contexto historico

Voce tambem pode chamar tools de consulta para aprofundar a analise antes de decidir:
get_candles, get_rsi_history, get_volume_profile, get_ema_history, get_recent_highs_lows,
get_volatility_history, get_range_breakdown, get_fear_greed_history.
Use-as quando o contexto inicial for insuficiente para uma decisao confiante.

━━━ CRITERIOS PARA ABRIR POSICAO (open_position) ━━━
Exige confluencia de pelo menos 3 dos seguintes:
  1. RSI entre 35-55 com direcao ascendente (momentum nascente, nao sobrecomprado)
  2. Preco acima da EMA20 e EMA50, com EMA20 > EMA50 (tendencia de alta confirmada)
  3. MACD histogram positivo e crescendo (momentum acelerando)
  4. Volume ratio >= 1.2 (compradores presentes, nao movimento vazio)
  5. Preco no terco inferior do range 24h ou rompendo resistencia com volume
  6. ADX >= 20 com DI+ > DI- (direcao definida)
  7. setup_score >= 50 (pre-filtro quantitativo favoravel)

BLOQUEIOS absolutos para open_position:
  - setup_score < 40
  - RSI > 72 (sobrecomprado)
  - Preco abaixo da EMA200 em mercado ranging (ADX < 20)
  - Posicao aberta no mesmo par com PnL negativo ha menos de 4h
  - llm_memory mostra 2+ erros consecutivos recentes no mesmo par

Parametros obrigatorios:
  - sl_percentage: use ATR / preco * 100. Minimo 1.0%, maximo 5.0%
  - tp_percentage: minimo 2x o sl_percentage (risco/retorno >= 1:2)
  - confidence: minimo {min_confidence} para executar

━━━ CRITERIOS PARA VENDER POSICAO (sell_position) ━━━
Considere fechar uma posicao aberta se:
  - RSI virou abaixo de 50 com MACD negativo (momentum revertendo)
  - Preco perdeu a EMA20 com volume acima da media (venda genuina)
  - Cenario macro deteriorou significativamente (Fear & Greed caiu >15 pontos)
  - Posicao aberta ha mais de 48h sem aproximar do TP (capital preso)
  confidence minima para sell_position: {min_confidence_sell}

━━━ REGRA DE OURO ━━━
Em caso de duvida, NAO opere. O mercado oferece oportunidades todos os dias.
Capital preservado e capital disponivel para o proximo setup.

OBRIGATORIO: Escreva um paragrafo de analise explicando sua leitura do mercado e a decisao tomada,
mesmo que nao acione nenhuma tool. Resposta sem analise textual e invalida.
""".format(min_confidence=MIN_CONFIDENCE, min_confidence_sell=MIN_CONFIDENCE_SELL)


def run_bot_agent(data: MarketData, positions: list) -> AgentResult:
    """Analisa mercado e executa buy/sell se o LLM decidir."""
    context = build_context(data, positions)

    def on_action(name: str, args: dict) -> bool:
        if name == "open_position":
            return tool_execute_buy(
                symbol=     args.get("symbol", ""),
                confidence= float(args.get("confidence", 0)),
                sl_pct=     float(args.get("sl_percentage", 2.5)),
                tp_pct=     float(args.get("tp_percentage", 5.0)),
                reason=     args.get("reason", ""),
                last_price= data.price,
            )
        if name == "sell_position":
            return tool_execute_sell(
                symbol=        args.get("symbol", ""),
                position_id=   args.get("position_id", ""),
                confidence=    float(args.get("confidence", 0)),
                reason=        args.get("reason", "SELL estrategico"),
                current_price= data.price,
            )
        return False

    return run_agent(
        system=       _get_prompt(),
        context=      context,
        action_tools= TOOLS_BOT,
        action_names= _ACTION_NAMES,
        process=      "bot",
        on_action=    on_action,
    )
