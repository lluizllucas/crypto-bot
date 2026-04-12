# Crypto Trading Bot — OpenRouter + Binance + AWS Fargate

Bot de trading de criptomoedas que usa LLM (via OpenRouter) como estrategista
para analisar dados de mercado e tomar decisoes de BUY / SELL / HOLD / RANGE_MODE / TREND_MODE.
Execucao serverless na AWS (ECS Fargate + EventBridge), sem servidor ligado 24/7.
Persistencia no Supabase e notificacoes no Discord.

**Backtest validado:** 365 dias de dados reais (mar/2025 a mar/2026)
- Par: BTCUSDT | Capital inicial: $500
- Saldo final com bot: $503.86 (+0.77%)
- Saldo final Buy and Hold: $427.90 (-14.42%)
- Drawdown maximo: -3.51% | Win rate: 36.9%

---

## Arquitetura

```
EventBridge (a cada 5 min)
  → ECS Fargate: src/check_sl_tp.py
      → Supabase (le posicoes abertas)
      → Binance Testnet (preco atual)
      → Fecha posicao se SL ou TP atingido
      → Supabase (atualiza trades)
      → Discord (notificacao)

EventBridge (a cada 15 min)
  → ECS Fargate: src/analysis_llm.py
      → Binance Mainnet (200 candles 1h)
      → Indicadores: EMA 20/50/200, RSI, ATR, Bollinger Bands
      → Range engine: 24h / 7d / 30d
      → Fear & Greed Index (alternative.me)
      → Supabase (posicoes abertas para contexto)
      → LLM OpenRouter (TradeSignal com SL/TP dinamicos)
      → Binance Testnet (executa ordem se BUY/SELL)
      → Supabase (persiste trade + llm_log)
      → Discord (notificacao)
```

---

## Stack

| Componente | Tecnologia |
|---|---|
| LLM estrategista | OpenRouter (modelo free) |
| Exchange dados | Binance Mainnet (publica, sem auth) |
| Exchange ordens | Binance Testnet (simulado) |
| Par operado | BTCUSDT |
| Persistencia | Supabase (PostgreSQL) |
| Notificacoes | Discord webhook |
| Infraestrutura | AWS ECS Fargate + EventBridge |
| Imagem Docker | Amazon ECR (sa-east-1) |
| CI/CD | GitHub Actions (build + push ECR) |

---

## Estrutura do projeto

```
src/
  analysis_llm.py             <- execucao efemera: analise LLM + ordem (15 min)
  check_sl_tp.py              <- execucao efemera: monitor SL/TP (5 min)
  bot.py                      <- modo continuo legado (nao usado em producao)
  config.py                   <- parametros (chaves via variavel de ambiente)
  resumo.py                   <- resumo diario Discord (opcional via cron)
  test_context.py             <- testa coleta de dados sem chamar LLM

  domain/
    models.py                 <- dataclasses: Position, MarketData, TradeSignal, SessionStats

  application/
    market_data.py            <- 200 candles + indicadores + range engine + Fear & Greed
    indicators.py             <- EMA, RSI, ATR, Bollinger Bands, SMA
    fear_greed.py             <- Fear & Greed Index (alternative.me)
    llm_analyst.py            <- prompt + analise OpenRouter + TradeSignal
    signal_generator.py       <- sinais tecnicos puros (usado pelo backtest)
    risk_manager.py           <- posicoes, SL/TP dinamicos, limite diario, ordens
    notifier.py               <- notificacoes Discord

  infra/
    binance/client.py         <- market_client (mainnet) + trade_client (testnet)
    supabase/client.py        <- conexao Supabase
    supabase/repository.py    <- open_positions, trades, llm_logs
    logging/setup.py          <- console + arquivo (fallback gracioso no Fargate)

scripts/
  build_and_push.sh           <- build Docker + push para ECR

infra/                        <- (futuro) Terraform
```

---

## Configuracao local

### 1. Clone o repositorio

```bash
git clone https://github.com/lluizllucas/crypto-bot
cd crypto-bot
```

### 2. Crie o `.env`

```bash
cp .env.example .env
```

| Variavel | Onde obter |
|---|---|
| `OPENROUTER_API_KEY` | https://openrouter.ai/settings/keys |
| `BINANCE_API_KEY` | https://www.binance.com → API Management |
| `BINANCE_SECRET_KEY` | https://www.binance.com → API Management |
| `BINANCE_TESTNET_API_KEY` | https://testnet.binance.vision (expira em 30 dias) |
| `BINANCE_TESTNET_SECRET_KEY` | https://testnet.binance.vision |
| `DISCORD_WEBHOOK_URL` | Discord → canal → Integracoes → Webhooks |
| `SUPABASE_URL` | Supabase → Project Settings → API → Project URL |
| `SUPABASE_KEY` | Supabase → Project Settings → API → anon public |
| `SUPABASE_SERVICE_KEY` | Supabase → Project Settings → API → service_role |

### 3. Crie as tabelas no Supabase

No SQL Editor do painel Supabase:

```sql
create table llm_logs (
  id         uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  symbol     text not null,
  context    jsonb,
  response   jsonb
);

create table trades (
  id           uuid primary key default gen_random_uuid(),
  created_at   timestamptz default now(),
  symbol       text not null,
  action       text not null,
  confidence   numeric,
  entry_price  numeric,
  exit_price   numeric,
  qty          numeric,
  sl           numeric,
  tp           numeric,
  pnl          numeric,
  reason       text,
  llm_log_id   uuid references llm_logs(id)
);

create table open_positions (
  id           uuid primary key default gen_random_uuid(),
  created_at   timestamptz default now(),
  symbol       text not null,
  entry_price  numeric not null,
  qty          numeric not null,
  sl           numeric not null,
  tp           numeric not null
);
```

---

## Testar localmente

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Testa coleta de dados sem chamar a LLM
python3 -m src.test_context

# Roda o ciclo LLM uma vez
python3 src/analysis_llm.py

# Roda o monitor SL/TP uma vez
python3 src/check_sl_tp.py
```

---

## Deploy (AWS Fargate)

### Pre-requisitos AWS
- ECR repository: `trading-bot-repo` (regiao `sa-east-1`)
- ECS Cluster: `TradingBotCluster` (Fargate)
- Task Definition: `TradingBotTask` com todas as variaveis de ambiente
- Duas regras no EventBridge (ver abaixo)

### Build e push manual

```bash
AWS_REGION=sa-east-1 \
AWS_ACCOUNT_ID=SEU_ACCOUNT_ID \
ECR_REPOSITORY=trading-bot-repo \
IMAGE_TAG=latest \
./scripts/build_and_push.sh
```

### CI/CD automatico

Push na branch `main` dispara o GitHub Actions que faz build e push para o ECR automaticamente.

Secrets necessarios no GitHub (Settings → Secrets → Actions):

| Secret | Descricao |
|---|---|
| `AWS_ACCESS_KEY_ID` | IAM user com permissao ECR |
| `AWS_SECRET_ACCESS_KEY` | IAM user com permissao ECR |

### EventBridge — schedules

| Regra | Frequencia | Script |
|---|---|---|
| `Run-SL-TP-5min` | a cada 5 min | `src/check_sl_tp.py` |
| `Run-LLM-15min` | a cada 15 min | `src/analysis_llm.py` |

Container override (JSON) — campo **Input transformer** no EventBridge:
```json
{
  "containerOverrides": [
    {
      "name": "bot-container",
      "command": ["src/check_sl_tp.py"]
    }
  ]
}
```

---

## Monitoramento

Logs disponiveis no **AWS CloudWatch**:
- `/ecs/TradingBotTask` — todas as execucoes

Para acompanhar pelo terminal:

```bash
aws logs tail /ecs/TradingBotTask --follow --region sa-east-1
```

---

## Gestao de risco

| Parametro | Valor | Descricao |
|---|---|---|
| `STOP_LOSS_PCT` | dinamico | Definido pela LLM com base no ATR (min 1%, max 5%) |
| `TAKE_PROFIT_PCT` | dinamico | Definido pela LLM com RR minimo de 1:2 |
| `MAX_DAILY_LOSS` | $20 | Para novas compras se perder $20/dia |
| `TRADE_USDT` | $50 | Valor por operacao |
| `MAX_POSITIONS_PER_SYMBOL` | 3 | Maximo de lotes abertos por par |
| `MIN_ENTRY_DISTANCE_PCT` | 0.5% | Distancia minima entre entradas |
| `MIN_CONFIDENCE` | 65% | Confianca minima do LLM para executar |

---

## Acoes da LLM

| Acao | Descricao |
|---|---|
| `BUY` | Entrada de compra |
| `SELL` | Saida / venda |
| `HOLD` | Sinal ambiguo, sem execucao |
| `RANGE_MODE` | Mercado lateralizado identificado |
| `TREND_MODE` | Tendencia forte identificada |

---

## Backtest

```bash
python3 -m src.backtest
```

---

## Roadmap

### V1 — MVP serverless (atual)
- [x] Binance candles 1h (200 periodos)
- [x] EMA 20/50/200, RSI, ATR, Bollinger Bands
- [x] Range engine (24h / 7d / 30d)
- [x] Fear & Greed Index
- [x] SL/TP dinamicos via LLM (baseado no ATR)
- [x] Multi-posicao por par (max 3 lotes)
- [x] Persistencia no Supabase (open_positions, trades, llm_logs)
- [x] Execucao serverless (ECS Fargate + EventBridge)
- [x] CI/CD via GitHub Actions para ECR

### V2 — Observabilidade e contexto externo
- [ ] Duas Task Definitions separadas com log groups distintos no CloudWatch
- [ ] NewsAPI (noticias macro e crypto)
- [ ] Reddit sentiment (r/Bitcoin, r/CryptoCurrency)
- [ ] Dados macro: DXY, Nasdaq, juros FED (yfinance)

### V3 — Dados avancados e infraestrutura
- [ ] Dados on-chain (Glassnode, CryptoQuant)
- [ ] Open Interest e Funding Rate
- [ ] Multi-timeframe (5m + 1h + 4h + 1d)
- [ ] Dashboard de monitoramento
- [ ] Terraform para infraestrutura como codigo