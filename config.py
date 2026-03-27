import os

# config.py

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY",  "")

# 2. Binance TESTNET (sem dinheiro real)

BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY",     "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY",  "")

# Pares a monitorar
# BNB e ETH removidos apos backtest de 365 dias
SYMBOLS = ["BTCUSDT"]

# Valor em USDT por operacao de compra (fixo; sem % do capital)
TRADE_USDT = 50.0

# Multi-posicao por par: no maximo N lotes abertos; novas entradas exigem distancia minima
MAX_POSITIONS_PER_SYMBOL = 3
MIN_ENTRY_DISTANCE_PCT = 0.5

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
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Limite de perda total no dia em USDT
MAX_DAILY_LOSS_USDT = 20.0
