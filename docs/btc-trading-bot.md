# Bot de Trading Automatizado com LLM para Bitcoin

## Visão Geral

Bot de compra e venda automática de Bitcoin capaz de:

- Operar em **range / lateralização**
- Operar em **tendência / hold**
- Identificar **mudança de regime do mercado**
- Usar uma **LLM como camada de decisão**
- Executar ordens automaticamente na exchange
- Aplicar **gestão de risco**

---

## Arquitetura Geral

```text
Market Data APIs
    ↓
Indicators + Range Analysis
    ↓
Sentiment + News + Macro
    ↓
Context Builder
    ↓
LLM Decision Engine
    ↓
Risk Engine
    ↓
Order Executor (Exchange API)
    ↓
Trade Logs + Monitoring
```

---

## Stack

- Python
- FastAPI
- Supabase
- APScheduler (cron / scheduler)
- Binance API
- OpenAI API / Claude API
- pandas
- ta
- yfinance

---

# V1 / MVP — Escopo Detalhado

O objetivo da V1 é validar se o bot consegue tomar boas decisões utilizando **somente dados quantitativos e sentimento consolidado**, sem depender ainda de notícias, redes sociais ou dados on-chain.

> **Recomendação:** utilizar a V1 em **paper trading por 2 a 4 semanas** antes de operar com capital real.

## Objetivos da V1

- Identificar se o BTC está em **range** ou **tendência**
- Identificar possíveis pontos de **compra**
- Identificar possíveis pontos de **venda**
- Decidir quando **não operar (HOLD)**
- Definir **SL e TP**
- Registrar todas as decisões para análise posterior

---

## Fluxo Completo da V1

```text
Scheduler (executa a cada 1 hora)
        ↓
Coleta de candles na Binance
        ↓
Cálculo dos indicadores
        ↓
Cálculo de ranges
        ↓
Coleta do Fear & Greed
        ↓
Montagem do contexto JSON
        ↓
Envio para LLM
        ↓
Recebimento da decisão
        ↓
Risk Engine
        ↓
Execução da ordem
        ↓
Persistência no banco
        ↓
Monitoramento da posição
```

---

# 1. Scheduler

Responsável por iniciar o fluxo periodicamente.

**Frequência recomendada para V1:** execução a cada **1 hora**, mantendo consistência com o timeframe `1h`.

```python
from apscheduler.schedulers.blocking import BlockingScheduler

scheduler = BlockingScheduler()
scheduler.add_job(run_trade_cycle, "interval", hours=1)
scheduler.start()
```

---

# 2. Coleta de Dados OHLCV

Base de todo o sistema.

## Campos necessários

- Open, High, Low, Close, Volume

## Timeframes recomendados

| Timeframe | Uso |
|-----------|-----|
| `5m` | Curto prazo |
| `1h` | **Principal (V1)** |
| `4h` | Médio prazo |
| `1d` | Longo prazo |

## API recomendada — Binance (gratuita)

**Endpoint:**
```text
GET https://api.binance.com/api/v3/klines
```

**Quantidade recomendada:** `200 candles` — permite cálculo confiável da EMA 200.

```python
import requests
import pandas as pd

def get_candles():
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "limit": 200
    }

    response = requests.get(url, params=params)
    data = response.json()

    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close",
        "volume", "close_time", "quote_asset_volume",
        "number_of_trades", "taker_buy_base",
        "taker_buy_quote", "ignore"
    ])

    return df
```

---

# 3. Indicadores Técnicos

## 3.1 RSI

Excelente para identificar sobrecompra e sobrevenda em range.

**Regras sugeridas:**
- `< 30` → região de compra
- `> 70` → região de venda

```python
import ta

rsi = ta.momentum.RSIIndicator(
    df["close"].astype(float)
).rsi().iloc[-1]
```

---

## 3.2 EMA 20 / 50 / 200

Identificação de tendência.

**Interpretação:**

| Sinal | Condição |
|-------|----------|
| Tendência de alta | `EMA20 > EMA50 > EMA200` |
| Tendência de baixa | `EMA20 < EMA50 < EMA200` |

```python
close_series = df["close"].astype(float)

ema20  = ta.trend.EMAIndicator(close_series, 20).ema_indicator().iloc[-1]
ema50  = ta.trend.EMAIndicator(close_series, 50).ema_indicator().iloc[-1]
ema200 = ta.trend.EMAIndicator(close_series, 200).ema_indicator().iloc[-1]
```

---

## 3.3 ATR

Utilizado para:
- Medir volatilidade
- Definir SL dinâmico
- Evitar operar em rompimentos fortes

```python
atr = ta.volatility.AverageTrueRange(
    df["high"].astype(float),
    df["low"].astype(float),
    df["close"].astype(float)
).average_true_range().iloc[-1]
```

---

## 3.4 Bollinger Bands

Perfeito para identificar lateralização.

```python
bb = ta.volatility.BollingerBands(df["close"].astype(float))

bb_high = bb.bollinger_hband().iloc[-1]
bb_low  = bb.bollinger_lband().iloc[-1]
```

---

# 4. Range Engine

Essencial para saber se o preço está próximo de suporte ou resistência.

## Curto prazo — Últimas 24h

```python
short_high = df["high"].tail(24).astype(float).max()
short_low  = df["low"].tail(24).astype(float).min()
```

## Médio prazo — Últimos 7 dias

```python
medium_high = df["high"].tail(24 * 7).astype(float).max()
medium_low  = df["low"].tail(24 * 7).astype(float).min()
```

## Longo prazo — Últimos 30 dias

```python
long_high = df["high"].tail(24 * 30).astype(float).max()
long_low  = df["low"].tail(24 * 30).astype(float).min()
```

## Posição dentro do range

```python
current_price = float(df["close"].iloc[-1])

range_position = (current_price - medium_low) / (medium_high - medium_low)
```

**Interpretação:**

| Range Position | Zona |
|----------------|------|
| `0.0 – 0.2` | Próximo ao suporte |
| `0.2 – 0.8` | Zona neutra |
| `0.8 – 1.0` | Próximo à resistência |

---

# 5. Sentimento do Mercado

## Fear & Greed Index

Extremamente importante. Disponível gratuitamente via Alternative.me.

```python
import requests

def get_fear_greed():
    url = "https://api.alternative.me/fng/"
    return requests.get(url).json()["data"][0]["value"]
```

**Interpretação:**

| Valor | Sentimento |
|-------|-----------|
| `0–25` | Medo extremo |
| `25–50` | Medo |
| `50–75` | Ganância |
| `75–100` | Ganância extrema |

---

# 6. Dados Macro (V2)

Dados macroeconômicos relevantes para o contexto:

- DXY
- Nasdaq
- Juros FED
- CPI / Inflação

```python
import yfinance as yf

dxy    = yf.download("DX-Y.NYB", period="5d")
nasdaq = yf.download("^IXIC", period="5d")
```

---

# 7. Notícias e Sentimento Social (V2)

## CoinMarketCap API

Plano gratuito com 10k créditos/mês. Pago a partir de 29 USD/mês.

## NewsAPI

Boa para macro. Free tier disponível.

```python
def get_news():
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": "bitcoin OR btc",
        "apiKey": "SUA_KEY"
    }
    return requests.get(url, params=params).json()
```

## Reddit — PRAW (gratuito)

Subreddits relevantes: `r/Bitcoin`, `r/CryptoCurrency`, `r/algotrading`

```python
import praw

reddit = praw.Reddit(
    client_id="ID",
    client_secret="SECRET",
    user_agent="btc-bot"
)

posts = reddit.subreddit("Bitcoin").hot(limit=10)
```

---

# 8. Montagem do Contexto para LLM

A LLM **nunca** deve receber texto solto — sempre JSON estruturado.

## Contexto V1 (mínimo)

```json
{
  "price": 68400,
  "rsi_1h": 28.5,
  "ema20": 68200,
  "ema50": 67900,
  "ema200": 66100,
  "atr": 1100,
  "range_position_24h": 0.18,
  "range_position_7d": 0.22,
  "fear_greed": 24
}
```

## Contexto V2 (completo)

```json
{
  "price": 68400,
  "rsi_1h": 32.4,
  "ema_trend": "bullish",
  "atr": 1200,
  "bb_high": 70000,
  "bb_low": 65000,
  "range_position_24h": 0.15,
  "range_position_7d": 0.20,
  "fear_greed": 28,
  "news_sentiment": "neutral",
  "reddit_sentiment": "bullish",
  "macro_bias": "risk_on"
}
```

---

# 9. Prompt da LLM

```text
Você é um analista quantitativo especializado em Bitcoin.

Com base no JSON enviado, responda SOMENTE em JSON.

Formato obrigatório:

{
  "action": "BUY | SELL | HOLD | RANGE_MODE | TREND_MODE",
  "confidence": 0-1,
  "sl_percentage": number,
  "tp_percentage": number,
  "reason": "string"
}
```

## Exemplo de resposta esperada

```json
{
  "action": "BUY",
  "confidence": 0.83,
  "sl_percentage": 1.8,
  "tp_percentage": 3.5,
  "reason": "RSI oversold near 7d support"
}
```

---

# 10. Risk Engine (Obrigatório)

Antes de executar qualquer ordem, validar:

## Confiança mínima

```python
if llm_response["confidence"] < 0.75:
    return  # ignora o trade
```

## Perda máxima diária

```python
if daily_loss_percentage >= 2:
    disable_bot()
```

## Posição já aberta

```python
if has_open_position():
    return
```

## Validações adicionais

- Exposição total
- SL compatível com ATR
- Rompimento de range

---

# 11. Execução da Ordem

```python
place_market_buy(
    symbol="BTCUSDT",
    amount_usdt=100
)
```

---

# 12. Persistência

Salvar no banco após cada ciclo:

**Tabela: `trades`**

| Campo | Descrição |
|-------|-----------|
| `id` | Identificador único |
| `created_at` | Timestamp da decisão |
| `action` | BUY / SELL / HOLD |
| `confidence` | Score da LLM |
| `sl` | Stop loss aplicado |
| `tp` | Take profit aplicado |
| `pnl` | Resultado da operação |
| `llm_context` | JSON enviado para a LLM |
| `llm_response` | Resposta completa da LLM |

---

# 13. Próximos Passos por Versão

## V1 — MVP (atual)

Foco em validação com dados quantitativos puros.

- [x] Binance candles (1h, 200 períodos)
- [x] RSI
- [x] EMA 20 / 50 / 200
- [x] ATR
- [x] Bollinger Bands
- [x] Range Engine (24h / 7d / 30d)
- [x] Fear & Greed Index
- [x] Contexto JSON estruturado
- [x] Prompt LLM com saída JSON
- [x] Risk Engine (confiança, perda diária, posição aberta)
- [x] Execução de ordem na Binance
- [x] Persistência no banco (Supabase)
- [x] Scheduler horário (APScheduler)

> **Critério de avanço para V2:** rodar em paper trade por 2–4 semanas com resultados estáveis.

---

## V2 — Contexto Externo

Enriquecer a decisão da LLM com fontes externas.

- [ ] Integrar NewsAPI (notícias macro e crypto)
- [ ] Integrar CoinMarketCap API
- [ ] Integrar Reddit via PRAW (`r/Bitcoin`, `r/CryptoCurrency`)
- [ ] Integrar yfinance para DXY, Nasdaq, juros FED
- [ ] Adicionar campo `news_sentiment` ao contexto JSON
- [ ] Adicionar campo `reddit_sentiment` ao contexto JSON
- [ ] Adicionar campo `macro_bias` ao contexto JSON
- [ ] Atualizar prompt da LLM para interpretar campos V2
- [ ] Logging e análise de impacto por fonte

> **Critério de avanço para V3:** demonstrar que o contexto externo melhora o accuracy das decisões em comparação com V1.

---

## V3 — Dados Avançados e Multi-exchange

Incorporar sinais de alta qualidade e expandir cobertura.

- [ ] Dados on-chain (ex: Glassnode, CryptoQuant)
  - SOPR, MVRV, Exchange Netflow
  - Whale movements (transfers > X BTC)
- [ ] Multi-exchange (Bybit, OKX, Kraken)
  - Agregação de order book
  - Open Interest e Funding Rate
- [ ] Twitter / X sentiment (API paga)
- [ ] Decisão multi-timeframe (5m + 1h + 4h + 1d)
- [ ] Engine de backtesting
  - Replay histórico com todas as fontes
  - Métricas: Sharpe ratio, max drawdown, win rate
- [ ] Dashboard de monitoramento em tempo real
- [ ] Alertas automáticos (Telegram / Discord)

---

## V4 — Otimização e Aprendizado

Sistema adaptativo e autônomo.

- [ ] Fine-tuning ou few-shot da LLM com trades históricos
- [ ] Avaliação automática de desempenho por regime de mercado
- [ ] Ajuste dinâmico de parâmetros de risk (confiança mínima, perda diária)
- [ ] A/B testing entre modelos de LLM (GPT-4o vs Claude vs local)
- [ ] Pipeline de retraining automatizado
- [ ] Detecção automática de regime (range vs tendência) sem depender da LLM
