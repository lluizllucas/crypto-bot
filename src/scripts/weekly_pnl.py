"""
Relatorio semanal de P&L — roda 1x/semana via EventBridge + ECS Fargate.
Consolida todas as operacoes de venda dos ultimos 7 dias por simbolo.
"""

import sys
import os

from datetime import datetime, timedelta, timezone

from src.domain.entities.trade import Trade
from src.infra.persistence.repository import get_trades_since

from src.infra.logging.setup import setup_logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

log = setup_logging()


def run():
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    trades = get_trades_since(week_start.strftime("%Y-%m-%dT%H:%M:%S+00:00"))

    log.info("=" * 55)
    log.info("RELATORIO SEMANAL DE P&L")
    log.info(
        f"  Periodo: {week_start.strftime('%Y-%m-%d')} a {now.strftime('%Y-%m-%d')}")

    if not trades:
        log.info("  Nenhuma operacao de venda na semana.")
        log.info("=" * 55)
        return

    by_symbol: dict[str, list[Trade]] = {}
    for t in trades:
        by_symbol.setdefault(t.symbol, []).append(t)

    total_pnl_global = 0.0

    for sym, sym_trades in by_symbol.items():
        wins = [t for t in sym_trades if t.pnl > 0]
        losses = [t for t in sym_trades if t.pnl <= 0]
        total_pnl = sum(t.pnl for t in sym_trades)
        total_pnl_global += total_pnl
        wr = len(wins) / len(sym_trades) * 100 if sym_trades else 0

        log.info(f"\n  [{sym}]")
        log.info(
            f"    Operacoes:        {len(sym_trades)} ({len(wins)} ganhos / {len(losses)} perdas)")
        log.info(f"    Win rate:         {wr:.1f}%")
        log.info(f"    PnL total:        ${total_pnl:+.4f}")

        if wins:
            best = max(wins, key=lambda t: t.pnl)
            created = best.created_at.isoformat(
            )[:10] if best.created_at else ""
            log.info(
                f"    Melhor trade:     ${best.pnl:+.4f} ({best.action} @ {created})")
        if losses:
            worst = min(losses, key=lambda t: t.pnl)
            created = worst.created_at.isoformat(
            )[:10] if worst.created_at else ""
            log.info(
                f"    Pior trade:       ${worst.pnl:+.4f} ({worst.action} @ {created})")

        log.info(f"    Detalhe:")
        for t in sym_trades:
            created = t.created_at.isoformat()[:16] if t.created_at else ""
            log.info(
                f"      {created} | {t.action:<12} | "
                f"entrada: ${t.entry_price:.4f} -> saida: ${t.exit_price:.4f} | "
                f"qty: {t.qty} | PnL: ${t.pnl:+.4f}"
            )

    log.info(f"\n  PnL GLOBAL DA SEMANA: ${total_pnl_global:+.4f}")
    log.info("=" * 55)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log.exception("Erro no relatorio semanal")
        sys.exit(1)

    sys.exit(0)
