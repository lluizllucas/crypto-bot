"""
Testa o fluxo completo de coleta de dados sem chamar a LLM.
Executa:
  Binance (candles + ticker)
    -> indicadores -> range engine -> Fear & Greed
    -> posicoes abertas (Supabase)
    -> contexto JSON final (identico ao enviado a LLM)

Uso:
    python -m src.test_context
"""

import json
import logging

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from src.config import SYMBOLS

from src.application.market_data import get_market_data
from src.application.llm_analyst import build_context
from src.infra.supabase.repository import load_positions

if __name__ == "__main__":
    print("\nCarregando posicoes abertas do Supabase...")

    open_positions = load_positions()

    total = sum(len(v) for v in open_positions.values())

    print(f"  {total} posicao(oes) encontrada(s) em {len(open_positions)} par(es)\n")

    for symbol in SYMBOLS:
        print(f"{'=' * 60}")
        print(f"  Testando coleta de dados para: {symbol}")
        print('=' * 60)

        data = get_market_data(symbol)

        if data is None:
            print(f"  ERRO: get_market_data retornou None para {symbol}")
            continue

        print(f"\n  MarketData:")
        print(f"    Preco:              ${data.price:.2f}")
        print(f"    RSI 1h:             {data.rsi_1h}")
        print(f"    EMA 20/50/200:      {data.ema20} / {data.ema50} / {data.ema200}")
        print(f"    ATR:                {data.atr}")
        print(f"    Bollinger:          ${data.bb_lower} - ${data.bb_upper}")
        print(f"    Range pos. 24h:     {data.range_position_24h} (0=suporte, 1=resistencia)")
        print(f"    Range pos. 7d:      {data.range_position_7d}")
        print(f"    Range 24h:          ${data.range_low_24h} - ${data.range_high_24h}")
        print(f"    Range 7d:           ${data.range_low_7d} - ${data.range_high_7d}")
        print(f"    Range 30d:          ${data.range_low_30d} - ${data.range_high_30d}")
        print(f"    Fear & Greed:       {data.fear_greed}/100")
        print(f"    Volume 24h:         {data.volume_24h:.2f}")
        print(f"    Volume medio 5h:    {data.avg_volume_5h:.2f}")

        pos_symbol = open_positions.get(symbol, [])

        if pos_symbol:
            print(f"\n  Posicoes abertas ({len(pos_symbol)}):")

            for p in pos_symbol:
                pnl_pct = (data.price - p.entry_price) / p.entry_price * 100
                print(f"    entrada: ${p.entry_price:.2f} | qty: {p.qty} | SL: ${p.sl:.2f} | TP: ${p.tp:.2f} | PnL: {pnl_pct:+.2f}%")
        else:
            print(f"\n  Posicoes abertas: nenhuma")

        context = build_context(data, open_positions)

        print(f"\n  Contexto JSON enviado a LLM:")
        print(json.dumps(context, indent=4))
        print()
