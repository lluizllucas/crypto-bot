# Arquitetura Completa --- Projeto Python com DDD, Clean Architecture, LLM, Tools, Binance e futura API

## Visão geral

Projeto preparado para rodar hoje por scripts e evoluir para API,
workers e schedulers.

## Estrutura recomendada

``` text
src/
├── domain/
├── application/
├── clients/
├── infrastructure/
├── interfaces/
└── main.py
```

## Organização do OpenAI

``` text
clients/llm/openai/
├── openai_client.py
├── tool_executor.py
├── agent.py
├── schemas/
└── tools/
```

## Onde colocar as services

A localização das services depende da responsabilidade arquitetural.

### Domain services (`domain/services`)

Se a service contém **regra de negócio pura**, ela deve ficar no
domínio.

Exemplos:

-   análise de risco
-   cálculo de stop loss
-   take profit
-   sizing de posição
-   exposição máxima da carteira

Estrutura sugerida:

``` text
domain/
   services/
      risk/
         risk_analysis_service.py
         stop_loss_service.py
         position_sizing_service.py
```

Exemplo:

``` python
class RiskAnalysisService:
    def calculate_trade_risk(self, entry_price: float, stop_loss: float, capital: float) -> float:
        loss = abs(entry_price - stop_loss)
        return (loss / capital) * 100
```

Essas regras devem funcionar independentemente de API, banco ou LLM.

### Application services (`application/services`)

Se a service **orquestra fluxo** entre componentes, integrações e casos
de uso, ela deve ficar na camada de aplicação.

Exemplos:

-   chamar Binance
-   chamar LLM
-   salvar resultados
-   coordenar múltiplos serviços

Estrutura sugerida:

``` text
application/
   services/
      trading_orchestrator_service.py
      market_analysis_service.py
```

Exemplo:

``` python
class TradeDecisionService:
    def __init__(self, llm_client, risk_service, binance_client):
        self.llm_client = llm_client
        self.risk_service = risk_service
        self.binance_client = binance_client
```

### Regra prática

-   Se a lógica pode rodar em memória sem dependências externas →
    **domain**
-   Se depende de integrações e coordenação → **application**
