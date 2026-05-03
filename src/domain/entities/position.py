from datetime import datetime
from dataclasses import dataclass


@dataclass
class Position:
    """Representa um lote aberto de compra em um par."""
    entry_price:   float
    qty:           float
    sl:            float
    tp:            float
    ts:            datetime
    db_id:         str = ""   # id da linha no Supabase (open_positions)
    llm_log_id:    str = ""   # log LLM que originou a compra
    original_sl:   float = 0.0  # SL original antes de ajustes progressivos
    original_tp:   float = 0.0  # TP original antes de extensoes
    tp_hold_count: int = 0    # numero de vezes que o LLM segurou o TP
