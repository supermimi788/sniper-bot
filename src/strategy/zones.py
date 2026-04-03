from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from config import settings
from src.data.candles import Candle
from src.strategy.swing import find_swing_highs, find_swing_lows, SwingPoint


@dataclass(frozen=True)
class Zone:
    kind: str  # "support" or "resistance"
    lower: float
    upper: float
    center: float
    swing_index: int


def _zone_width_pct() -> float:
    # Spec: zone width must be between 0.15% and 0.35%.
    # We choose the middle value inside that allowed range.
    return (settings.ZONE_WIDTH_MIN_PCT + settings.ZONE_WIDTH_MAX_PCT) / 2.0


def _make_support_zone(swing: SwingPoint) -> Zone:
    width = _zone_width_pct()
    half = width / 2.0
    center = swing.price
    lower = center * (1.0 - half)
    upper = center * (1.0 + half)
    return Zone(kind="support", lower=lower, upper=upper, center=center, swing_index=swing.index)


def _make_resistance_zone(swing: SwingPoint) -> Zone:
    width = _zone_width_pct()
    half = width / 2.0
    center = swing.price
    lower = center * (1.0 - half)
    upper = center * (1.0 + half)
    return Zone(kind="resistance", lower=lower, upper=upper, center=center, swing_index=swing.index)


def latest_support_zone(candles: List[Candle], left: int = 3, right: int = 3) -> Optional[Zone]:
    swings = find_swing_lows(candles, left=left, right=right)
    if not swings:
        return None
    return _make_support_zone(swings[-1])


def latest_resistance_zone(candles: List[Candle], left: int = 3, right: int = 3) -> Optional[Zone]:
    swings = find_swing_highs(candles, left=left, right=right)
    if not swings:
        return None
    return _make_resistance_zone(swings[-1])


def touch_support_zone(candle: Candle, zone: Zone) -> bool:
    assert zone.kind == "support"
    # Touch means the candle's price range intersects the zone.
    return candle.low <= zone.upper and candle.high >= zone.lower


def touch_resistance_zone(candle: Candle, zone: Zone) -> bool:
    assert zone.kind == "resistance"
    # Touch means the candle's price range intersects the zone.
    return candle.high >= zone.lower and candle.low <= zone.upper


def support_reaction(candle: Candle, zone: Zone) -> bool:
    """
    Used in 4H bias:
    bullish if there is a support zone touch and the candle is bullish.
    """
    assert zone.kind == "support"
    return touch_support_zone(candle, zone) and candle.close > candle.open


def resistance_reaction(candle: Candle, zone: Zone) -> bool:
    """
    Used in 4H bias:
    bearish if there is a resistance zone touch and the candle is bearish.
    """
    assert zone.kind == "resistance"
    return touch_resistance_zone(candle, zone) and candle.close < candle.open

