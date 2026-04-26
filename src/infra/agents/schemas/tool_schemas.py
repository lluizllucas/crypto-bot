"""
Schemas JSON das tools disponibilizadas ao LLM.
Define o que o LLM pode "chamar" — enviado no toolConfig do Bedrock.
"""

TOOLS_BOT = [
    {
        "type": "function",
        "function": {
            "name": "open_position",
            "description": "Solicita abertura de nova posicao de compra.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":        {"type": "string", "description": "Par a comprar, ex: BTCUSDT"},
                    "confidence":    {"type": "number", "description": "Confianca na decisao (0.0 a 1.0)"},
                    "sl_percentage": {"type": "number", "description": "Stop-loss recomendado em % (1.0 a 5.0)"},
                    "tp_percentage": {"type": "number", "description": "Take-profit recomendado em % (minimo 2x o sl_percentage)"},
                    "reason":        {"type": "string", "description": "Justificativa objetiva em ate 2 frases"},
                },
                "required": ["symbol", "confidence", "sl_percentage", "tp_percentage", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sell_position",
            "description": "Vende uma posicao especifica por decisao estrategica (nao por SL/TP).",
            "parameters": {
                "type": "object",
                "properties": {
                    "position_id": {"type": "string", "description": "db_id da posicao a ser vendida"},
                    "confidence":  {"type": "number", "description": "Confianca na decisao (0.0 a 1.0)"},
                    "reason":      {"type": "string", "description": "Justificativa objetiva em ate 2 frases"},
                },
                "required": ["position_id", "confidence", "reason"],
            },
        },
    },
]

TOOLS_TP = [
    {
        "type": "function",
        "function": {
            "name": "sell_position",
            "description": "Vende uma posicao especifica realizando o lucro no TP.",
            "parameters": {
                "type": "object",
                "properties": {
                    "position_id": {"type": "string", "description": "db_id da posicao a ser vendida"},
                    "confidence":  {"type": "number", "description": "Confianca na decisao (0.0 a 1.0)"},
                    "reason":      {"type": "string", "description": "Justificativa objetiva em ate 2 frases"},
                },
                "required": ["position_id", "confidence", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hold_position",
            "description": "Mantem uma posicao aberta apos o TP ser atingido, apostando em continuacao da alta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "position_id": {"type": "string", "description": "db_id da posicao a ser mantida"},
                    "confidence":  {"type": "number", "description": "Confianca na decisao (0.0 a 1.0)"},
                    "reason":      {"type": "string", "description": "Justificativa objetiva em ate 2 frases"},
                },
                "required": ["position_id", "confidence", "reason"],
            },
        },
    },
]

TOOLS_EARLY_EXIT = [
    {
        "type": "function",
        "function": {
            "name": "early_exit",
            "description": "Sai antecipadamente de uma posicao antes do SL ser atingido.",
            "parameters": {
                "type": "object",
                "properties": {
                    "position_id": {"type": "string", "description": "db_id da posicao a sair"},
                    "confidence":  {"type": "number", "description": "Confianca na decisao (0.0 a 1.0)"},
                    "reason":      {"type": "string", "description": "Justificativa objetiva em ate 2 frases"},
                },
                "required": ["position_id", "confidence", "reason"],
            },
        },
    },
]

TOOLS_QUERY = [
    {
        "type": "function",
        "function": {
            "name": "get_candles",
            "description": (
                "Busca candles OHLCV de um timeframe especifico. "
                "Use para analisar tendencia em 4h ou precisao de entrada em 15m."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":    {"type": "string", "description": "Par, ex: BTCUSDT"},
                    "timeframe": {
                        "type": "string",
                        "enum": ["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
                        "description": "Timeframe dos candles",
                    },
                    "limit": {"type": "integer", "description": "Numero de candles (5 a 100)", "default": 20},
                },
                "required": ["symbol", "timeframe"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rsi_history",
            "description": (
                "Retorna o historico de RSI das ultimas N velas (1h). "
                "Use para identificar divergencias de longo prazo e tendencia do momentum."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":  {"type": "string", "description": "Par, ex: BTCUSDT"},
                    "periods": {"type": "integer", "description": "Numero de velas (5 a 50)", "default": 20},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_volume_profile",
            "description": (
                "Retorna volume por candle das ultimas N horas com classificacao relativa a media. "
                "Use para confirmar se o volume atual e realmente anomalo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":  {"type": "string", "description": "Par, ex: BTCUSDT"},
                    "periods": {"type": "integer", "description": "Numero de horas (5 a 48)", "default": 24},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ema_history",
            "description": (
                "Retorna a distancia percentual do preco em relacao a uma EMA ao longo do tempo. "
                "Use para identificar preco muito esticado (candidato a mean reversion) ou recuo saudavel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":  {"type": "string", "description": "Par, ex: BTCUSDT"},
                    "ema":     {"type": "integer", "enum": [20, 50, 200], "description": "Periodo da EMA"},
                    "periods": {"type": "integer", "description": "Numero de velas historicas (5 a 50)", "default": 20},
                },
                "required": ["symbol", "ema"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_highs_lows",
            "description": (
                "Retorna as maximas e minimas locais das ultimas N velas (1h), "
                "identificando suportes e resistencias recentes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":  {"type": "string", "description": "Par, ex: BTCUSDT"},
                    "periods": {"type": "integer", "description": "Numero de velas (10 a 100)", "default": 48},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_volatility_history",
            "description": (
                "Retorna o ATR das ultimas N velas (1h). "
                "Use para ver se a volatilidade esta aumentando ou diminuindo e ajustar SL/TP."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":  {"type": "string", "description": "Par, ex: BTCUSDT"},
                    "periods": {"type": "integer", "description": "Numero de velas (5 a 50)", "default": 20},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_range_breakdown",
            "description": (
                "Retorna o range (high-low) de diferentes janelas de tempo e a posicao atual do preco. "
                "Use para comparar ranges e identificar contracao ou expansao de volatilidade."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":  {"type": "string", "description": "Par, ex: BTCUSDT"},
                    "periods": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Lista de janelas em horas, ex: [24, 48, 168]. Maximo 6 valores.",
                        "default": [24, 48, 168],
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fear_greed_history",
            "description": (
                "Retorna o Fear & Greed Index dos ultimos N dias. "
                "Use para ver se o sentimento esta mudando rapidamente ou se mantem estavel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Numero de dias (1 a 30)", "default": 7},
                },
                "required": [],
            },
        },
    },
]
