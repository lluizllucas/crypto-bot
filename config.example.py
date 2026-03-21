# config.py

OPENROUTER_API_KEY = "sua_chave_aqui"

# 2. Binance TESTNET (sem dinheiro real)

BINANCE_API_KEY    = "sua_chave_aqui"
BINANCE_SECRET_KEY = "sua_chave_aqui"

# Pares a monitorar
# BNB e ETH removidos apos backtest de 365 dias
SYMBOLS = ["BTCUSDT"]

# Valor em USDT por operacao de compra
TRADE_USDT = 50.0

# Confianca minima do LLM para executar uma ordem (0.0 a 1.0)
MIN_CONFIDENCE = 0.65

# Intervalo entre ciclos de analise LLM (em minutos)
INTERVAL_MINUTES = 60

# Intervalo do ciclo rapido de monitoramento SL/TP (em minutos)
MONITOR_INTERVAL_MINUTES = 5

# Stop-loss: fecha a posicao se cair X% desde a entrada
STOP_LOSS_PCT = 2.5

# Take-profit: fecha a posicao se subir X% desde a entrada
TAKE_PROFIT_PCT = 5.0

# Discord webhook para notificacoes
# Crie em: canal -> Integrações -> Webhooks -> Novo Webhook
DISCORD_WEBHOOK_URL = "sua_url_aqui"

# Limite de perda total no dia em USDT
MAX_DAILY_LOSS_USDT = 20.0
