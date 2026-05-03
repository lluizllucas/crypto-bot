# Arquitetura de Referência — CryptoBot Python (DDD + Clean Architecture)

## Visão geral

Projeto que roda hoje via **scripts** na raiz de `src/`, mas estruturado para evoluir
naturalmente para API REST, workers e schedulers sem reescrever regras de negócio.

Princípio central:

> Scripts, API e filas devem chamar os mesmos use-cases. A forma de execução nunca contém regra de negócio.

---

## Estrutura de diretórios recomendada

```text
src/
├── domain/
│   ├── entities/
│   │   └── position.py
│   ├── value_objects/
│   │   └── trade_signal.py
│   ├── services/
│   │   ├── risk_service.py          # cálculo de SL/TP, sizing
│   │   └── signal_service.py        # geração de sinais técnicos puros
│   └── repositories/
│       └── position_repository.py   # interface (porta), sem implementação
│
├── application/
│   ├── use_cases/
│   │   ├── analyze_market.py        # orquestra: dados → LLM → decisão
│   │   └── generate_trade_signal.py # orquestra: dados → signal técnico
│   ├── services/
│   │   └── llm_orchestrator.py      # monta prompt, chama agent, processa resposta
│   ├── ports/
│   │   ├── llm_port.py              # interface abstrata do LLM
│   │   └── market_port.py           # interface abstrata de dados de mercado
│   └── dto/
│       └── market_data.py           # objetos de transferência entre camadas
│
├── infra/
│   ├── clients/
│   │   └── binance/
│   │       └── client.py
│   │
│   ├── agents/
│   │   ├── client.py                # wrapper unificado (escolhe provider)
│   │   ├── providers/
│   │   │   ├── bedrock_provider.py  # implementação AWS Bedrock
│   │   │   └── openai_provider.py   # implementação OpenAI (futura)
│   │   ├── trade_agent.py           # tools + system prompt + loop de execução
│   │   ├── tools/
│   │   │   ├── market/
│   │   │   │   ├── get_candles.py
│   │   │   │   └── get_market_data.py
│   │   │   ├── portfolio/
│   │   │   │   └── get_positions.py
│   │   │   └── execution/
│   │   │       ├── open_position.py
│   │   │       └── close_position.py
│   │   ├── prompts/
│   │   │   ├── trade_prompt.txt
│   │   │   └── risk_analysis_prompt.txt
│   │   ├── memory/
│   │   │   └── context_builder.py   # monta contexto dinâmico (histórico, posições)
│   │   └── schemas/
│   │       └── tool_schemas.py      # JSON schemas das tools para o LLM
│   │
│   ├── persistence/
│   │   ├── client.py
│   │   └── repository.py
│   │
│   └── logging/
│       └── setup.py
│
├── interfaces/
│   ├── scripts/
│   │   ├── bot.py                   # ponto de entrada principal hoje
│   │   ├── check_sl_tp.py
│   │   └── resumo.py
│   ├── cli/                         # futura CLI estruturada
│   └── api/                         # futura API FastAPI
│       ├── routes/
│       └── controllers/
│
└── config.py
```

---

## Responsabilidade por camada

### `domain/`

Camada mais importante. Não conhece LLM, Binance, banco ou HTTP.

- **entities/**: objetos com identidade e ciclo de vida (`Position`)
- **value_objects/**: objetos imutáveis sem identidade (`TradeSignal`, `MarketData`)
- **services/**: regras puras que rodam em memória, sem dependências externas
- **repositories/**: interfaces (portas) que definem contratos, implementados na infra

```python
# domain/services/risk_service.py
class RiskService:
    def calculate_stop_loss(self, entry: float, risk_pct: float) -> float:
        return entry * (1 - risk_pct / 100)

    def calculate_position_size(self, capital: float, risk_pct: float, sl_distance: float) -> float:
        risk_amount = capital * (risk_pct / 100)
        return risk_amount / sl_distance
```

### `application/`

Orquestra fluxos. Conhece as portas (interfaces), nunca as implementações concretas.

- **use_cases/**: um arquivo por caso de uso, recebe dependências por injeção
- **services/**: coordena múltiplos componentes (ex: montar contexto + chamar agent + processar resposta)
- **ports/**: interfaces abstratas que a infra implementa (inversão de dependência)
- **dto/**: objetos de transferência entre camadas, sem lógica

```python
# application/use_cases/analyze_market.py
class AnalyzeMarketUseCase:
    def __init__(self, llm_orchestrator: LLMOrchestrator, market_port: MarketPort):
        self.llm = llm_orchestrator
        self.market = market_port

    def execute(self, symbol: str) -> TradeDecision:
        data = self.market.get_market_data(symbol)
        return self.llm.analyze(data)
```

### `infra/clients/`

Wrappers de APIs externas. Um diretório por integração, isolados entre si.

```text
infra/clients/
└── binance/
    └── client.py    # wrapper do SDK da Binance
```

Se no futuro houver outros clients:

```text
infra/clients/
├── binance/
├── coingecko/
└── telegram/
```

### `infra/agents/`

Subsistema completo do LLM — vai além de um simples client porque tem loop, tools, memória e prompt.

| Arquivo / Pasta  | Responsabilidade                                                 |
| ---------------- | ---------------------------------------------------------------- |
| `client.py`      | wrapper unificado, escolhe o provider via config                 |
| `providers/`     | um arquivo por provedor (Bedrock, OpenAI)                        |
| `trade_agent.py` | define tools, system prompt e loop de execução                   |
| `tools/`         | tools agrupadas por domínio (market, portfolio, execution)       |
| `schemas/`       | JSON schemas enviados ao LLM (o que ele pode "chamar")           |
| `prompts/`       | arquivos `.txt` com os prompts base                              |
| `memory/`        | monta contexto dinâmico: histórico de decisões, posições abertas |

```python
# infra/agents/client.py
class LLMClient:
    def __init__(self, provider: str, config: Config):
        if provider == "bedrock":
            self._provider = BedrockProvider(config)
        elif provider == "openai":
            self._provider = OpenAIProvider(config)

    def create_response(self, messages, tools=None):
        return self._provider.create_response(messages, tools)
```

```python
# infra/agents/trade_agent.py
class TradeAgent:
    def __init__(self, llm_client, tool_executor, context_builder):
        self.llm = llm_client
        self.executor = tool_executor
        self.context = context_builder

    def run(self, market_data, positions, max_query_rounds=3):
        messages = self.context.build(market_data, positions)
        for _ in range(max_query_rounds):
            response = self.llm.create_response(messages, tools=TOOLS_SCHEMA)
            tool_calls = self._extract_tool_calls(response)
            if not tool_calls:
                break
            for call in tool_calls:
                result = self.executor.execute(call.name, call.arguments)
                messages.append({"role": "tool", "content": result})
        return response
```

### `infra/agents/tools/`

Uma tool por arquivo, agrupadas por domínio. Cada uma recebe suas dependências como parâmetro — sem estado global.

```python
# infra/agents/tools/market/get_candles.py
def get_candles(symbol: str, interval: str, limit: int, binance_client) -> dict:
    return binance_client.get_klines(symbol, interval, limit)
```

```python
# infra/agents/schemas/tool_schemas.py
TOOLS_SCHEMA = [
    {
        "type": "function",
        "name": "get_candles",
        "description": "Busca candles OHLCV de um par",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol":   {"type": "string"},
                "interval": {"type": "string"},
                "limit":    {"type": "integer"}
            },
            "required": ["symbol", "interval", "limit"]
        }
    }
]
```

### `infra/persistence/`

Tudo relacionado a banco de dados. Hoje Supabase, amanhã qualquer outro.

```text
infra/persistence/
├── client.py        # conexão com o banco
└── repository.py    # queries e operações de dados
```

### `interfaces/`

Pontos de entrada. Não contêm regra de negócio — apenas instanciam dependências e chamam use-cases.

```python
# interfaces/scripts/bot.py
from src.application.use_cases.analyze_market import AnalyzeMarketUseCase
from src.infra.agents.client import LLMClient
from src.infra.clients.binance.client import BinanceClient

def main():
    binance = BinanceClient(config)
    llm = LLMClient(provider="bedrock", config=config)
    use_case = AnalyzeMarketUseCase(llm, binance)
    result = use_case.execute("BTCUSDT")
```

---

## Fluxo completo

```text
interfaces/scripts/bot.py
    ↓ instancia e chama
application/use_cases/analyze_market.py
    ↓ chama
application/services/llm_orchestrator.py
    ↓ usa
infra/agents/trade_agent.py
    ↓ chama LLM em loop
infra/agents/providers/bedrock_provider.py
    ↓ LLM responde com tool_call
infra/agents/tools/market/get_candles.py   ←→   infra/clients/binance/client.py
    ↓ resultado volta ao LLM
infra/agents/providers/bedrock_provider.py
    ↓ decisão final retorna por toda a pilha
interfaces/scripts/bot.py
```

---

## Regras de dependência

```text
domain       → nenhuma dependência interna
application  → apenas domain (via ports)
infra        → domain + application/ports
interfaces   → application (use_cases) + infra (para instanciar)
```

Nunca:

- `domain` importar `infra` ou `application`
- `application` importar `infra` diretamente (usar as portas)

---

## Estado atual vs. destino

| Hoje                                  | Destino                                                                              |
| ------------------------------------- | ------------------------------------------------------------------------------------ |
| `src/application/llm_analyst.py`      | `infra/agents/trade_agent.py` + `application/use_cases/analyze_market.py`            |
| `src/application/tools.py`            | `infra/agents/tools/` (um arquivo por tool) + `infra/agents/schemas/tool_schemas.py` |
| `src/application/signal_generator.py` | `domain/services/signal_service.py`                                                  |
| `src/application/risk_manager.py`     | `domain/services/risk_service.py`                                                    |
| `src/application/market_queries.py`   | `infra/agents/tools/market/` (tools de consulta)                                     |
| `src/domain/models.py`                | `domain/entities/` + `domain/value_objects/`                                         |
| `src/bot.py`                          | `interfaces/scripts/bot.py`                                                          |
| `src/infra/binance/client.py`         | `infra/clients/binance/client.py`                                                    |
| `src/infra/supabase/`                 | `infra/persistence/`                                                                 |

---

## Migração incremental recomendada

A migração pode ser feita em etapas sem quebrar o funcionamento atual:

1. **Mover domain**: extrair entidades e serviços puros de `domain/models.py` e `risk_manager.py`
2. **Separar tools**: quebrar `application/tools.py` em `infra/agents/tools/` (um arquivo por tool) e `infra/agents/schemas/`
3. **Criar agent**: mover a lógica de loop do LLM de `llm_analyst.py` para `infra/agents/trade_agent.py`
4. **Criar use-cases**: extrair a orquestração de alto nível para `application/use_cases/`
5. **Reorganizar infra**: mover `infra/binance/` → `infra/clients/binance/` e `infra/supabase/` → `infra/persistence/`
6. **Mover scripts**: mover `bot.py`, `check_sl_tp.py`, `resumo.py` para `interfaces/scripts/`

---

## Evolução para API (sem reescrita)

```python
# interfaces/api/routes/analysis.py
from fastapi import APIRouter
from src.application.use_cases.analyze_market import AnalyzeMarketUseCase

router = APIRouter()

@router.post("/analyze/{symbol}")
def analyze(symbol: str, use_case: AnalyzeMarketUseCase = Depends(get_use_case)):
    return use_case.execute(symbol)
```

O use-case não muda. Apenas um novo ponto de entrada é adicionado.
