"""
Operacoes de banco via Supabase.
Responsavel por persistir e carregar posicoes abertas, historico de trades,
logs LLM e perda diaria acumulada.
"""

import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client, Client

from src.config import SUPABASE_URL, SUPABASE_KEY
from src.domain.entities.position import Position

load_dotenv()

log = logging.getLogger(__name__)

_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Posicoes abertas ──────────────────────────────────────────────────────────

def load_positions() -> dict[str, list[Position]]:
    """
    Carrega todas as posicoes abertas do banco ao iniciar o bot.
    Retorna { "BTCUSDT": [Position, ...] }
    """
    try:
        rows = _client.table("open_positions").select("*").execute().data
        result: dict[str, list[Position]] = {}

        for row in rows:
            symbol = row["symbol"]
            if symbol not in result:
                result[symbol] = []

            result[symbol].append(Position(
                entry_price=  row["entry_price"],
                qty=          row["qty"],
                sl=           row["sl"],
                tp=           row["tp"],
                ts=           datetime.fromisoformat(row["created_at"]),
                db_id=        row["id"],
                llm_log_id=   row.get("llm_log_id") or "",
                original_sl=  row.get("original_sl") or row["sl"],
                original_tp=  row.get("original_tp") or row["tp"],
                tp_hold_count=row.get("tp_hold_count") or 0,
            ))

        log.info(f"Posicoes carregadas do banco: {sum(len(v) for v in result.values())} lote(s)")
        return result

    except Exception as e:
        log.error(f"Erro ao carregar posicoes do banco: {e}")
        return {}


def save_position(symbol: str, position: Position) -> str | None:
    """
    Salva uma posicao aberta no banco.
    Retorna o id gerado para uso posterior na remocao.
    """
    try:
        payload = {
            "symbol":       symbol,
            "entry_price":  position.entry_price,
            "qty":          position.qty,
            "sl":           position.sl,
            "tp":           position.tp,
            "original_sl":  position.original_sl,
            "original_tp":  position.original_tp,
            "tp_hold_count": position.tp_hold_count,
        }
        if position.llm_log_id:
            payload["llm_log_id"] = position.llm_log_id

        row = _client.table("open_positions").insert(payload).execute().data
        return row[0]["id"] if row else None

    except Exception as e:
        log.error(f"Erro ao salvar posicao no banco ({symbol}): {e}")
        return None


def update_position(position: Position):
    """Atualiza sl, tp e tp_hold_count de uma posicao existente no banco."""
    if not position.db_id:
        return
    try:
        _client.table("open_positions").update({
            "sl":            position.sl,
            "tp":            position.tp,
            "tp_hold_count": position.tp_hold_count,
        }).eq("id", position.db_id).execute()
    except Exception as e:
        log.error(f"Erro ao atualizar posicao no banco (id={position.db_id}): {e}")


def delete_position(position_id: str):
    """Remove uma posicao fechada do banco pelo id."""
    try:
        _client.table("open_positions").delete().eq("id", position_id).execute()
    except Exception as e:
        log.error(f"Erro ao remover posicao do banco (id={position_id}): {e}")


def delete_all_positions(symbol: str):
    """Remove todas as posicoes de um simbolo (usado no SELL total)."""
    try:
        _client.table("open_positions").delete().eq("symbol", symbol).execute()
    except Exception as e:
        log.error(f"Erro ao remover posicoes do banco ({symbol}): {e}")


def count_positions_in_db(symbol: str) -> int:
    """Conta posicoes abertas no banco (lock otimista para evitar duplicatas entre containers)."""
    try:
        rows = (
            _client.table("open_positions")
            .select("id", count="exact")
            .eq("symbol", symbol)
            .execute()
        )
        return rows.count or 0
    except Exception as e:
        log.error(f"Erro ao contar posicoes no banco ({symbol}): {e}")
        return 0


# ── Historico de trades ───────────────────────────────────────────────────────

def get_trades_since(since_iso: str) -> list[dict]:
    """
    Retorna todos os trades fechados a partir de since_iso.
    since_iso: string ISO 8601, ex: '2024-01-01T00:00:00+00:00'
    """
    try:
        rows = (
            _client.table("trades")
            .select("symbol, action, entry_price, exit_price, qty, pnl, reason, created_at")
            .in_("action", ["STOP-LOSS", "TAKE-PROFIT", "SELL", "EARLY-EXIT"])
            .gte("created_at", since_iso)
            .order("created_at")
            .execute()
            .data
        )
        return rows
    except Exception as e:
        log.error(f"Erro ao buscar trades desde {since_iso}: {e}")
        return []


def save_trade(
    symbol:          str,
    action:          str,
    confidence:      float,
    entry_price:     float,
    exit_price:      float,
    qty:             float,
    sl:              float,
    tp:              float,
    pnl:             float,
    reason:          str,
    llm_log_id:      str | None = None,
    exit_llm_log_id: str | None = None,
):
    """Persiste um trade no historico referenciando os logs LLM de abertura e fechamento."""
    try:
        payload = {
            "symbol":      symbol,
            "action":      action,
            "confidence":  confidence,
            "entry_price": entry_price,
            "exit_price":  exit_price,
            "qty":         qty,
            "sl":          sl,
            "tp":          tp,
            "pnl":         pnl,
            "reason":      reason,
        }
        if llm_log_id:
            payload["llm_log_id"] = llm_log_id
        if exit_llm_log_id:
            payload["exit_llm_log_id"] = exit_llm_log_id

        _client.table("trades").insert(payload).execute()

    except Exception as e:
        log.error(f"Erro ao salvar trade no banco ({symbol}): {e}")


# ── LLM Logs ─────────────────────────────────────────────────────────────────

def save_llm_log(
    symbol:      str,
    context:     dict,
    response:    dict,
    process:     str = "",
    tool_called: str | None = None,
    position_id: str | None = None,
) -> str | None:
    """
    Persiste o contexto e a resposta da LLM para cada ciclo de analise.
    Retorna o id gerado para ser referenciado no trade.
    """
    try:
        payload = {
            "symbol":   symbol,
            "context":  context,
            "response": response,
            "process":  process,
        }

        if tool_called:
            payload["tool_called"] = tool_called

        if position_id:
            payload["position_id"] = position_id

        row = _client.table("llm_logs").insert(payload).execute().data
        
        return row[0]["id"] if row else None

    except Exception as e:
        log.error(f"Erro ao salvar llm_log ({symbol}): {e}")
        return None


# ── Historico para contexto do LLM ───────────────────────────────────────────

def get_recent_llm_decisions(symbol: str, limit: int = 5) -> list[dict]:
    """
    Retorna as ultimas N decisoes do LLM para o simbolo (tool_called + reason + timestamp).
    Usado para passar memoria de analises anteriores ao LLM.
    """
    try:
        rows = (
            _client.table("llm_logs")
            .select("tool_called, response, created_at, process")
            .eq("symbol", symbol)
            .eq("process", "bot")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )
        result = []
        for row in reversed(rows):
            actions  = row.get("response", {}).get("actions", [])
            reason   = actions[0]["args"].get("reason", "") if actions else ""
            result.append({
                "timestamp":   row["created_at"][:16],
                "tool_called": row.get("tool_called") or "none",
                "reason":      reason,
            })
        return result
    except Exception as e:
        log.error(f"Erro ao buscar decisoes recentes do LLM ({symbol}): {e}")
        return []


def get_recent_performance(symbol: str, limit: int = 10) -> dict:
    """
    Retorna resumo de performance das ultimas N trades fechadas do simbolo.
    Usado para o LLM calibrar confianca com base no proprio historico recente.
    """
    try:
        rows = (
            _client.table("trades")
            .select("action, pnl, confidence, created_at")
            .eq("symbol", symbol)
            .in_("action", ["STOP-LOSS", "TAKE-PROFIT", "SELL", "EARLY-EXIT"])
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )
        if not rows:
            return {"trades": 0}

        wins   = [r for r in rows if r["pnl"] > 0]
        losses = [r for r in rows if r["pnl"] <= 0]
        pnls   = [r["pnl"] for r in rows]

        return {
            "trades":    len(rows),
            "wins":      len(wins),
            "losses":    len(losses),
            "win_rate":  round(len(wins) / len(rows) * 100, 1),
            "pnl_total": round(sum(pnls), 4),
            "pnl_avg":   round(sum(pnls) / len(pnls), 4),
            "best":      round(max(pnls), 4),
            "worst":     round(min(pnls), 4),
        }
    except Exception as e:
        log.error(f"Erro ao buscar performance recente ({symbol}): {e}")
        return {"trades": 0}


# ── Perda diaria ──────────────────────────────────────────────────────────────

def get_daily_loss(date_str: str) -> float:
    """
    Retorna a perda acumulada no dia (date_str formato YYYY-MM-DD).
    Retorna 0.0 se nao houver registro.
    """
    try:
        rows = (
            _client.table("daily_loss")
            .select("loss")
            .eq("date", date_str)
            .execute()
            .data
        )
        return float(rows[0]["loss"]) if rows else 0.0
    except Exception as e:
        log.error(f"Erro ao buscar daily_loss ({date_str}): {e}")
        return 0.0


def upsert_daily_loss(date_str: str, loss: float):
    """
    Cria ou atualiza o registro de perda do dia.
    date_str formato YYYY-MM-DD.
    """
    try:
        _client.table("daily_loss").upsert({
            "date":       date_str,
            "loss":       loss,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="date").execute()
    except Exception as e:
        log.error(f"Erro ao salvar daily_loss ({date_str}): {e}")
