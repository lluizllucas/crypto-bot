# Crypto Trading Bot — AWS Bedrock + Binance + AWS Fargate

Bot de trading de criptomoedas com arquitetura de agentes LLM especializados.
Analisa dados de mercado via AWS Bedrock (Claude Haiku 4.5) e executa ordens simuladas
na Binance Testnet. Execucao serverless no AWS ECS Fargate via EventBridge, sem servidor
ligado 24/7. Persistencia no Supabase (PostgreSQL direto via psycopg2) e notificacoes no Discord.

**Par operado:** BTCUSDT | **Capital simulado:** $500 | **Exchange de ordens:** Binance Testnet

---

## Arquitetura

```
EventBridge (a cada 5 min)
  → ECS Fargate: python -m src.scripts.check_sl_tp
      → Binance Mainnet (preco atual)
      → Para cada posicao aberta:
          se preco <= SL → fecha automaticamente
          se preco >= TP → tp_agent (LLM decide: segurar com SL elevado ou fechar)
          se queda forte  → early_exit_agent (LLM decide saida antecipada)
      → PostgreSQL/Supabase (atualiza posicao/trade)
      → Discord (notificacao)

EventBridge (a cada 15 min)
  → ECS Fargate: python -m src.scripts.bot
      → Binance Mainnet (200 candles 1h)
      → Indicadores: EMA 20/50/200, RSI, MACD, ATR, Bollinger Bands, ADX
      → Range engine: 24h / 7d / 30d + Fear & Greed Index
      → PostgreSQL/Supabase (posicoes abertas + historico LLM)
      → bot_agent (LLM decide: open_position / sell_position / hold)
      → Binance Testnet (executa ordem se decidir abrir/fechar)
      → PostgreSQL/Supabase (persiste trade + llm_log)
      → Discord (notificacao)
```

### Agentes LLM

| Agente | Quando roda | Responsabilidade |
|---|---|---|
| `bot_agent` | A cada 15 min | Analisa mercado, decide abrir ou fechar posicao |
| `tp_agent` | Quando preco >= TP | Decide segurar com SL elevado (trailing) ou fechar |
| `early_exit_agent` | Queda forte detectada | Decide saida antecipada antes do SL |

---

## Stack

| Componente | Tecnologia |
|---|---|
| LLM estrategista | AWS Bedrock — Claude Haiku 4.5 |
| Exchange dados | Binance Mainnet (publica, sem auth) |
| Exchange ordens | Binance Testnet (simulado) |
| Par operado | BTCUSDT |
| Persistencia | Supabase PostgreSQL (SQLAlchemy + psycopg2) |
| Notificacoes | Discord webhook |
| Infraestrutura | AWS ECS Fargate + EventBridge |
| Imagem Docker | Amazon ECR (sa-east-1) |
| CI/CD | GitHub Actions (build + push ECR no push para main) |

---

## Estrutura do projeto

```
src/
  config.py                        <- parametros operacionais e chaves via env vars
  scripts/
    bot.py                         <- entry point: ciclo de analise LLM (15 min)
    check_sl_tp.py                 <- entry point: monitor SL/TP (5 min)
    daily_summary.py               <- resumo diario Discord (opcional)
    weekly_pnl.py                  <- PnL semanal Discord (opcional)

  domain/
    entities/                      <- Position, Trade, LlmLog, DailyLoss
    value_objects/                 <- MarketData, TradeSignal
    services/                      <- regras de negocio puras (sem IO)

  application/
    use_cases/
      analyze_market.py            <- orquestra coleta + bot_agent + persistencia
      monitor_positions.py         <- orquestra monitoramento + agentes SL/TP
    services/
      market_data_service.py       <- 200 candles + indicadores + range + Fear&Greed
      indicators_service.py        <- EMA, RSI, MACD, ATR, Bollinger, ADX, setup_score
      risk_service.py              <- validacoes de risco pre-execucao
    ports/                         <- interfaces (abstrações) de LLM, mercado, notificador

  infra/
    agents/
      bot_agent.py                 <- prompt + loop bot_agent (open/sell)
      tp_agent.py                  <- prompt + loop tp_agent (hold/close TP)
      early_exit_agent.py          <- prompt + loop early_exit_agent
      agent_core.py                <- loop Bedrock compartilhado (query + action)
      providers/bedrock_provider.py <- cliente AWS Bedrock Converse API
      schemas/tool_schemas.py      <- definicoes JSON das tools disponibilizadas ao LLM
      tools/
        execution/                 <- execute_buy, execute_sell, execute_hold, execute_early_exit
        market/                    <- get_candles, get_market_data (query tools)
        portfolio/                 <- get_positions (query tool)
    clients/
      binance/client.py            <- market_client (mainnet) + trade_client (testnet)
      discord/client.py            <- notificacoes Discord
      fear_greed/client.py         <- Fear & Greed Index (alternative.me)
    persistence/
      database.py                  <- engine SQLAlchemy + session factory
      repository.py                <- fachada publica de persistencia
      repositories/                <- OpenPositions, Trades, LlmLogs, DailyLoss
      entities/                    <- modelos ORM (SQLAlchemy)
      mappers/                     <- conversao ORM <-> domain entities
    logging/setup.py               <- configuracao de logs (console + arquivo)
```

---

## Configuracao local

### 1. Clone o repositorio

```bash
git clone https://github.com/lluizllucas/crypto-bot
cd crypto-bot
```

### 2. Suba o banco com Docker Compose

```bash
docker compose up -d
```

### 3. Crie o `.env`

```bash
cp .env.example .env
```

| Variavel | Descricao | Onde obter |
|---|---|---|
| `ENV` | `development` ou `production` | — |
| `AWS_ACCESS_KEY_ID` | IAM user com permissao Bedrock | AWS Console → IAM |
| `AWS_SECRET_ACCESS_KEY` | IAM user com permissao Bedrock | AWS Console → IAM |
| `AWS_DEFAULT_REGION` | Regiao com acesso ao modelo | ex: `us-east-1` |
| `POSTGRES_HOST` | Host do banco | `localhost` (dev) / Session Pooler Supabase (prod) |
| `POSTGRES_PORT` | Porta | `5432` |
| `POSTGRES_DB` | Nome do banco | `cryptobot` (dev) / `postgres` (Supabase) |
| `POSTGRES_USER` | Usuario | `postgres` (dev) / usuario Supabase |
| `POSTGRES_PASSWORD` | Senha | definida no docker-compose (dev) / Supabase |
| `BINANCE_API_KEY` | Binance Mainnet (leitura de dados) | binance.com → API Management |
| `BINANCE_SECRET_KEY` | Binance Mainnet | binance.com → API Management |
| `BINANCE_TESTNET_API_KEY` | Binance Testnet (execucao de ordens) | testnet.binance.vision |
| `BINANCE_TESTNET_SECRET_KEY` | Binance Testnet | testnet.binance.vision |
| `DISCORD_WEBHOOK_URL` | Notificacoes | Discord → canal → Integracoes → Webhooks |

### 4. Rode localmente

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Ciclo de analise LLM (15 min)
python3 -m src.scripts.bot

# Monitor SL/TP (5 min)
python3 -m src.scripts.check_sl_tp
```

---

## Deploy (AWS Fargate)

### Pre-requisitos AWS

- ECR repository: `trading-bot-repo` (regiao `sa-east-1`)
- ECS Cluster: `TradingBotCluster` (Fargate)
- Task Definition: `TradingBotTask` com todas as variaveis de ambiente configuradas
- Duas regras no EventBridge (ver abaixo)

### CI/CD automatico

Push na branch `main` dispara o GitHub Actions que faz build e push para o ECR automaticamente.

Secrets necessarios no GitHub (Settings → Secrets → Actions):

| Secret | Descricao |
|---|---|
| `AWS_ACCESS_KEY_ID` | IAM user com permissao ECR |
| `AWS_SECRET_ACCESS_KEY` | IAM user com permissao ECR |

### EventBridge — container overrides

| Regra | Frequencia | Container override |
|---|---|---|
| `Run-LLM-15min` | a cada 15 min | `python -m src.scripts.bot` |
| `Run-SL-TP-5min` | a cada 5 min | `python -m src.scripts.check_sl_tp` |

Override JSON no EventBridge (campo **Input** da regra, aba **Targets**):

```json
{
  "containerOverrides": [
    {
      "name": "bot-container",
      "command": ["-m", "src.scripts.bot"]
    }
  ]
}
```

---

## Monitoramento

Logs disponíveis no **AWS CloudWatch**:

```bash
aws logs tail /ecs/TradingBotTask --follow --region sa-east-1
```

---

## Gestao de risco

| Parametro | Valor | Descricao |
|---|---|---|
| `STOP_LOSS_PCT` | 1.0% (default) | Calibrado pelo agente via ATR (min 1%, max 5%) |
| `TAKE_PROFIT_PCT` | 2.0% (default) | Calibrado pelo agente — RR minimo 1:2 obrigatorio |
| `MAX_DAILY_LOSS_USDT` | $20 | Bloqueia novas entradas se perda diaria atingir $20 |
| `TRADE_USDT` | $100 | Valor por posicao |
| `MAX_POSITIONS_PER_SYMBOL` | 3 | Maximo de lotes abertos por par |
| `MIN_ENTRY_DISTANCE_PCT` | 0.5% | Distancia minima entre entradas do mesmo par |
| `MIN_CONFIDENCE` | 75% | Confianca minima do LLM para abrir posicao |
| `MIN_CONFIDENCE_SELL` | 70% | Confianca minima do LLM para fechar posicao |

---

## Roadmap

### V1 — MVP serverless (atual)
- [x] Binance candles 1h (200 periodos)
- [x] EMA 20/50/200, RSI, MACD, ATR, Bollinger Bands, ADX, setup_score
- [x] Range engine (24h / 7d / 30d) + Fear & Greed Index
- [x] Agente LLM com tools de consulta e execucao (AWS Bedrock)
- [x] SL/TP dinamicos calibrados pelo agente via ATR
- [x] Multi-posicao por par (max 3 lotes)
- [x] tp_agent (trailing stop via LLM quando TP e atingido)
- [x] early_exit_agent (saida antecipada em quedas fortes)
- [x] Persistencia PostgreSQL via SQLAlchemy (Supabase em producao)
- [x] Execucao serverless (ECS Fargate + EventBridge)
- [x] CI/CD via GitHub Actions para ECR

### V2 — Observabilidade e contexto externo
- [ ] Task Definitions separadas com log groups distintos no CloudWatch
- [ ] NewsAPI (noticias macro e crypto)
- [ ] Reddit sentiment (r/Bitcoin, r/CryptoCurrency)
- [ ] Dados macro: DXY, Nasdaq, juros FED (yfinance)

### V3 — Dados avancados e infraestrutura
- [ ] Dados on-chain (Glassnode, CryptoQuant)
- [ ] Open Interest e Funding Rate
- [ ] Multi-timeframe (5m + 1h + 4h + 1d)
- [ ] Dashboard de monitoramento
- [ ] Terraform para infraestrutura como codigo
