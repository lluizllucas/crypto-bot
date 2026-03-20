# ─────────────────────────────────────────────────────────────────────────────
# config.py
# ─────────────────────────────────────────────────────────────────────────────

# 1. OpenRouter API Key (grátis, sem cartão)
#    → Acesse: https://openrouter.ai
#    → Crie conta com Google ou GitHub
#    → Vá em: https://openrouter.ai/settings/keys → "Create Key"
OPENROUTER_API_KEY = "OPENROUTER_API_KEY"

# 2. Binance TESTNET (sem dinheiro real, sem dados fiscais)
#    → Acesse: https://testnet.binance.vision
#    → Clique em "Log in with GitHub"
#    → Vá em "API Keys" → "Generate HMAC_SHA256 Key"
BINANCE_API_KEY    = "BINANCE_API_KEY"
BINANCE_SECRET_KEY = "BINANCE_SECRET_KEY "

# ─────────────────────────────────────────────────────────────────────────────
# Parâmetros do bot
# ─────────────────────────────────────────────────────────────────────────────

# Pares a monitorar (todos terminam em USDT na Binance)
SYMBOLS = ["BTCUSDT"]

# Valor em USDT por operação de compra
TRADE_USDT = 50.0

# Confiança mínima para executar uma ordem (0.0 a 1.0)
MIN_CONFIDENCE = 0.65

# Intervalo entre ciclos de analise LLM (em minutos)
INTERVAL_MINUTES = 60
 
# Intervalo do ciclo rapido de monitoramento SL/TP (em minutos)
# Nao chama LLM -- apenas busca preco atual na Binance
MONITOR_INTERVAL_MINUTES = 5
 
# ── Gestao de risco ───────────────────────────────────────────────────────────
 
# Stop-loss: fecha a posicao se cair X% desde a entrada
# Backtest 365 dias: SL foi acionado 51x com prejuizo total de -$93
# Reduzir para 2.5% para cortar perdas mais cedo
STOP_LOSS_PCT = 2.5
 
# Take-profit: fecha a posicao se subir X% desde a entrada
# Mantem 5% -- responsavel por todo o lucro no backtest ($201 em 69 TPs)
TAKE_PROFIT_PCT = 5.0
 
# Limite de perda total no dia em USDT -- sem novas compras apos atingir
MAX_DAILY_LOSS_USDT = 20.0

