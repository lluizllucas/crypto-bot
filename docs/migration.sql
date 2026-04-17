-- =============================================================
-- CryptoBot — Migration
-- Aplicar no Supabase SQL Editor
-- Ordem importa: llm_logs deve existir antes das foreign keys
-- =============================================================


-- -------------------------------------------------------------
-- 1. llm_logs — novos campos
-- -------------------------------------------------------------

alter table public.llm_logs
  add column if not exists process     text null,
  add column if not exists tool_called text null,
  add column if not exists position_id uuid null;

comment on column public.llm_logs.process     is 'Processo que gerou o log: bot (ciclo de analise) ou monitor (check_sl_tp)';
comment on column public.llm_logs.tool_called is 'Tool chamada pelo LLM: open_position, sell_position, hold_position, early_exit, ou null se nenhuma';
comment on column public.llm_logs.position_id is 'Posicao analisada quando o LLM foi consultado sobre um lote especifico (TP, early exit)';


-- -------------------------------------------------------------
-- 2. open_positions — novos campos
-- -------------------------------------------------------------

alter table public.open_positions
  add column if not exists tp_hold_count integer          not null default 0,
  add column if not exists original_sl   double precision not null default 0,
  add column if not exists original_tp   double precision not null default 0,
  add column if not exists llm_log_id    uuid             null references public.llm_logs(id);

comment on column public.open_positions.tp_hold_count is 'Numero de vezes que o LLM segurou o TP — define o threshold de confianca progressivo';
comment on column public.open_positions.original_sl   is 'SL original no momento da abertura, antes de qualquer ajuste progressivo';
comment on column public.open_positions.original_tp   is 'TP original no momento da abertura, antes de qualquer extensao';
comment on column public.open_positions.llm_log_id    is 'Log LLM que originou a compra desta posicao';


-- -------------------------------------------------------------
-- 3. llm_logs — foreign key para open_positions (apos criacao)
-- -------------------------------------------------------------

alter table public.llm_logs
  add constraint if not exists llm_logs_position_id_fkey
    foreign key (position_id) references public.open_positions(id)
    on delete set null;


-- -------------------------------------------------------------
-- 4. trades — novo campo de log de fechamento
-- -------------------------------------------------------------

alter table public.trades
  add column if not exists exit_llm_log_id uuid null references public.llm_logs(id);

comment on column public.trades.llm_log_id      is 'Log LLM que originou a abertura do trade (BUY)';
comment on column public.trades.exit_llm_log_id is 'Log LLM que originou o fechamento do trade (SELL, TP, early exit). Null indica fechamento automatico por SL sem LLM';


-- -------------------------------------------------------------
-- 5. Nova tabela: daily_loss
-- Persiste a perda acumulada no dia entre containers Fargate
-- -------------------------------------------------------------

create table if not exists public.daily_loss (
  id         uuid                     not null default gen_random_uuid(),
  date       date                     not null unique,
  loss       double precision         not null default 0,
  updated_at timestamp with time zone not null default now(),
  constraint daily_loss_pkey primary key (id)
);

comment on table  public.daily_loss            is 'Perda acumulada por dia — restaurada na inicializacao do bot para garantir limite diario entre containers';
comment on column public.daily_loss.date       is 'Data UTC do registro (unique — um registro por dia)';
comment on column public.daily_loss.loss       is 'Total de perda em USDT acumulada no dia';
comment on column public.daily_loss.updated_at is 'Ultima atualizacao — atualizado a cada trade com perda';
