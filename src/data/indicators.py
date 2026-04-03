from __future__ import annotations

from typing import List

from src.data.candles import Candle


def ema(values: List[float], period: int) -> List[float]:
    """
    Standard EMA.
    Returns a list of the same length as `values`; early values are still computed
    using the EMA recurrence so callers can use the last element safely.
    """
    if not values:
        return []
    if period <= 0:
        raise ValueError("period must be > 0")

    k = 2.0 / (period + 1.0)
    out: List[float] = [values[0]]
    for v in values[1:]:
        prev = out[-1]
        out.append(v * k + prev * (1.0 - k))
    return out


def ema_on_candles(candles: List[Candle], period: int) -> float:
    closes = [c.close for c in candles]
    if len(closes) < 2:
        return closes[-1] if closes else 0.0
    e = ema(closes, period=period)
    return e[-1]

