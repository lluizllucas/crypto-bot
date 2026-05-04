-- =============================================================
-- Migration: atualiza schema para arquitetura de agentes LLM
-- Idempotente: seguro para rodar mais de uma vez
-- Rodar no SQL Editor do Supabase
-- =============================================================


-- -------------------------------------------------------------
-- open_positions: campos de trailing stop e referencia ao log
-- -------------------------------------------------------------

ALTER TABLE open_positions
    ADD COLUMN IF NOT EXISTS original_sl    double precision,
    ADD COLUMN IF NOT EXISTS original_tp    double precision,
    ADD COLUMN IF NOT EXISTS tp_hold_count  integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS llm_log_id     text;


-- -------------------------------------------------------------
-- trades: referencia ao log do agente que fechou a posicao
-- -------------------------------------------------------------

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS exit_llm_log_id text;


-- -------------------------------------------------------------
-- llm_logs: contexto de execucao e rastreio por posicao
-- -------------------------------------------------------------

ALTER TABLE llm_logs
    ADD COLUMN IF NOT EXISTS tool_called  text,
    ADD COLUMN IF NOT EXISTS process      text DEFAULT '',
    ADD COLUMN IF NOT EXISTS position_id  text;


-- -------------------------------------------------------------
-- daily_loss: controle de perda diaria por data
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS daily_loss (
    date        text        PRIMARY KEY,
    loss        numeric     NOT NULL DEFAULT 0,
    updated_at  timestamptz
);
