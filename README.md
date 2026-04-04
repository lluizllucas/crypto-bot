# Crypto Trading Bot — OpenRouter + Binance Testnet

Bot de trading de criptomoedas que usa LLM (via OpenRouter) como estrategista
para analisar dados de mercado e tomar decisoes de BUY / SELL / HOLD.
Roda 24/7 em VPS na nuvem com gestao de risco automatica e notificacoes no Discord.

**Backtest validado:** 365 dias de dados reais (mar/2025 a mar/2026)
- Par: BTCUSDT | Capital inicial: $500
- Saldo final com bot: $503.86 (+0.77%)
- Saldo final Buy and Hold: $427.90 (-14.42%)
- Drawdown maximo: -3.51% | Win rate: 36.9%

## Requisitos

- Docker (recomendado)
- ou Python 3.10+

## Configuracao

1. Clone o repositorio:
```bash
git clone https://github.com/lluizllucas/crypto-bot
cd crypto-bot
```

2. Crie o arquivo de configuracao a partir do exemplo:
```bash
cp config.example.py config.py
```

3. Edite o `config.py` com suas chaves:

| Chave | Onde obter |
|---|---|
| OPENROUTER_API_KEY | https://openrouter.ai/settings/keys |
| BINANCE_API_KEY | https://testnet.binance.vision |
| BINANCE_SECRET_KEY | https://testnet.binance.vision |
| DISCORD_WEBHOOK_URL | Canal Discord → Integrações → Webhooks |

## Uso com Docker (recomendado)
```bash
docker build -t crypto-bot .
docker run -d --name trading-bot crypto-bot
```

Ver logs em tempo real:
```bash
docker logs -f trading-bot
```

Parar o bot:
```bash
docker stop trading-bot
```

## Uso sem Docker
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 bot.py
```

## Deploy em VPS (Linux)
```bash
sudo systemctl start trading-bot
sudo systemctl status trading-bot
sudo journalctl -fu trading-bot
```

> A VPS deve estar na regiao de Sao Paulo (sa-east-1) na AWS.
> IPs americanos sao bloqueados pela Binance Testnet.

## Arquitetura
```
bot.py
  ├── run_cycle()          ← analise LLM a cada 60 min
  ├── monitor_positions()  ← verifica SL/TP a cada 5 min
  └── log_daily_summary()  ← resumo automatico a meia-noite

backtest.py      ← simulacao historica de 365 dias
analyze_logs.py  ← relatorio de performance dos logs reais
```

## Gestao de risco

| Parametro | Valor | Descricao |
|---|---|---|
| STOP_LOSS_PCT | 2.5% | Fecha se cair 2.5% da entrada |
| TAKE_PROFIT_PCT | 5.0% | Fecha se subir 5.0% da entrada |
| MAX_DAILY_LOSS | $20 | Para compras se perder $20/dia |
| TRADE_USDT | $50 | Valor maximo por operacao |
| MIN_CONFIDENCE | 65% | Confianca minima do LLM |

## Backtest
```bash
python3 backtest.py
```

## Analise de logs
```bash
python3 analyze_logs.py          # log de hoje
python3 analyze_logs.py --all    # historico completo
```