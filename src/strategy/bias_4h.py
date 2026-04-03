from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from config import settings
from src.data.candles import Candle
from src.data.indicators import ema_on_candles
from src.strategy.swing import find_swing_highs, find_swing_lows, SwingPoint
from src.strategy.zones import latest_resistance_zone, latest_support_zone, resistance_reaction, support_reaction


@dataclass(frozen=True)
class Bias4H:
    bias_type: str  # "bullish", "bearish", "range_lower", "range_upper", "range_middle"
    range_low: Optional[float] = None
    range_high: Optional[float] = None


def _latest_close(candles: List[Candle]) -> float:
    return candles[-1].close


def _prev_two_prices(points: List[SwingPoint]) -> Optional[Tuple[float, float]]:
    if len(points) < 2:
        return None
    return (points[-2].price, points[-1].price)


def _bullish_bos(candles: List[Candle], swing_highs: List[SwingPoint]) -> bool:
    if len(candles) < 5 or not swing_highs:
        return False
    latest = len(candles) - 1
    prev_high = None
    for s in reversed(swing_highs):
        if s.index < latest:
            prev_high = s.price
            break
    if prev_high is None:
        return False
    return candles[-1].close > prev_high


def _bearish_bos(candles: List[Candle], swing_lows: List[SwingPoint]) -> bool:
    if len(candles) < 5 or not swing_lows:
        return False
    latest = len(candles) - 1
    prev_low = None
    for s in reversed(swing_lows):
        if s.index < latest:
            prev_low = s.price
            break
    if prev_low is None:
        return False
    return candles[-1].close < prev_low


def _range_quantiles(candles: List[Candle], swing_highs: List[SwingPoint], swing_lows: List[SwingPoint]) -> Bias4H:
    if not swing_highs or not swing_lows:
        return Bias4H(bias_type="range_middle")

    range_high = max(s.price for s in swing_highs[-15:])
    range_low = min(s.price for s in swing_lows[-15:])
    if range_high <= 0 or range_high == range_low:
        return Bias4H(bias_type="range_middle", range_low=range_low, range_high=range_high)

    pos = (_latest_close(candles) - range_low) / (range_high - range_low)
    if pos <= 0.25:
        return Bias4H(bias_type="range_lower", range_low=range_low, range_high=range_high)
    if pos >= 0.75:
        return Bias4H(bias_type="range_upper", range_low=range_low, range_high=range_high)
    return Bias4H(bias_type="range_middle", range_low=range_low, range_high=range_high)


def compute_bias_4h(candles_4h: List[Candle]) -> Bias4H:
    """
    4H BIAS rules (exact structure, implemented as binary checks):
    Bullish if 2 of:
      - HH/HL
      - above EMA50
      - bullish BOS
      - support reaction
    Bearish if 2 of:
      - LH/LL
      - below EMA50
      - bearish BOS
      - resistance reaction
    Otherwise -> RANGE (then apply range lower/upper/middle rule).
    """
    if len(candles_4h) < 80:
        return Bias4H(bias_type="range_middle")

    swing_highs = find_swing_highs(candles_4h, left=3, right=3)
    swing_lows = find_swing_lows(candles_4h, left=3, right=3)

    hh_hl = False
    lh_ll = False
    high_two = _prev_two_prices(swing_highs)
    low_two = _prev_two_prices(swing_lows)
    if high_two is not None and low_two is not None:
        prev_high, last_high = high_two
        prev_low, last_low = low_two
        hh_hl = (last_high > prev_high) and (last_low > prev_low)
        lh_ll = (last_high < prev_high) and (last_low < prev_low)

    ema50 = ema_on_candles(candles_4h, period=settings.EMA_PERIOD)
    above_ema = candles_4h[-1].close > ema50
    below_ema = candles_4h[-1].close < ema50

    bullish_bos = _bullish_bos(candles_4h, swing_highs)
    bearish_bos = _bearish_bos(candles_4h, swing_lows)

    # Support/resistance reaction on the latest 4H candle.
    support_zone = latest_support_zone(candles_4h)
    resistance_zone = latest_resistance_zone(candles_4h)
    sup_react = support_zone is not None and support_reaction(candles_4h[-1], support_zone)
    res_react = resistance_zone is not None and resistance_reaction(candles_4h[-1], resistance_zone)

    bull_count = sum([hh_hl, above_ema, bullish_bos, sup_react])
    bear_count = sum([lh_ll, below_ema, bearish_bos, res_react])

    # Apply the ">=2 then decide, unclear -> RANGE" logic.
    if bull_count >= 2 and bear_count < 2:
        return Bias4H(bias_type="bullish")
    if bear_count >= 2 and bull_count < 2:
        return Bias4H(bias_type="bearish")

    # If both are >=2 (rare), spec says "If unclear -> RANGE".
    return _range_quantiles(candles_4h, swing_highs, swing_lows)

