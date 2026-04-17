# Trading Decision Flow — Especificação

## Visão Geral

O bot opera com dois agentes distintos e com responsabilidades bem definidas:

- **Monitor**: processo técnico, rápido, sem LLM. Responsável por verificar SL e acionar o LLM quando necessário.
- **LLM**: cérebro do bot. Toma todas as decisões estratégicas via tools, por posição individual.

A separação garante que proteção de capital nunca dependa de latência ou disponibilidade de API externa.

---

## Princípios Fundamentais

1. **SL é sagrado** — executado pelo Monitor diretamente, sem consulta ao LLM, sempre.
2. **LLM decide por posição individual** — não de forma genérica para o símbolo.
3. **Confiança é validada pelo código** — o LLM propõe via tool, o código valida e executa.
4. **Proteção cresce com o lucro** — quanto mais o bot segura uma posição, maior a proteção acumulada via SL progressivo.

---

## Arquitetura de Decisão

### Tools disponíveis para o LLM

O LLM não retorna mais um JSON genérico em nenhum dos dois processos. Em ambos os fluxos (`check_sl_tp.py` e `bot.py`), ele recebe o contexto completo e chama tools específicas para cada ação, informando o `position_id` ou `symbol` e sua `confidence`.

O código valida a confiança de cada chamada antes de executar qualquer ação.

#### Tools disponíveis no `check_sl_tp.py` (Monitor SL/TP)

| Tool                                             | Quando é oferecida | Descrição                                                           |
| ------------------------------------------------ | ------------------ | ------------------------------------------------------------------- |
| `early_exit(position_id, confidence, reason)`    | Preço a 80% do SL  | Solicita saída antecipada antes do SL ser atingido                  |
| `sell_position(position_id, confidence, reason)` | TP atingido        | Solicita venda e realização do lucro                                |
| `hold_position(position_id, confidence, reason)` | TP atingido        | Solicita manutenção — sujeito ao threshold progressivo de confiança |

#### Tools disponíveis no `bot.py` (Ciclo de Análise)

| Tool                                             | Quando é oferecida                                  | Descrição                                                        |
| ------------------------------------------------ | --------------------------------------------------- | ---------------------------------------------------------------- |
| `open_position(symbol, confidence, reason)`      | Sempre, se há saldo e limite de posições disponível | Solicita abertura de nova compra                                 |
| `sell_position(position_id, confidence, reason)` | Sempre que há posições abertas                      | Solicita venda de uma posição específica por decisão estratégica |

> O LLM pode não chamar nenhuma tool — nesse caso nenhuma ação é executada.

---

## Dois Processos Independentes

O bot opera com dois scripts separados, agendados via EventBridge no Fargate:

| Script           | Intervalo         | Responsabilidade                                                     |
| ---------------- | ----------------- | -------------------------------------------------------------------- |
| `check_sl_tp.py` | A cada 5 minutos  | Verificar SL e acionar LLM quando TP é atingido ou early exit        |
| `bot.py`         | A cada 15 minutos | Análise LLM completa: decidir compras, modo de operação e estratégia |

A separação garante que a proteção de capital (SL) roda com alta frequência e nunca fica bloqueada pela latência da chamada LLM.

---

## Processo 1 — Monitor SL/TP (`check_sl_tp.py`, a cada 5 min)

Carrega posições do Supabase, verifica preço atual e age conforme os níveis de cada lote:

```
Para cada posição aberta:
│
├── 1. Verificar SL
│   └── Se preço <= SL → vende imediatamente (sem LLM) ✓
│
├── 2. Verificar proximidade do SL (preço a 80% do caminho até o SL)
│   └── Consulta LLM → LLM pode chamar: early_exit(position_id, confidence)
│       ├── confiança >= mínimo → vende antecipadamente
│       └── confiança < mínimo ou LLM não aciona → mantém, SL continua como proteção
│
└── 3. Verificar TP
    └── Consulta LLM → LLM pode chamar:
        ├── sell_position(position_id, confidence) → vende, realiza lucro
        └── hold_position(position_id, confidence) → segura se confiança válida
            ├── confiança >= threshold da tentativa atual
            │   └── SL sobe, TP sobe × 1.5, contador de tentativas +1
            └── confiança < threshold → vende (realiza lucro atual)
```

---

## Processo 2 — Ciclo de Análise (`bot.py`, a cada 15 min)

Busca dados de mercado completos, consulta o LLM e executa decisões estratégicas:

```
Para cada símbolo monitorado:
│
├── 1. Buscar dados de mercado
│   ├── 200 candles 1h da Binance
│   ├── Calcular indicadores (RSI, EMA, MACD, ATR, BB, volume)
│   ├── Calcular ranges 24h / 7d / 30d
│   └── Buscar Fear & Greed Index
│
├── 2. Montar contexto para o LLM
│   ├── Dados de mercado completos
│   ├── Últimas 4 velas (price action)
│   ├── Posições abertas com PnL%, horas abertas, distância SL/TP
│   └── Tentativas de hold anteriores por posição
│
├── 3. Consultar LLM via tools
│   └── LLM recebe contexto e chama tools (ou nenhuma):
│       ├── open_position(symbol, confidence, reason)
│       │   └── código valida antes de executar:
│       │       ├── confiança >= MIN_CONFIDENCE
│       │       ├── posições abertas < MAX_POSITIONS_PER_SYMBOL
│       │       ├── distância mínima da última entrada respeitada
│       │       ├── saldo USDT suficiente
│       │       └── limite diário de perda não atingido → executa BUY
│       ├── sell_position(position_id, confidence, reason)
│       │   └── código valida confiança mínima → vende posição específica
│       └── (nenhuma tool chamada) → nenhuma ação executada
│
└── 4. Salvar log LLM no Supabase (auditoria)
```

---

## Fluxo Detalhado: SL

### Execução direta (sem LLM)

Quando o preço cruza o nível de SL de qualquer posição:

- O Monitor executa a venda imediatamente
- Nenhuma consulta ao LLM é feita
- O motivo `STOP-LOSS` é registrado no histórico
- O LLM é informado do ocorrido no próximo ciclo regular (via contexto)

**Motivação:** SL existe para cenários de queda rápida. Latência de chamada LLM nesse momento representa risco direto de capital.

### Early Exit (saída antecipada)

Quando o preço está a 80% do caminho entre a entrada e o SL:

- Monitor consulta o LLM antes de atingir o SL
- LLM pode chamar `early_exit(position_id, confidence, reason)`
- Código valida confiança mínima configurável antes de executar
- Se LLM não chamar a tool ou confiança for insuficiente, posição é mantida
- SL continua como proteção final

---

## Fluxo Detalhado: TP com Hold Progressivo

### Quando o TP é atingido

O Monitor detecta que o preço cruzou o nível de TP e consulta o LLM imediatamente (chamada extra, fora do ciclo regular).

O LLM recebe:

- Contexto completo de mercado (preço, indicadores, fear & greed, ranges)
- Dados da posição (entrada, TP atingido, lucro atual em %, tentativas anteriores de hold)

O LLM então chama uma das tools disponíveis para aquela posição.

---

### Tabela de decisão por tentativa

| Tentativa de Hold | Confiança mínima para segurar | SL movido para                | Novo TP           |
| ----------------- | ----------------------------- | ----------------------------- | ----------------- |
| 1ª                | 0.75                          | Preço de entrada (break-even) | TP anterior × 1.5 |
| 2ª                | 0.85                          | TP original (lucro garantido) | TP anterior × 1.5 |
| 3ª+               | 0.90                          | TP da tentativa anterior      | TP anterior × 1.5 |

A partir da 3ª tentativa, o threshold de 0.90 se repete indefinidamente.

**Se em qualquer tentativa a confiança for menor que o mínimo exigido → vende imediatamente.**

**Se LLM chamar `sell_position` → vende imediatamente, independente da tentativa.**

---

### Proteção garantida por tentativa

| Tentativa        | Pior cenário possível           |
| ---------------- | ------------------------------- |
| Antes do 1º hold | Zero (SL original ainda válido) |
| Após 1º hold     | Break-even (não perde capital)  |
| Após 2º hold     | Lucro do TP original garantido  |
| Após 3º hold     | Lucro do 2º TP garantido        |
| Após Nth hold    | Lucro do (N-1)º TP garantido    |

O SL progressivo garante que o Monitor pode fechar a posição a qualquer momento por SL, capturando o lucro acumulado sem depender do LLM.

---

### Exemplo numérico

Posição: entrada a $100.000, TP inicial a $102.500 (2.5%), SL inicial a $97.500 (2.5%)

| Evento                                     | Preço    | SL       | TP       | Lucro garantido    |
| ------------------------------------------ | -------- | -------- | -------- | ------------------ |
| Compra                                     | $100.000 | $97.500  | $102.500 | —                  |
| TP atingido, LLM segura (conf 0.82 ≥ 0.75) | $102.500 | $100.000 | $103.750 | Break-even         |
| TP atingido, LLM segura (conf 0.87 ≥ 0.85) | $103.750 | $102.500 | $105.625 | +$2.500            |
| TP atingido, LLM segura (conf 0.91 ≥ 0.90) | $105.625 | $103.750 | $108.437 | +$3.750            |
| TP atingido, LLM segura (conf 0.93 ≥ 0.90) | $108.437 | $105.625 | $112.656 | +$5.625            |
| Mercado reverte, SL atingido               | $105.625 | $105.625 | —        | +$5.625 realizados |

O bot nunca precisou do LLM para a saída final — o Monitor fechou pelo SL progressivo.

---

## Enriquecimento do Contexto enviado ao LLM

O LLM toma decisões melhores quanto mais rico for o contexto que recebe. Abaixo estão os dados que o bot envia hoje e as melhorias planejadas.

---

### Contexto atual

| Categoria            | Dados enviados hoje                                          |
| -------------------- | ------------------------------------------------------------ |
| Preço                | Preço atual                                                  |
| Indicadores técnicos | RSI 1h, EMA 20/50/200, ATR, BB upper/lower                   |
| Range engine         | Posição no range 24h/7d (0.0–1.0), high/low de 24h, 7d e 30d |
| Sentimento           | Fear & Greed Index (número bruto)                            |
| Volume               | Volume 24h, volume médio 5h                                  |
| Posições abertas     | Entrada, qty, SL, TP, PnL%                                   |

---

### Melhorias planejadas

#### Price Action — últimas velas

O LLM hoje só vê o último candle. Sem as velas anteriores, ele não consegue distinguir um RSI 62 subindo de um RSI 62 caindo, ou um volume crescente de um volume decrescente.

**Adicionar:** resumo das últimas 4 velas (open, high, low, close, volume) para dar noção de direção e momentum recente.

---

#### Bollinger Bands — métricas derivadas

Hoje o LLM recebe os valores absolutos de `bb_upper` e `bb_lower`, mas não consegue avaliar o comportamento das bandas sem calcular métricas adicionais por conta própria.

**Adicionar:**

- **BB Width** (`(bb_upper - bb_lower) / bb_mid`): indica compressão das bandas. Valores baixos sinalizam squeeze, que precede movimentos explosivos.
- **%B** (`(price - bb_lower) / (bb_upper - bb_lower)`): posição relativa do preço dentro das bandas. 0 = na banda inferior, 1 = na banda superior.

---

#### MACD

Hoje o bot não possui nenhum indicador de momentum de médias. O MACD complementa o RSI ao mostrar se o momentum está acelerando ou revertendo, e seus cruzamentos são sinais clássicos de entrada e saída.

**Adicionar:** MACD linha, MACD sinal e histograma (diferença entre os dois), calculados sobre as velas 1h.

---

#### Variação percentual recente

O LLM não sabe quanto o preço variou nos períodos recentes, o que impede avaliar se estamos no início ou no fim de um movimento.

**Adicionar:** variação percentual do preço em 1h, 4h e 24h.

---

#### Volume ratio

Hoje o bot envia volume 24h e média 5h como valores absolutos. Um número isolado não diz se o volume está alto ou baixo em relação ao histórico.

**Adicionar:** `volume_ratio` — razão entre o volume atual e a média histórica (ex: `1.8` significa 80% acima da média). Valores acima de 1.5 confirmam rompimentos e reversões.

---

#### Direção do RSI

RSI 62 não diz nada sobre a tendência de momentum. A mesma leitura pode indicar força crescente ou divergência bearish, dependendo da direção.

**Adicionar:** direção do RSI nas últimas 3 velas (`rising` / `falling` / `flat`) e flag de divergência simples (preço subindo + RSI caindo = bearish divergence, e vice-versa).

---

#### Contexto das posições abertas — enriquecido

Hoje o LLM sabe entrada, SL, TP e PnL%, mas não tem informações temporais ou de proximidade dos níveis.

**Adicionar por posição:**

- Horas desde a abertura da posição
- Distância percentual até o SL
- Distância percentual até o TP
- Número de tentativas de hold já realizadas (quando TP progressivo for implementado)

---

#### Label do Fear & Greed

Hoje o LLM recebe apenas o número bruto (ex: `34`). Enviar o label junto elimina ambiguidade na interpretação da escala.

**Adicionar:** label textual junto ao valor (ex: `{ "value": 34, "label": "Fear" }`).

---

### Tabela de impacto por melhoria

| Melhoria                        | Onde calcular                      | Impacto esperado                   |
| ------------------------------- | ---------------------------------- | ---------------------------------- |
| Últimas 4 velas (OHLCV)         | `market_data.py`                   | Alto — direção e momentum recente  |
| BB Width e %B                   | `indicators.py` + `market_data.py` | Alto — squeeze e posição relativa  |
| MACD (linha, sinal, histograma) | `indicators.py` + `market_data.py` | Alto — momentum de médias          |
| Variação % 1h, 4h, 24h          | `market_data.py`                   | Médio — amplitude do movimento     |
| Volume ratio                    | `market_data.py`                   | Médio — confirmação de volume      |
| Direção e divergência do RSI    | `llm_analyst.py`                   | Médio — qualidade do sinal         |
| Horas abertas + distância SL/TP | `llm_analyst.py`                   | Médio — gestão de risco contextual |
| Label do Fear & Greed           | `llm_analyst.py`                   | Baixo — clareza de interpretação   |

### O que não será adicionado agora

| Dado                              | Motivo                                                    |
| --------------------------------- | --------------------------------------------------------- |
| Order book / liquidações          | Requer WebSocket em tempo real, complexidade alta         |
| On-chain data                     | APIs pagas, latência alta                                 |
| Múltiplos timeframes (4h, diário) | Aumenta custo de tokens sem ganho proporcional no momento |
| Correlação com outras criptos     | Complexidade alta, pouco ganho com símbolo único          |

---

## Parâmetros Configuráveis

Todos os valores são configuráveis via `config.py`, sem alterar a lógica:

| Parâmetro                   | Valor padrão       | Descrição                                      |
| --------------------------- | ------------------ | ---------------------------------------------- |
| `MONITOR_INTERVAL_MIN`      | 15                 | Intervalo do ciclo em minutos                  |
| `SL_EARLY_EXIT_THRESHOLD`   | 0.80               | % do caminho até o SL para acionar early exit  |
| `TP_HOLD_MIN_CONFIDENCE`    | [0.75, 0.85, 0.90] | Confiança mínima por tentativa de hold         |
| `TP_EXTENSION_MULTIPLIER`   | 1.5                | Multiplicador do novo TP a cada hold           |
| `MIN_CONFIDENCE_EARLY_EXIT` | 0.70               | Confiança mínima para early exit ser executado |

---

## Arquivos Impactados

| Arquivo                        | O que muda                                                                                                                                                                |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `config.py`                    | Novos parâmetros de configuração                                                                                                                                          |
| `domain/models.py`             | `Position` recebe `tp_hold_count`, `original_sl`, `original_tp`; `MarketData` recebe novos campos de contexto                                                             |
| `application/indicators.py`    | Adiciona cálculo de MACD, BB Width e %B                                                                                                                                   |
| `application/market_data.py`   | Adiciona últimas 4 velas, variação % 1h/4h/24h, volume ratio, novos campos ao `MarketData`                                                                                |
| `application/llm_analyst.py`   | LLM passa a usar tools em vez de retornar JSON genérico; `build_context` enriquecido com direção do RSI, divergências, horas abertas, distância SL/TP, label Fear & Greed |
| `application/risk_manager.py`  | Lógica completa do fluxo TP progressivo e early exit                                                                                                                      |
| `check_sl_tp.py`               | Integra consulta ao LLM quando TP é atingido ou early exit é acionado                                                                                                     |
| `infra/supabase/repository.py` | Persistência dos novos campos de `Position`                                                                                                                               |

---

## Bugs e Melhorias de Robustez Identificados

Problemas encontrados na análise do código atual, separados por severidade.

---

### Bugs críticos

#### `db_id` não restaurado ao reiniciar — posições fantasma

Ao carregar posições do Supabase na inicialização (`load_positions()`), o campo `db_id` do objeto `Position` nunca é populado. Quando o bot tenta fechar uma posição após restart, `pos.db_id` está vazio, o `delete_position()` é silenciosamente ignorado e o registro permanece no banco como posição "fantasma". Em ciclos seguintes, o bot acha que tem menos posições abertas do que realmente tem e pode ultrapassar o `MAX_POSITIONS_PER_SYMBOL`.

**Correção:** popular `db_id` ao construir o `Position` dentro de `load_positions()`.

---

#### `daily_loss_usdt` zerado a cada container — limite diário ineficaz

O limite de perda diária é controlado por uma variável global em memória (`daily_loss_usdt`). No Fargate, cada execução é um container novo — a variável sempre começa zerada. O bot pode perder o dobro ou triplo do limite configurado num mesmo dia sem que o bloqueio seja ativado.

**Correção:** na inicialização, calcular `daily_loss_usdt` somando os trades de perda do dia atual diretamente do Supabase.

---

#### SELL sem PnL real registrado

Quando o sinal é SELL, o trade é salvo com `entry_price=0.0` e `pnl=0.0`. O bot tem posições abertas com entradas conhecidas — o PnL real de cada lote deveria ser calculado e registrado individualmente antes de fechar tudo.

**Correção:** no SELL, iterar pelas posições abertas, calcular PnL por lote e salvar cada fechamento corretamente antes de deletar.

---

#### Ordens duplicadas entre containers concorrentes

Se dois containers Fargate subirem ao mesmo tempo (falha de agendamento no EventBridge), ambos consultam a memória local antes de qualquer um persistir no banco — e ambos podem executar BUY para o mesmo símbolo, ultrapassando o `MAX_POSITIONS_PER_SYMBOL`.

**Correção:** verificar a contagem de posições diretamente no banco (não só na memória local) imediatamente antes de executar uma nova ordem, funcionando como lock otimista.

---

### Melhorias de robustez

#### Sem retry na busca de preço atual

Em `monitor_positions()`, se `get_current_price()` retornar `None` (timeout ou erro da Binance), o símbolo é simplesmente pulado. Isso acontece justamente em momentos de alta volatilidade — exatamente quando SL/TP são mais críticos.

**Melhoria:** retry de 2-3 tentativas com intervalo curto antes de pular o símbolo, com notificação Discord de alerta.

---

#### Sem alerta de proximidade do limite diário

O bot notifica apenas quando o limite diário é atingido. Quando está em 80% do limite, nenhum alerta é enviado — o operador não tem chance de reagir antes do bloqueio.

**Melhoria:** enviar notificação Discord quando `daily_loss_usdt` ultrapassar 80% do `MAX_DAILY_LOSS_USDT`.

---

### Melhorias de observabilidade

#### LLM log sem rastreio no trade de fechamento

O `llm_log_id` é salvo no trade de abertura (BUY), mas quando a posição é fechada por SL/TP, o trade de fechamento é salvo sem nenhuma referência ao log LLM que originou a posição. Fica impossível rastrear qual análise gerou um trade específico que teve perda.

**Melhoria:** salvar o `llm_log_id` original dentro do objeto `Position` e repassá-lo ao salvar o trade de fechamento.

---

#### `session_stats` não reflete sessões anteriores

O resumo diário usa `session_stats`, que começa zerado a cada execução. Em Fargate, cada container tem sua própria sessão — o win rate e PnL exibidos no log representam apenas aquele ciclo, não o dia inteiro.

**Melhoria:** calcular `session_stats` do dia a partir dos trades do Supabase na inicialização, ou remover a métrica de sessão dos logs e usar sempre os dados do banco.

---

### Tabela de prioridades

| #   | Problema                                   | Impacto | Tipo            |
| --- | ------------------------------------------ | ------- | --------------- |
| 1   | `db_id` não restaurado → posições fantasma | Crítico | Bug             |
| 2   | `daily_loss_usdt` zerado a cada container  | Alto    | Bug             |
| 3   | SELL sem PnL real registrado               | Alto    | Bug             |
| 4   | Ordens duplicadas entre containers         | Alto    | Bug             |
| 5   | Sem retry no preço atual                   | Médio   | Robustez        |
| 6   | Sem alerta de 80% do limite diário         | Médio   | Robustez        |
| 7   | LLM log sem rastreio no fechamento         | Médio   | Observabilidade |
| 8   | `session_stats` sem contexto real          | Baixo   | Observabilidade |

### Arquivos impactados por esses bugs

| Arquivo                        | O que muda                                                                                                               |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| `infra/supabase/repository.py` | `load_positions()` popula `db_id`; nova função `get_daily_loss_since()`                                                  |
| `application/risk_manager.py`  | Inicialização calcula `daily_loss_usdt` do banco; SELL com PnL real; lock otimista no BUY; retry no preço; alerta de 80% |
| `domain/models.py`             | `Position` recebe campo `llm_log_id`                                                                                     |

---

## Alterações no Banco de Dados

Todas as mudanças necessárias no schema do Supabase para suportar os novos fluxos.

---

### `open_positions` — novos campos

```sql
alter table public.open_positions
  add column tp_hold_count integer          not null default 0,
  add column original_sl   double precision not null default 0,
  add column original_tp   double precision not null default 0,
  add column llm_log_id    uuid             null references public.llm_logs(id);
```

| Campo | Tipo | Motivo |
|-------|------|--------|
| `tp_hold_count` | `integer` | Contador de tentativas de hold no TP progressivo — define qual threshold de confiança aplicar |
| `original_sl` | `double precision` | SL original antes de qualquer ajuste progressivo — referência para auditoria |
| `original_tp` | `double precision` | TP original antes de qualquer extensão — referência para auditoria |
| `llm_log_id` | `uuid` | Vincula a posição ao log LLM que originou a compra |

---

### `trades` — novo campo

```sql
alter table public.trades
  add column exit_llm_log_id uuid null references public.llm_logs(id);
```

| Campo | Tipo | Motivo |
|-------|------|--------|
| `exit_llm_log_id` | `uuid` | Log LLM que originou o fechamento da posição (TP com hold, early exit, sell estratégico). Fica `null` em fechamentos por SL — indicador implícito de execução automática sem LLM |

> O campo `llm_log_id` já existente continua referenciando o log de **abertura** (BUY). O novo `exit_llm_log_id` referencia o log de **fechamento**.

---

### `llm_logs` — novos campos

```sql
alter table public.llm_logs
  add column process     text not null default '',
  add column tool_called text null,
  add column position_id uuid null references public.open_positions(id);
```

| Campo | Tipo | Motivo |
|-------|------|--------|
| `process` | `text` | Identifica qual processo gerou o log: `bot` (ciclo de análise) ou `monitor` (check_sl_tp) |
| `tool_called` | `text` | Tool que o LLM chamou naquela análise: `open_position`, `sell_position`, `hold_position`, `early_exit`, ou `null` se não chamou nenhuma |
| `position_id` | `uuid` | Quando o LLM foi consultado sobre uma posição específica (TP, early exit), vincula o log à posição analisada |

---

### Nova tabela — `daily_loss`

```sql
create table public.daily_loss (
  id         uuid not null default gen_random_uuid(),
  date       date not null unique,
  loss       double precision not null default 0,
  updated_at timestamp with time zone not null default now(),
  constraint daily_loss_pkey primary key (id)
);
```

**Motivo:** resolve o bug crítico do `daily_loss_usdt` zerado a cada container no Fargate. Na inicialização, o bot busca o registro do dia atual e restaura o valor acumulado. Atualizado a cada trade com perda.

---

### Resumo de todas as alterações

| Tabela | Operação | Campo | Motivo |
|--------|----------|-------|--------|
| `open_positions` | add column | `tp_hold_count` | Contador do hold progressivo |
| `open_positions` | add column | `original_sl` | SL original antes de subir |
| `open_positions` | add column | `original_tp` | TP original antes de subir |
| `open_positions` | add column | `llm_log_id` | Qual análise originou a compra |
| `trades` | add column | `exit_llm_log_id` | Qual análise originou o fechamento |
| `llm_logs` | add column | `process` | Qual processo gerou o log |
| `llm_logs` | add column | `tool_called` | Qual tool o LLM chamou |
| `llm_logs` | add column | `position_id` | Posição analisada (quando aplicável) |
| `daily_loss` | new table | — | Persistir perda diária entre containers |

---

## Resumo Visual

```
┌─────────────────────────────────────────────────────────────┐
│  check_sl_tp.py — a cada 5 min                              │
│                                                             │
│  Para cada posição aberta:                                  │
│  ├── SL atingido? → vende direto (sem LLM) ✓               │
│  ├── 80% do SL? → LLM: early_exit(id, conf)?               │
│  │   ├── conf >= mínimo → vende antecipado                  │
│  │   └── conf < mínimo → mantém, SL protege                 │
│  └── TP atingido? → LLM: sell ou hold?                      │
│      ├── sell_position(id, conf) → vende                    │
│      └── hold_position(id, conf)?                           │
│          ├── conf >= threshold → SL sobe, TP sobe ×1.5      │
│          └── conf < threshold → vende                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  bot.py — a cada 15 min                                     │
│                                                             │
│  Para cada símbolo:                                         │
│  ├── Busca mercado (candles, indicadores, F&G, ranges)      │
│  ├── Monta contexto rico para o LLM                         │
│  └── LLM analisa e decide:                                  │
│      ├── open_position(symbol, conf) → valida regras → BUY  │
│      │   ├── conf >= MIN_CONFIDENCE                         │
│      │   ├── posições < MAX_POSITIONS_PER_SYMBOL            │
│      │   ├── distância mínima respeitada                    │
│      │   ├── saldo USDT suficiente                          │
│      │   └── limite diário não atingido                     │
│      ├── sell_position(id, conf) → vende posição específica │
│      └── (sem tool) → nenhuma ação                          │
└─────────────────────────────────────────────────────────────┘
```
