"""
Auditoria de tools de execucao — replica o despacho exato dos agentes LLM
(bot_agent, tp_agent, early_exit_agent) com args mockados.

Binance mockada | Discord silenciado | banco real

Fluxo:
  1. Cria 3 posicoes via on_action do bot_agent (open_position)
  2. Posicao 0 → on_action do bot_agent    (sell_position)
  3. Posicao 1 → on_action do tp_agent     (hold_position)
  4. Posicao 2 → on_action do early_exit   (early_exit)
  5. Limpa posicoes restantes do banco
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.config import SYMBOLS
from src.infra.logging.setup import setup_logging
from src.infra.persistence.repository import get_positions_by_symbol, delete_all_positions, get_position_by_id

from src.infra.agents.tools.execution.execute_buy import tool_execute_buy
from src.infra.agents.tools.execution.execute_sell import tool_execute_sell
from src.infra.agents.tools.execution.execute_hold import tool_hold_position
from src.infra.agents.tools.execution.execute_early_exit import tool_early_exit

log = setup_logging()

SYMBOL   = SYMBOLS[0]
PRICE    = 95_000.0

# ──────────────────────────────────────────────
# on_action copiados dos agentes reais
# ──────────────────────────────────────────────

def _on_action_bot(name: str, args: dict, price: float) -> bool:
    """Replica exata de bot_agent.on_action."""
    if name == "open_position":
        return tool_execute_buy(
            symbol=     args.get("symbol", ""),
            confidence= float(args.get("confidence", 0)),
            sl_pct=     float(args.get("sl_percentage", 2.5)),
            tp_pct=     float(args.get("tp_percentage", 5.0)),
            reason=     args.get("reason", ""),
            last_price= price,
        )
    if name == "sell_position":
        return tool_execute_sell(
            symbol=        args.get("symbol", ""),
            position_id=   args.get("position_id", ""),
            confidence=    float(args.get("confidence", 0)),
            reason=        args.get("reason", "SELL estrategico"),
            current_price= price,
        )
    return False


def _on_action_tp(name: str, args: dict, pos, price: float) -> bool:
    """Replica exata de tp_agent.on_action."""
    if args.get("position_id") != pos.db_id:
        return False

    confidence = float(args.get("confidence", 0))

    if name == "sell_position":
        return tool_execute_sell(SYMBOL, pos.db_id, confidence, "TAKE-PROFIT", price)

    if name == "hold_position":
        return tool_hold_position(SYMBOL, pos.db_id, confidence, price)

    return False


def _on_action_early_exit(name: str, args: dict, pos, price: float) -> bool:
    """Replica exata de early_exit_agent.on_action."""
    if args.get("position_id") != pos.db_id:
        return False

    if name == "early_exit":
        return tool_early_exit(SYMBOL, pos.db_id, float(args.get("confidence", 0)), price, None)

    return False


# ──────────────────────────────────────────────
# patches — Binance mockada, Discord silenciado
# ──────────────────────────────────────────────

PATCHES = [
    patch(
        "src.infra.agents.tools.execution.execute_buy.order_market_buy",
        return_value={"orderId": "AUDIT-BUY-001", "status": "FILLED"},
    ),
    patch(
        "src.infra.agents.tools.execution.execute_sell.order_market_sell",
        return_value={"orderId": "AUDIT-SELL-001", "status": "FILLED"},
    ),
    patch(
        "src.infra.agents.tools.execution.execute_buy.get_balance",
        return_value=500.0,
    ),
    patch(
        "src.infra.agents.tools.execution.execute_buy.get_symbol_filters",
        return_value=(0.00001, 0.00001, 5, 5.0),
    ),
    patch(
        "src.infra.agents.tools.execution.execute_sell.get_symbol_filters",
        return_value=(0.00001, 0.00001, 5, 5.0),
    ),
    patch("src.infra.agents.tools.execution.execute_buy.discord_notify"),
    patch("src.infra.agents.tools.execution.execute_sell.discord_notify"),
    patch("src.infra.agents.tools.execution.execute_hold.discord_notify"),
    patch(
        "src.infra.agents.tools.execution.execute_buy.check_daily_loss_limit",
        return_value=False,
    ),
]


# ──────────────────────────────────────────────
# helpers de log
# ──────────────────────────────────────────────

def _section(title: str):
    log.info(f"\n{'=' * 55}")
    log.info(f"  {title}")
    log.info("=" * 55)


def _result(ok: bool, label: str, detail: str = ""):
    status = "OK    " if ok else "FALHOU"
    suffix = f" | {detail}" if detail else ""
    (log.info if ok else log.error)(f"  [{status}] {label}{suffix}")


# ──────────────────────────────────────────────
# etapas
# ──────────────────────────────────────────────

def step_buy_three() -> list:
    _section("ETAPA 1 — open_position x3  (bot_agent)")

    compras = [
        # (price_offset, sl_pct, tp_pct, reason)
        (0.0,   2.0, 4.0, "auditoria: posicao A — sera SELL"),
        (1.0,   2.0, 4.0, "auditoria: posicao B — sera HOLD"),
        (-1.0,  2.0, 4.0, "auditoria: posicao C — sera EARLY EXIT"),
    ]

    for offset, sl, tp, reason in compras:
        price = PRICE + offset
        ok = _on_action_bot("open_position", {
            "symbol":        SYMBOL,
            "confidence":    0.90,
            "sl_percentage": sl,
            "tp_percentage": tp,
            "reason":        reason,
        }, price)
        _result(ok, "open_position", reason)

    positions = get_positions_by_symbol(SYMBOL)
    log.info(f"\n  Posicoes criadas: {len(positions)}")
    for pos in positions:
        log.info(
            f"    id={pos.db_id}  entrada=${pos.entry_price:.2f}"
            f"  sl=${pos.sl:.2f}  tp=${pos.tp:.2f}"
        )
    return positions


def step_sell(pos):
    _section("ETAPA 2 — sell_position  (bot_agent)")

    exit_price = pos.entry_price * 1.03
    ok = _on_action_bot("sell_position", {
        "symbol":      SYMBOL,
        "position_id": pos.db_id,
        "confidence":  0.85,
        "reason":      "SELL estrategico",
    }, exit_price)
    _result(ok, "sell_position", f"saida @ ${exit_price:.2f} (+3%)")


def step_hold(pos):
    _section("ETAPA 3 — hold_position  (tp_agent)")

    ok = _on_action_tp("hold_position", {
        "position_id": pos.db_id,
        "confidence":  0.90,
    }, pos, pos.tp)
    _result(ok, "hold_position", f"preco no TP=${pos.tp:.2f}  conf=0.90")

    updated = get_position_by_id(pos.db_id)
    if updated:
        log.info(
            f"  Estado apos hold: sl=${updated.sl:.2f}  tp=${updated.tp:.2f}"
            f"  hold_count={updated.tp_hold_count}"
        )


def step_early_exit(pos):
    _section("ETAPA 4 — early_exit  (early_exit_agent)")

    exit_price = pos.entry_price * 0.985
    ok = _on_action_early_exit("early_exit", {
        "position_id": pos.db_id,
        "confidence":  0.80,
    }, pos, exit_price)
    _result(ok, "early_exit", f"saida @ ${exit_price:.2f} (-1.5%)")


def cleanup():
    _section("LIMPEZA")
    positions = get_positions_by_symbol(SYMBOL)
    if positions:
        delete_all_positions(SYMBOL)
        log.info(f"  {len(positions)} posicao(oes) removida(s)")
    else:
        log.info("  Banco limpo")


# ──────────────────────────────────────────────
# main
# ──────────────────────────────────────────────

def run():
    log.info("=" * 55)
    log.info(f"AUDITORIA EXECUTION TOOLS — {SYMBOL}")
    log.info("Binance mockada | Discord silenciado | banco real")
    log.info("=" * 55)

    for p in PATCHES:
        p.start()

    try:
        positions = step_buy_three()

        if len(positions) < 3:
            log.error(f"Esperava 3 posicoes, banco retornou {len(positions)} — abortando")
            return

        step_sell(positions[0])
        step_hold(positions[1])
        step_early_exit(positions[2])

    finally:
        for p in PATCHES:
            try:
                p.stop()
            except RuntimeError:
                pass
        cleanup()

    log.info("\n" + "=" * 55)
    log.info("Auditoria concluida.")
    log.info("=" * 55)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log.exception("Erro na auditoria de execution tools")
        sys.exit(1)

    sys.exit(0)
