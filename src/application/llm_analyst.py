"""
Analise de mercado via LLM (OpenRouter).
Recebe um MarketData completo, envia contexto JSON estruturado e retorna um TradeSignal.
"""

import json
import time
import logging

from openai import OpenAI

from src.config import OPENROUTER_API_KEY, MIN_CONFIDENCE

from src.domain.models import MarketData, TradeSignal

log = logging.getLogger(__name__)

_llm = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

_VALID_ACTIONS = ("BUY", "SELL", "HOLD", "RANGE_MODE", "TREND_MODE")


def _sanitize(text: str) -> str:
    """Substitui caracteres tipograficos que o Windows cp1252 nao suporta."""
    replacements = {
        "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2026": "...", "\u00b7": ".",
    }

    for char, rep in replacements.items():
        text = text.replace(char, rep)

    return text


def build_context(data: MarketData, open_positions: dict | None = None) -> dict:
    """
    Monta o contexto JSON estruturado para envio a LLM.
    open_positions: { "BTCUSDT": [Position, ...] } -- estado atual do banco
    """
    if data.ema20 > data.ema50 > data.ema200:
        ema_trend = "bullish"
    elif data.ema20 < data.ema50 < data.ema200:
        ema_trend = "bearish"
    else:
        ema_trend = "neutral"

    # Posicoes abertas do simbolo atual para contexto da LLM
    positions_ctx = []
    if open_positions:
        for pos in open_positions.get(data.symbol, []):
            pnl_pct = (data.price - pos.entry_price) / pos.entry_price * 100
            positions_ctx.append({
                "entry_price": pos.entry_price,
                "qty":         pos.qty,
                "sl":          pos.sl,
                "tp":          pos.tp,
                "pnl_pct":     round(pnl_pct, 2),
            })

    return {
        "symbol":             data.symbol,
        "price":              data.price,
        "rsi_1h":             data.rsi_1h,
        "ema20":              data.ema20,
        "ema50":              data.ema50,
        "ema200":             data.ema200,
        "ema_trend":          ema_trend,
        "atr":                data.atr,
        "bb_upper":           data.bb_upper,
        "bb_lower":           data.bb_lower,
        "range_position_24h": data.range_position_24h,
        "range_position_7d":  data.range_position_7d,
        "range_high_24h":     data.range_high_24h,
        "range_low_24h":      data.range_low_24h,
        "range_high_7d":      data.range_high_7d,
        "range_low_7d":       data.range_low_7d,
        "range_high_30d":     data.range_high_30d,
        "range_low_30d":      data.range_low_30d,
        "fear_greed":         data.fear_greed,
        "volume_24h":         data.volume_24h,
        "avg_volume_5h":      data.avg_volume_5h,
        "open_positions":     positions_ctx,
    }


_PROMPT_TEMPLATE = """\
Voce e um analista quantitativo especializado em Bitcoin.

Contexto de mercado atual:
{context}

Com base nos dados acima, responda SOMENTE com um JSON valido, sem texto adicional, \
sem markdown, sem blocos de codigo.

Formato obrigatorio:
{{
  "action": "BUY" | "SELL" | "HOLD" | "RANGE_MODE" | "TREND_MODE",
  "confidence": <numero entre 0.0 e 1.0>,
  "sl_percentage": <stop-loss recomendado em %>,
  "tp_percentage": <take-profit recomendado em %>,
  "reason": "<explicacao objetiva em ate 2 frases>"
}}

Definicao das acoes:
- BUY:        entrada de compra -- RSI baixo, preco proximo ao suporte, volume confirmando
- SELL:       saida / venda -- RSI alto, preco proximo a resistencia, pressao vendedora
- HOLD:       sinal ambiguo, confianca abaixo de {min_confidence} ou sem setup claro
- RANGE_MODE: mercado lateralizado -- operar apenas nas extremidades do range (BB / suporte-resistencia)
- TREND_MODE: tendencia forte identificada (EMA alinhadas) -- seguir a tendencia, evitar contratendencia

Regras de risco:
- sl_percentage: use o ATR como referencia (ATR / preco * 100). Minimo 1.0%, maximo 5.0%
- tp_percentage: relacao risco/retorno minima de 1:2 em relacao ao sl_percentage
- Em caso de duvida, prefira HOLD\
"""


def analyze(data: MarketData, open_positions: dict | None = None) -> TradeSignal:
    """Envia contexto ao OpenRouter e retorna TradeSignal com action, SL e TP dinamicos."""
    context = build_context(data, open_positions)

    prompt = _PROMPT_TEMPLATE.format(
        context=json.dumps(context, indent=2),
        min_confidence=MIN_CONFIDENCE,
    )

    for attempt in range(1, 4):
        try:
            response = _llm.chat.completions.create(
                model="openrouter/free",
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.choices[0].message.content.strip()

            if "```" in text:
                text = text.split("```")[1]

                if text.startswith("json"):
                    text = text[4:]

            result = json.loads(text.strip())

            assert result.get("action") in _VALID_ACTIONS

            assert 0.0 <= float(result.get("confidence", 0)) <= 1.0
            assert 0.0 < float(result.get("sl_percentage", 0)) <= 10.0
            assert 0.0 < float(result.get("tp_percentage", 0)) <= 20.0

            return TradeSignal(
                action=result["action"],
                confidence=float(result["confidence"]),
                sl_percentage=float(result["sl_percentage"]),
                tp_percentage=float(result["tp_percentage"]),
                reason=_sanitize(result.get("reason", "")),
            )
        except Exception as e:
            wait = attempt * 15

            if attempt < 3:
                log.warning(
                    f"Tentativa {attempt} falhou para {data.symbol}: "
                    f"{_sanitize(str(e))} -- aguardando {wait}s"
                )
                time.sleep(wait)
            else:
                log.error(
                    f"Erro na analise LLM para {data.symbol} "
                    f"apos 3 tentativas: {_sanitize(str(e))}"
                )

    return TradeSignal(
        action="HOLD",
        confidence=0.0,
        sl_percentage=2.5,
        tp_percentage=5.0,
        reason="Erro na analise.",
    )
