"""
Agente de Early Exit: decide sair ou manter quando o preco se aproxima do SL.
"""

from src.config import MIN_CONFIDENCE_EARLY_EXIT

from src.domain.entities.position import Position
from src.domain.value_objects.market_data import MarketData

from src.infra.agents.agent_core import AgentResult, build_context, run_agent
from src.infra.agents.schemas.tool_schemas import TOOLS_EARLY_EXIT
from src.infra.agents.tools.execution.execute_early_exit import tool_early_exit

_ACTION_NAMES = {t["function"]["name"] for t in TOOLS_EARLY_EXIT}


def _get_prompt() -> str:
    return """\
Voce e um especialista em gestao de risco operando Bitcoin.
O preco atingiu 80% do caminho entre a entrada e o Stop-Loss. Sua unica tarefa e decidir: sair agora ou manter ate o SL.

━━━ CONTEXTO DISPONIVEL ━━━
- "triggered_position": posicao em risco (entry_price, sl, pnl_pct atual, dist_sl_pct, hours_open)
- "indicators": RSI, EMA, MACD, ATR, Bollinger Bands — estado atual
- "market_regime": ADX, DI+/DI-, regime (trending/ranging)
- "price_action": variacao recente e ultimos candles — leia o momentum de curto prazo
- "llm_memory": decisoes recentes neste par — evite padrao de saidas prematuras seguidas de recuperacao
- "recent_performance": historico de win_rate e PnL

Voce pode consultar tools antes de decidir:
get_candles (15m ou 1h para momentum recente), get_rsi_history, get_volume_profile, get_recent_highs_lows.

━━━ CRITERIOS PARA SAIDA ANTECIPADA (early_exit) ━━━
Saia apenas se houver confirmacao tecnica de continuacao da queda — pelo menos 2 dos seguintes:
  1. RSI < 35 e caindo (momentum negativo acelerando)
  2. MACD histogram negativo e aprofundando (vendedores no controle)
  3. Volume de venda acima da media nos ultimos 3 candles (pressao real)
  4. Preco abaixo da EMA20 com EMA20 virando para baixo (suporte perdido)
  5. Rompimento de suporte relevante identificado em get_recent_highs_lows
  6. DI- > DI+ com ADX crescendo (tendencia de baixa se firmando)

Confianca minima para acionar early_exit: {min_confidence}

━━━ CRITERIOS PARA MANTER (nao chamar nenhuma tool) ━━━
Mantenha a posicao se:
  - O recuo e dentro do range normal de volatilidade (ATR nao expandido)
  - RSI ainda acima de 40 sem divergencia clara
  - Volume de venda nao confirma a queda (movimento sem participacao)
  - Preco ainda acima de suporte tecnico relevante
  - llm_memory mostra saidas prematuras recentes que se recuperaram

━━━ REGRA DE OURO ━━━
O SL foi definido com criterio — ele existe para proteger capital sem intervencao emocional.
Saida antecipada so se justificada por evidencia tecnica clara, nao por desconforto com o PnL negativo.
Em caso de duvida, mantenha e deixe o SL trabalhar.

OBRIGATORIO: Escreva um paragrafo explicando a leitura do momentum atual e a decisao tomada. Sem analise textual a resposta e invalida.
""".format(min_confidence=MIN_CONFIDENCE_EARLY_EXIT)


def run_early_exit_agent(
    data:           MarketData,
    open_positions: dict,
    pos:            Position,
) -> AgentResult:
    """Decide sair antecipadamente ou manter quando o preco se aproxima do SL."""
    context = build_context(data, open_positions)
    
    context["trigger_type"]       = "EARLY_EXIT"
    context["triggered_position"] = pos.db_id

    symbol = data.symbol

    def on_action(name: str, args: dict) -> bool:
        if args.get("position_id") != pos.db_id:
            return False

        if name == "early_exit":
            return tool_early_exit(symbol, pos.db_id, float(args.get("confidence", 0)), data.price, None)

        return False

    return run_agent(
        system=       _get_prompt(),
        context=      context,
        action_tools= TOOLS_EARLY_EXIT,
        action_names= _ACTION_NAMES,
        process=      "early_exit",
        on_action=    on_action,
    )
