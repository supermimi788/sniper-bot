from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.data.candles import Candle


@dataclass(frozen=True)
class SwingPoint:
    index: int
    price: float


def find_swing_highs(candles: List[Candle], left: int = 3, right: int = 3) -> List[SwingPoint]:
    """
    Fractal swing highs:
    candles[i].high is greater than all highs in [i-left, i+right] excluding itself.
    """
    if len(candles) < left + right + 1:
        return []
    out: List[SwingPoint] = []
    for i in range(left, len(candles) - right):
        hi = candles[i].high
        ok = True
        for j in range(i - left, i + right + 1):
            if j == i:
                continue
            if candles[j].high >= hi:
                ok = False
                break
        if ok:
            out.append(SwingPoint(index=i, price=hi))
    return out


def find_swing_lows(candles: List[Candle], left: int = 3, right: int = 3) -> List[SwingPoint]:
    """
    Fractal swing lows:
    candles[i].low is less than all lows in [i-left, i+right] excluding itself.
    """
    if len(candles) < left + right + 1:
        return []
    out: List[SwingPoint] = []
    for i in range(left, len(candles) - right):
        lo = candles[i].low
        ok = True
        for j in range(i - left, i + right + 1):
            if j == i:
                continue
            if candles[j].low <= lo:
                ok = False
                break
        if ok:
            out.append(SwingPoint(index=i, price=lo))
    return out

