from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TradeSignal:
    pair: str
    side: str  # "long" or "short"

    entry_ts_ms: int
    entry_price: float

    sl_price: float
    final_tp_price: float

    score: int
    # Optional debug info (keep simple; useful for CSV/Telegram later).
    reason: Optional[str] = None

