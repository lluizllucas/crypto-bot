"""
Agente de Take-Profit: decide hold ou sell quando o TP e atingido.
"""

from src.config import TP_HOLD_MIN_CONFIDENCE

from src.domain.entities.position import Position
from src.domain.value_objects.market_data import MarketData

from src.infra.agents.agent_core import AgentResult, build_context, run_agent
from src.infra.agents.schemas.tool_schemas import TOOLS_TP
from src.infra.agents.tools.execution.execute_sell import tool_execute_sell
from src.infra.agents.tools.execution.execute_hold import tool_hold_position

_ACTION_NAMES = {t["function"]["name"] for t in TOOLS_TP}


def _get_prompt() -> str:
    conf = TP_HOLD_MIN_CONFIDENCE
    return """\
Voce e um gestor de posicoes lucrativas especializado em Bitcoin.
Uma posicao atingiu o Take-Profit. Sua unica tarefa e decidir: realizar o lucro agora ou segurar buscando mais.

━━━ CONTEXTO DISPONIVEL ━━━
- "triggered_position": posicao que atingiu o TP (entry_price, tp, sl, pnl_pct, tp_hold_count, hours_open)
- "indicators": RSI, EMA, MACD, ATR, Bollinger Bands — estado atual do mercado
- "market_regime": ADX, DI+/DI-, regime (trending/ranging)
- "llm_memory": suas ultimas 5 decisoes neste par — evite repetir erros de hold sem fundamento
- "recent_performance": contexto historico de win_rate e PnL

Voce tambem pode usar tools de consulta antes de decidir:
get_candles (4h para tendencia maior), get_rsi_history, get_volume_profile, get_volatility_history.

━━━ CRITERIOS PARA HOLD (hold_position) ━━━
Segure apenas se TODOS os seguintes estiverem presentes:
  1. ADX >= 25 com DI+ dominante (tendencia forte ainda ativa)
  2. RSI entre 55-70 sem divergencia bearish (momentum preservado, nao sobrecomprado)
  3. MACD histogram positivo e crescendo ou estavel
  4. Volume acima da media nos ultimos candles (compradores ativos)
  5. Preco acima das EMAs 20 e 50 sem perda de suporte

Requisitos de confianca por tentativa de hold:
  - 1a vez (tp_hold_count = 0): confianca minima {conf_1}
  - 2a vez (tp_hold_count = 1): confianca minima {conf_2}
  - 3a vez em diante:           confianca minima {conf_3}

Ao segurar, o SL sobe automaticamente (1a vez: break-even; 2a+: TP anterior). O TP e extendido 1.5x.

━━━ CRITERIOS PARA VENDER (sell_position) ━━━
Venda imediatamente se qualquer um dos seguintes:
  - RSI > 72 ou com divergencia bearish no topo
  - MACD histogram virando negativo
  - Volume de venda crescendo nos ultimos candles
  - ADX < 20 (mercado ranging, sem forca direcional)
  - tp_hold_count >= 2 sem convicção clara de continuacao
  - llm_memory mostra holds anteriores que nao performaram

━━━ REGRA DE OURO ━━━
Lucro realizado e lucro garantido. Em caso de duvida, venda.
Hold requer evidencia forte — nao apenas esperanca de alta.

OBRIGATORIO: Escreva um paragrafo explicando a leitura tecnica atual e a decisao tomada. Sem analise textual a resposta e invalida.
""".format(
        conf_1=conf[0],
        conf_2=conf[1] if len(conf) > 1 else conf[0],
        conf_3=conf[2] if len(conf) > 2 else conf[-1],
    )


def run_tp_agent(
    data: MarketData,
    pos:  Position,
) -> AgentResult:
    """Decide hold ou sell quando o TP e atingido."""
    context = build_context(data, [pos])
    context["trigger_type"]       = "TP"
    context["triggered_position"] = pos.db_id

    symbol = data.symbol

    def on_action(name: str, args: dict) -> bool:
        if args.get("position_id") != pos.db_id:
            return False

        confidence = float(args.get("confidence", 0))

        if name == "sell_position":
            return tool_execute_sell(symbol, pos.db_id, confidence, "TAKE-PROFIT", data.price)

        if name == "hold_position":
            return tool_hold_position(symbol, pos.db_id, confidence, data.price)

        return False

    return run_agent(
        system=       _get_prompt(),
        context=      context,
        action_tools= TOOLS_TP,
        action_names= _ACTION_NAMES,
        process=      "tp",
        on_action=    on_action,
    )
