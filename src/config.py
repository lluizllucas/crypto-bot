import os

####################################################
################### OPEN ROUTER ####################
####################################################

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Confianca minima do LLM para executar uma ordem (0.0 a 1.0)
MIN_CONFIDENCE = 0.65

####################################################
##################### BINANCE #####################
####################################################

# Testnet -- execucao de ordens simuladas (sem dinheiro real)
BINANCE_TESTNET_API_KEY    = os.getenv("BINANCE_TESTNET_API_KEY",    "")
BINANCE_TESTNET_SECRET_KEY = os.getenv("BINANCE_TESTNET_SECRET_KEY", "")

# Mainnet -- apenas para quando quiser operar com dinheiro real
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY",    "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")

# Pares a monitorar
SYMBOLS = ["BTCUSDT"]

####################################################
##################### TRADING ######################
####################################################

# Valor em USDT por operacao de compra (fixo; sem % do capital)
TRADE_USDT = 50.0

# Multi-posicao por par: no maximo N lotes abertos; novas entradas exigem distancia minima
MAX_POSITIONS_PER_SYMBOL = 3
MIN_ENTRY_DISTANCE_PCT = 0.5

# Stop-loss e Take-profit: usados apenas pelo backtest.
# No bot ao vivo, SL/TP sao definidos dinamicamente pela LLM com base no ATR.
STOP_LOSS_PCT = 2.5
TAKE_PROFIT_PCT = 5.0

# Limite de perda total no dia em USDT
MAX_DAILY_LOSS_USDT = 20.0

####################################################
#################### SCHEDULER #####################
####################################################

# Intervalo entre ciclos de analise LLM (em minutos)
INTERVAL_MINUTES = 60

# Intervalo do ciclo rapido de monitoramento SL/TP (em minutos)
MONITOR_INTERVAL_MINUTES = 5

####################################################
##################### DISCORD ######################
####################################################

# Crie em: canal -> Integracoes -> Webhooks -> Novo Webhook
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

####################################################
#################### SUPABASE #####################
####################################################

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
# anon/publishable
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
# service_role (so migrations)
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
