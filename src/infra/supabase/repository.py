"""
Operacoes de banco via Supabase.
Responsavel por persistir e carregar posicoes abertas e historico de trades.
"""

from src.domain.models import Position
from src.config import SUPABASE_URL, SUPABASE_KEY
from supabase import create_client, Client
import os
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv

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
                entry_price=row["entry_price"],
                qty=row["qty"],
                sl=row["sl"],
                tp=row["tp"],
                ts=datetime.fromisoformat(row["created_at"]),
            ))
        log.info(
            f"Posicoes carregadas do banco: {sum(len(v) for v in result.values())} lote(s)")
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
        row = _client.table("open_positions").insert({
            "symbol":      symbol,
            "entry_price": position.entry_price,
            "qty":         position.qty,
            "sl":          position.sl,
            "tp":          position.tp,
        }).execute().data
        return row[0]["id"] if row else None
    except Exception as e:
        log.error(f"Erro ao salvar posicao no banco ({symbol}): {e}")
        return None


def delete_position(position_id: str):
    """Remove uma posicao fechada do banco pelo id."""
    try:
        _client.table("open_positions").delete().eq(
            "id", position_id).execute()
    except Exception as e:
        log.error(f"Erro ao remover posicao do banco (id={position_id}): {e}")


def delete_all_positions(symbol: str):
    """Remove todas as posicoes de um simbolo (usado no SELL total)."""
    try:
        _client.table("open_positions").delete().eq("symbol", symbol).execute()
    except Exception as e:
        log.error(f"Erro ao remover posicoes do banco ({symbol}): {e}")


# ── Historico de trades ───────────────────────────────────────────────────────

def get_trades_since(since_iso: str) -> list[dict]:
    """
    Retorna todos os trades fechados (STOP-LOSS, TAKE-PROFIT, SELL) a partir de since_iso.
    since_iso: string ISO 8601, ex: '2024-01-01T00:00:00+00:00'
    """
    try:
        rows = (
            _client.table("trades")
            .select("symbol, action, entry_price, exit_price, qty, pnl, reason, created_at")
            .in_("action", ["STOP-LOSS", "TAKE-PROFIT", "SELL"])
            .gte("created_at", since_iso)
            .order("created_at")
            .execute()
            .data
        )
        return rows
    except Exception as e:
        log.error(f"Erro ao buscar trades desde {since_iso}: {e}")
        return []


# ── LLM Logs ─────────────────────────────────────────────────────────────────

def save_llm_log(symbol: str, context: dict, response: dict) -> str | None:
    """
    Persiste o contexto e a resposta da LLM para cada ciclo de analise.
    Retorna o id gerado para ser referenciado no trade.
    """
    try:
        row = _client.table("llm_logs").insert({
            "symbol":   symbol,
            "context":  context,
            "response": response,
        }).execute().data
        return row[0]["id"] if row else None
    except Exception as e:
        log.error(f"Erro ao salvar llm_log ({symbol}): {e}")
        return None


def save_trade(
    symbol: str,
    action: str,
    confidence: float,
    entry_price: float,
    exit_price: float,
    qty: float,
    sl: float,
    tp: float,
    pnl: float,
    reason: str,
    llm_log_id: str | None = None,
):
    """Persiste um trade no historico, referenciando o llm_log correspondente."""
    try:
        payload = {
            "symbol":       symbol,
            "action":       action,
            "confidence":   confidence,
            "entry_price":  entry_price,
            "exit_price":   exit_price,
            "qty":          qty,
            "sl":           sl,
            "tp":           tp,
            "pnl":          pnl,
            "reason":       reason,
        }
        if llm_log_id:
            payload["llm_log_id"] = llm_log_id

        _client.table("trades").insert(payload).execute()
    except Exception as e:
        log.error(f"Erro ao salvar trade no banco ({symbol}): {e}")
