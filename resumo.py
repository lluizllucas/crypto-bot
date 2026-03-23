"""
resumo.py -- Gera e envia resumo diario no Discord.
Rodado via cron todo dia a meia-noite.
"""

import re
import os
import glob
import requests
from datetime import datetime, timedelta, timezone

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")


def parse_hoje() -> dict:
    """Parseia o log atual e extrai metricas das ultimas 24 horas."""
    filepath = "/app/logs/bot.log"

    if not os.path.exists(filepath):
        return {}

    trades  = []
    sinais  = {"BUY": 0, "SELL": 0, "HOLD": 0}
    erros   = 0
    saldo   = 0.0

    # Pega apenas eventos das ultimas 24 horas
    limite = datetime.now() - timedelta(hours=24)

    pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[(\w+)\] (.+)")

    with open(filepath, encoding="utf-8") as f:
        for line in f:
            m = pattern.match(line.strip())
            if not m:
                continue
            ts_str, level, msg = m.groups()
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")

            # Ignora eventos mais antigos que 24 horas
            if ts < limite:
                continue

            if "Posicao fechada" in msg:
                pnl = re.search(r"PnL: \$([+-][\d.]+)", msg)
                reason = re.search(r"\[([A-Z\-]+)\] Posicao", msg)
                if pnl and reason:
                    trades.append({
                        "pnl": float(pnl.group(1)),
                        "reason": reason.group(1)
                    })

            elif "Sinal:" in msg:
                for sig in ["BUY", "SELL", "HOLD"]:
                    if f"Sinal: {sig}" in msg:
                        sinais[sig] += 1

            elif "Saldo USDT:" in msg:
                s = re.search(r"Saldo USDT: \$([\d.]+)", msg)
                if s:
                    saldo = float(s.group(1))

            elif level == "ERROR":
                erros += 1

    wins   = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    pnl    = sum(t["pnl"] for t in trades)
    wr     = len(wins) / len(trades) * 100 if trades else 0

    return {
        "saldo":   saldo,
        "trades":  len(trades),
        "wins":    len(wins),
        "losses":  len(losses),
        "pnl":     pnl,
        "wr":      wr,
        "sinais":  sinais,
        "erros":   erros,
    }


def send_discord(data: dict):
    """Envia o resumo para o Discord."""
    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL nao configurado")
        return

    if not data:
        print("Sem dados para enviar")
        return

    hoje = datetime.now().strftime("%d/%m/%Y")
    pnl_emoji = "+" if data["pnl"] >= 0 else "-"

    fields = [
        {"name": "Saldo USDT", "value": f"${data['saldo']:.2f}", "inline": True},
        {"name": "PnL do dia", "value": f"${data['pnl']:+.4f}", "inline": True},
        {"name": "Operacoes", "value": f"{data['trades']} ({data['wins']}W / {data['losses']}L)", "inline": True},
        {"name": "Win rate", "value": f"{data['wr']:.1f}%", "inline": True},
        {"name": "Sinais LLM", "value": f"BUY: {data['sinais']['BUY']} | SELL: {data['sinais']['SELL']} | HOLD: {data['sinais']['HOLD']}", "inline": False},
        {"name": "Erros", "value": str(data['erros']), "inline": True},
    ]

    color = 0x57F287 if data["pnl"] >= 0 else 0xED4245

    payload = {
        "embeds": [{
            "title": f"Resumo diario -- {hoje}",
            "color": color,
            "fields": fields,
            "footer": {"text": "Trading Bot"},
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }]
    }

    r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    print(f"Discord: {r.status_code}")


if __name__ == "__main__":
    data = parse_hoje()
    send_discord(data)
    print("Resumo enviado!")