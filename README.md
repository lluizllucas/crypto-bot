# Crypto Trading Bot — OpenRouter + Binance Testnet

Stack 100% gratuito. Funciona no Brasil. Sem dados fiscais. Sem dinheiro real.

## Visao geral

Bot de trading de criptomoedas que usa um LLM (via OpenRouter) como estrategista
para analisar dados de mercado e tomar decisoes de BUY / SELL / HOLD. Roda 24/7
em VPS na nuvem com gestao de risco automatica.

**Backtest validado:** 365 dias de dados reais (mar/2025 a mar/2026)
- Par: BTCUSDT (ETH e BNB removidos por desempenho inconsistente no backtest)
- PnL: +$4.03 com capital simulado de $500
- Drawdown maximo: -3.51%
- Win rate: 36.9% com ganho medio > perda media

## Pre-requisitos

- Python 3.10+
- Conta no OpenRouter (gratis, sem cartao)
- Conta GitHub (para Binance Testnet)

## Instalacao

```bash
git clone <seu-repositorio>
cd trading-bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Configuracao

### 1. OpenRouter API Key (gratis, sem cartao)
- Acesse https://openrouter.ai
- Crie conta com Google ou GitHub
- Va em https://openrouter.ai/settings/keys -> "Create Key"
- Cole em `OPENROUTER_API_KEY` no `config.py`

### 2. Binance Testnet (gratis, sem cadastro fiscal)
- Acesse https://testnet.binance.vision
- Clique em "Log in with GitHub"
- Va em API Keys -> Generate HMAC_SHA256 Key
- Cole em `BINANCE_API_KEY` e `BINANCE_SECRET_KEY` no `config.py`

> Saldo inicial no testnet: ~15.000 USDT virtual.
> Se acabar, clique em "Faucet" no dashboard para repor.

## Uso local

```bash
source venv/bin/activate
python3 bot.py
```

## Deploy em VPS (Linux)

1. Instalar dependencias do sistema:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv -y
```

2. Criar ambiente virtual e instalar pacotes:
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

3. Configurar servico systemd para rodar 24/7:
```bash
sudo nano /etc/systemd/system/trading-bot.service
```

Conteudo do arquivo:
```ini
[Unit]
Description=Crypto Trading Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/trading-bot
ExecStart=/home/ubuntu/trading-bot/venv/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

4. Ativar e iniciar:
```bash
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
```

> Nota: a VPS deve estar na regiao de Sao Paulo (sa-east-1) na AWS.
> IPs de datacenters americanos sao bloqueados pela Binance Testnet.

## Monitoramento

Ver logs em tempo real:
```bash
sudo journalctl -fu trading-bot
# ou
tail -f ~/trading-bot/bot.log
```

Ver apenas erros:
```bash
tail -f ~/trading-bot/bot.error.log
```

Status do servico:
```bash
sudo systemctl status trading-bot
```

Reiniciar apos mudanca de configuracao:
```bash
sudo systemctl restart trading-bot
```

## Arquitetura

```
config.py          <- chaves de API e parametros de risco
bot.py             <- orquestrador principal
  |
  +-- run_cycle()          <- ciclo de analise LLM (a cada 60 min)
  |     +-- get_market_data()    <- busca velas e ticker na Binance
  |     +-- analyze_with_llm()  <- BUY / SELL / HOLD via OpenRouter
  |     +-- execute_trade()      <- executa ordem na Binance Testnet
  |
  +-- monitor_positions()  <- ciclo rapido de SL/TP (a cada 5 min)
  |     +-- get_current_price()  <- preco atual sem chamar LLM
  |     +-- check_stop_take()   <- verifica SL/TP
  |     +-- close_position()    <- fecha posicao se necessario
  |
  +-- log_daily_summary()  <- resumo automatico a meia-noite

backtest.py        <- simulacao historica de 365 dias
```

## Gestao de risco

| Parametro         | Valor   | Descricao                              |
|-------------------|---------|----------------------------------------|
| STOP_LOSS_PCT     | 2.5%    | Fecha posicao se cair 2.5% da entrada  |
| TAKE_PROFIT_PCT   | 5.0%    | Fecha posicao se subir 5.0% da entrada |
| MAX_DAILY_LOSS    | $20     | Para novas compras se perder $20/dia   |
| TRADE_USDT        | $50     | Valor maximo por operacao              |
| MIN_CONFIDENCE    | 65%     | Confianca minima do LLM para operar    |

## Logs

O bot gera dois arquivos de log com rotacao diaria (retencao infinita):

- `bot.log` — log completo (INFO+). Rotaciona a meia-noite: `bot.log.2026-03-20`
- `bot.error.log` — apenas WARNING e ERROR para diagnostico rapido

Todo dia a meia-noite e gerado um resumo automatico no log:
```
=======================================================
RESUMO DIARIO
  Saldo USDT atual:   $83956.54
  Operacoes hoje:     3
  Win rate:           66.7% (2W/1L)
  PnL da sessao:      +$4.2100
  Perda acumulada:    $1.58 / $20.00
  Posicoes abertas:   0
=======================================================
```

## Limites gratuitos

| Servico           | Limite                        |
|-------------------|-------------------------------|
| OpenRouter free   | 20 req/min, 200 req/dia       |
| Binance Testnet   | Ilimitado                     |

1 simbolo x ciclo de 60 min = ~24 req/dia -- dentro do limite.
