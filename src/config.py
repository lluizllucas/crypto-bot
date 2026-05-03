import os

from dotenv import load_dotenv

load_dotenv()

####################################################
################### OPERAÇÃO #######################
####################################################

MIN_CONFIDENCE = 0.75
MIN_CONFIDENCE_SELL = 0.70

####################################################
#################### BEDROCK #######################
####################################################

BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
BEDROCK_REGION   = os.getenv("BEDROCK_REGION",   "us-east-1")

####################################################
##################### BINANCE #####################
####################################################

BINANCE_TESTNET_API_KEY    = os.getenv("BINANCE_TESTNET_API_KEY",    "")
BINANCE_TESTNET_SECRET_KEY = os.getenv("BINANCE_TESTNET_SECRET_KEY", "")

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY",    "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")

SYMBOLS = ["BTCUSDT"]

####################################################
##################### TRADING ######################
####################################################

TRADE_USDT = 100.0

MAX_POSITIONS_PER_SYMBOL = 3
MIN_ENTRY_DISTANCE_PCT = 0.5

STOP_LOSS_PCT = 1.0
TAKE_PROFIT_PCT = 2.0

MAX_DAILY_LOSS_USDT = 20.0

####################################################
################# TP PROGRESSIVO ###################
####################################################

TP_HOLD_MIN_CONFIDENCE = [0.75, 0.85, 0.90]

TP_EXTENSION_MULTIPLIER = 1.5

SL_EARLY_EXIT_THRESHOLD = 0.80

MIN_CONFIDENCE_EARLY_EXIT = 0.70

AVERAGING_DOWN_BLOCK_HOURS = 4
AVERAGING_DOWN_MIN_PNL_PCT = -1.0

MIN_SETUP_SCORE_FOR_LLM = 40

####################################################
##################### DISCORD ######################
####################################################

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

####################################################
##################### ENV ##########################
####################################################

ENV = os.getenv("ENV", "production")

####################################################
#################### POSTGRES #####################
####################################################

POSTGRES_HOST     = os.getenv("POSTGRES_HOST",     "localhost")
POSTGRES_PORT     = os.getenv("POSTGRES_PORT",     "5432")
POSTGRES_DB       = os.getenv("POSTGRES_DB",       "cryptobot")
POSTGRES_USER     = os.getenv("POSTGRES_USER",     "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "123456")