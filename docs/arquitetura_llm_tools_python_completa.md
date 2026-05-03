# Arquitetura Completa --- Projeto Python com DDD, Clean Architecture, LLM, Tools, Binance e futura API

## Visão geral

Este documento consolida toda a arquitetura discutida para um projeto
que atualmente roda por **scripts**, mas foi desenhado para evoluir de
forma natural para:

-   API REST (ex: FastAPI)
-   workers / filas
-   schedulers / cron jobs
-   execução manual por CLI
-   automações futuras

A proposta segue os princípios de:

-   **DDD (Domain Driven Design)**
-   **Clean Architecture**
-   **Hexagonal / Ports & Adapters**
-   separação clara entre **regra de negócio**, **integrações externas**
    e **interfaces de entrada**

------------------------------------------------------------------------

## Princípio mais importante

A forma de execução nunca deve conter regra de negócio.

Em outras palavras:

> script, API, fila e worker devem chamar os mesmos use-cases

Exemplo:

-   hoje: script executa análise
-   amanhã: endpoint HTTP executa análise
-   depois: fila executa análise

Todos chamam o mesmo caso de uso.

------------------------------------------------------------------------

## Estrutura recomendada

``` text
src/
├── domain/
│   ├── entities/
│   ├── value_objects/
│   ├── services/
│   └── repositories/
│
├── application/
│   ├── ports/
│   ├── dto/
│   └── use_cases/
│
├── clients/
│   ├── binance/
│   │   └── binance_client.py
│   │
│   └── llm/
│       └── openai/
│           ├── openai_client.py
│           ├── tool_executor.py
│           ├── agent.py
│           ├── schemas/
│           │   └── tool_definitions.py
│           │
│           └── tools/
│               ├── __init__.py
│               ├── market/
│               ├── portfolio/
│               └── execution/
│
├── infrastructure/
│   ├── persistence/
│   └── config/
│
├── interfaces/
│   ├── scripts/
│   ├── cli/
│   └── api/
│
└── main.py
```

------------------------------------------------------------------------

## Responsabilidade por camada

### domain/

Camada mais importante.

Contém:

-   entidades
-   regras de negócio
-   validações
-   serviços de domínio
-   interfaces de repositório

Nunca deve conhecer:

-   OpenAI
-   Binance
-   banco ORM
-   FastAPI
-   requests HTTP

Exemplo:

``` python
from dataclasses import dataclass
from decimal import Decimal

@dataclass
class Position:
    symbol: str
    quantity: Decimal
    average_price: Decimal
```

------------------------------------------------------------------------

### application/

Contém os **use-cases**.

Aqui mora o fluxo da aplicação.

Exemplo:

``` python
class AnalyzeMarketUseCase:
    def __init__(self, llm_port, market_port):
        self.llm_port = llm_port
        self.market_port = market_port

    def execute(self, symbol: str):
        price = self.market_port.get_price(symbol)
        return self.llm_port.ask(f"Analyze {symbol}: {price}")
```

------------------------------------------------------------------------

### clients/

Integrações externas.

Exemplo:

-   OpenAI
-   Binance
-   APIs terceiras

------------------------------------------------------------------------

## Organização do OpenAI

Estrutura ideal:

``` text
clients/llm/openai/
├── openai_client.py
├── tool_executor.py
├── agent.py
├── schemas/
└── tools/
```

------------------------------------------------------------------------

## openai_client.py

Responsável apenas pela comunicação com a API.

``` python
from openai import OpenAI

class OpenAIClient:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def create_response(self, messages, tools=None):
        return self.client.responses.create(
            model="gpt-4.1-mini",
            input=messages,
            tools=tools,
        )
```

Regra:

> nenhuma lógica de negócio aqui

------------------------------------------------------------------------

## tool_executor.py

Responsável por executar tools dinamicamente.

``` python
class ToolExecutor:
    def __init__(self, registry: dict):
        self.registry = registry

    def execute(self, tool_name: str, arguments: dict):
        tool = self.registry.get(tool_name)

        if not tool:
            raise ValueError(f"Tool {tool_name} not found")

        return tool(**arguments)
```

Essa abordagem é superior a múltiplos `if/else`.

------------------------------------------------------------------------

## Organização das tools

Uma tool por arquivo.

``` text
tools/
├── market/
│   ├── get_price.py
│   └── get_candles.py
│
├── portfolio/
│   ├── get_positions.py
│   └── get_balance.py
│
└── execution/
    ├── open_position.py
    └── close_position.py
```

------------------------------------------------------------------------

## Exemplos de tools

``` python
def get_price(symbol: str, binance_client):
    return binance_client.get_price(symbol)
```

``` python
def open_position(symbol: str, quantity: float, order_service):
    return order_service.execute(symbol, quantity)
```

------------------------------------------------------------------------

## Registry de tools

``` python
from .market.get_price import get_price
from .execution.open_position import open_position

TOOLS_REGISTRY = {
    "get_price": get_price,
    "open_position": open_position,
}
```

------------------------------------------------------------------------

## schemas/tool_definitions.py

``` python
TOOLS_SCHEMA = [
    {
        "type": "function",
        "name": "get_price",
        "description": "Get current symbol price",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"}
            },
            "required": ["symbol"]
        }
    }
]
```

------------------------------------------------------------------------

## agent.py

Coração da orquestração.

``` python
class TradingAgent:
    def __init__(self, llm_client, tool_executor):
        self.llm_client = llm_client
        self.tool_executor = tool_executor

    def run(self, messages):
        response = self.llm_client.create_response(messages)

        for item in response.output:
            if item.type == "function_call":
                return self.tool_executor.execute(
                    item.name,
                    item.arguments
                )

        return response
```

------------------------------------------------------------------------

## Fluxo completo

``` text
Script / API
    ↓
UseCase
    ↓
Agent
    ↓
OpenAI
    ↓
Tool Call
    ↓
Tool Executor
    ↓
Tool específica
    ↓
Binance / Banco
```

------------------------------------------------------------------------

## Persistência

Separar sempre:

-   entidade de domínio
-   model ORM

Errado:

``` python
class PositionModel(Base):
    ...
```

usado diretamente no domínio.

Certo:

``` python
@dataclass
class Position:
    ...
```

e mapper separado.

------------------------------------------------------------------------

## Evolução futura para API

``` text
interfaces/api/
├── routes/
└── controllers/
```

Exemplo:

``` python
from fastapi import APIRouter

router = APIRouter()

@router.post("/analyze")
def analyze(symbol: str):
    return use_case.execute(symbol)
```

Sem mudar regra interna.

------------------------------------------------------------------------

## Resumo final

A arquitetura ideal para seu projeto é:

> client simples + tool executor genérico + tools desacopladas + agent
> loop + use-cases independentes da interface
