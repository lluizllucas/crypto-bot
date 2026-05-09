"""
Relatorio semanal de P&L — roda 1x/semana via EventBridge + ECS Fargate.
Consolida todas as operacoes de venda dos ultimos 7 dias por simbolo.
"""

import sys
import os

from datetime import datetime, timedelta, timezone

from src.domain.entities.trade import Trade
from src.infra.persistence.repository import get_trades_since, load_positions, get_daily_loss
from src.infra.clients.discord.client import discord_notify
from src.infra.clients.binance.client import get_balance

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

    _send_weekly_discord(trades, by_symbol, total_pnl_global, now, week_start)


def _send_weekly_discord(trades, by_symbol, total_pnl_global, now, week_start):
    usdt         = get_balance("USDT")
    open_positions = load_positions()
    total_lotes  = sum(len(v) for v in open_positions.values())

    lucro_total  = sum(t.pnl for t in trades if t.pnl > 0)
    perda_total  = sum(t.pnl for t in trades if t.pnl < 0)
    total_ops    = len(trades)
    wins         = [t for t in trades if t.pnl > 0]
    wr           = len(wins) / total_ops * 100 if total_ops > 0 else 0

    lines = []

    lines.append(f"**Periodo:** {week_start.strftime('%Y-%m-%d')} a {now.strftime('%Y-%m-%d')}")
    lines.append(f"**Saldo USDT atual:** ${usdt:.2f}")
    lines.append(f"**Operacoes:** {total_ops} — {len(wins)}W / {total_ops - len(wins)}L — Win rate: {wr:.1f}%")
    lines.append(f"**Lucro bruto:** ${lucro_total:+.4f}   |   **Perda bruta:** ${perda_total:+.4f}")
    lines.append(f"**PnL liquido da semana:** ${total_pnl_global:+.4f}")

    for sym, sym_trades in by_symbol.items():
        sym_wins   = [t for t in sym_trades if t.pnl > 0]
        sym_losses = [t for t in sym_trades if t.pnl <= 0]
        sym_pnl    = sum(t.pnl for t in sym_trades)
        sym_wr     = len(sym_wins) / len(sym_trades) * 100 if sym_trades else 0

        lines.append(
            f"\n**{sym}** — {len(sym_trades)} ops | {len(sym_wins)}W/{len(sym_losses)}L | "
            f"WR {sym_wr:.0f}% | PnL ${sym_pnl:+.4f}"
        )

        for t in sym_trades:
            hora  = t.created_at.strftime("%m/%d %H:%M") if t.created_at else "??/??"
            emoji = "✓" if t.pnl >= 0 else "✗"
            lines.append(
                f"  {emoji} `{hora}` {t.action} — "
                f"${t.entry_price:.4f}→${t.exit_price:.4f} | ${t.pnl:+.4f}"
            )

    lines.append(f"\n**Posicoes abertas:** {total_lotes} lote(s) em {len(open_positions)} par(es)")

    for symbol, positions in open_positions.items():
        for pos in positions:
            try:
                from src.application.services.market_data_service import get_market_data
                data = get_market_data(symbol)
                preco_atual = data.price if data else pos.entry_price
            except Exception:
                preco_atual = pos.entry_price
            pnl_est = (preco_atual - pos.entry_price) * pos.qty
            change  = (preco_atual - pos.entry_price) / pos.entry_price * 100
            lines.append(
                f"  `{symbol}` entrada ${pos.entry_price:.4f} → ${preco_atual:.4f} "
                f"({change:+.2f}%) | PnL est. ${pnl_est:+.4f} | SL ${pos.sl:.4f} TP ${pos.tp:.4f}"
            )

    color = 0x57F287 if total_pnl_global >= 0 else 0xED4245
    
    discord_notify(
        title=f"Relatorio Semanal — {week_start.strftime('%m/%d')} a {now.strftime('%m/%d/%Y')}",
        message="\n".join(lines),
        color=color,
    )


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log.exception("Erro no relatorio semanal")
        sys.exit(1)

    sys.exit(0)
