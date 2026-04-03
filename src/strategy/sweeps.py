from __future__ import annotations

from typing import List, Optional, Tuple

from config import settings
from src.data.candles import Candle
from src.strategy.swing import find_swing_highs, find_swing_lows


def _wick_body_ratio_for_sweep_low(c: Candle) -> float:
    body = abs(c.close - c.open)
    wick = min(c.open, c.close) - c.low
    if body <= 0:
        return float("inf") if wick > 0 else 0.0
    return wick / body


def _wick_body_ratio_for_sweep_high(c: Candle) -> float:
    body = abs(c.close - c.open)
    wick = c.high - max(c.open, c.close)
    if body <= 0:
        return float("inf") if wick > 0 else 0.0
    return wick / body


def detect_sweep_low(candles: List[Candle], sweep_candle_index: int) -> Tuple[bool, Optional[float], Optional[float]]:
    """
    Sweep low rule (for BUY):
    - break previous low (previous swing low)
    - penetration 0.03%–0.20%
    - wick/body >= 1.3
    """
    if sweep_candle_index < 0 or sweep_candle_index >= len(candles):
        return (False, None, None)

    if len(candles) < 10:
        return (False, None, None)

    swings = find_swing_lows(candles, left=3, right=3)
    prev = None
    for s in reversed(swings):
        if s.index < sweep_candle_index:
            prev = s
            break
    if prev is None:
        return (False, None, None)

    c = candles[sweep_candle_index]
    prev_low = prev.price
    if c.low >= prev_low:
        return (False, prev_low, None)

    penetration = (prev_low - c.low) / prev_low
    if not (settings.SWEEP_PEN_MIN_PCT <= penetration <= settings.SWEEP_PEN_MAX_PCT):
        return (False, prev_low, penetration)

    ratio = _wick_body_ratio_for_sweep_low(c)
    if ratio < settings.SWEEP_WICK_TO_BODY_MIN:
        return (False, prev_low, penetration)

    return (True, prev_low, penetration)


def detect_sweep_high(candles: List[Candle], sweep_candle_index: int) -> Tuple[bool, Optional[float], Optional[float]]:
    """
    Sweep high rule (for SELL):
    - break previous high (previous swing high)
    - penetration 0.03%–0.20%
    - wick/body >= 1.3
    """
    if sweep_candle_index < 0 or sweep_candle_index >= len(candles):
        return (False, None, None)

    if len(candles) < 10:
        return (False, None, None)

    swings = find_swing_highs(candles, left=3, right=3)
    prev = None
    for s in reversed(swings):
        if s.index < sweep_candle_index:
            prev = s
            break
    if prev is None:
        return (False, None, None)

    c = candles[sweep_candle_index]
    prev_high = prev.price
    if c.high <= prev_high:
        return (False, prev_high, None)

    penetration = (c.high - prev_high) / prev_high
    if not (settings.SWEEP_PEN_MIN_PCT <= penetration <= settings.SWEEP_PEN_MAX_PCT):
        return (False, prev_high, penetration)

    ratio = _wick_body_ratio_for_sweep_high(c)
    if ratio < settings.SWEEP_WICK_TO_BODY_MIN:
        return (False, prev_high, penetration)

    return (True, prev_high, penetration)

